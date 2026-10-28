import { computed, onActivated, onDeactivated, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox, type FormInstance } from 'element-plus'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import {
  createProperty,
  listProperties,
  versionProperty,
  type PropertyDefinition,
  type PropertyDefinitionFields,
} from '@/api/elements'

export function usePropertyDefinitions(
  projectId: string,
  changed: (definition: PropertyDefinition) => void,
  visible: () => boolean = () => true,
) {
  const auth = useAuthStore()
  let mountedActive = true
  const active = ref(visible()),
    valid = ref(true),
    uncertain = ref(false)
  const locked = computed(() => saving.value || uncertain.value)
  const editable = computed(() => active.value && valid.value && Boolean(auth.token))
  let epoch = 0
  let intent:
    | { id?: string; payload: PropertyDefinitionFields & { propertyKey: string }; key: string }
    | undefined
  const rows = ref<PropertyDefinition[]>([]),
    page = ref(1),
    total = ref(0),
    loading = ref(false),
    saving = ref(false),
    error = ref(''),
    notice = ref('')
  const editing = ref<PropertyDefinition>(),
    form = ref<FormInstance>()
  const fields = reactive({
    propertyKey: `property_${crypto.randomUUID().slice(0, 8)}`,
    name: '',
    valueType: 'text' as PropertyDefinitionFields['valueType'],
    optionsText: '',
  })
  let baseline = JSON.stringify(fields),
    controller: AbortController | undefined
  const dirty = computed(() => JSON.stringify(fields) !== baseline)
  async function load() {
    if (!editable.value) return
    controller?.abort()
    const active = new AbortController()
    controller = active
    loading.value = true
    error.value = ''
    try {
      const response = await listProperties(projectId, page.value, active.signal)
      if (!active.signal.aborted) {
        rows.value = response.rows
        total.value = response.total
      }
    } catch (cause) {
      if (!active.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '属性加载失败'
    } finally {
      if (!active.signal.aborted) loading.value = false
    }
  }
  async function confirmDiscard() {
    if (!valid.value) return true
    if (locked.value) return false
    if (!dirty.value) return true
    const stamp = epoch
    try {
      await ElMessageBox.confirm('未保存的属性配置将被丢弃。', '保留修改', {
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
      })
      return stamp === epoch && !locked.value
    } catch {
      return false
    }
  }
  async function edit(definition?: PropertyDefinition) {
    const stamp = epoch
    if (!editable.value || locked.value) return
    if (!(await confirmDiscard())) return
    if (stamp !== epoch || !editable.value || locked.value) return
    epoch++
    editing.value = definition ? JSON.parse(JSON.stringify(definition)) : undefined
    Object.assign(fields, {
      propertyKey: definition?.propertyKey || `property_${crypto.randomUUID().slice(0, 8)}`,
      name: definition?.name || '',
      valueType: definition?.valueType === 'multi_select' ? 'multi_select' : 'text',
      optionsText: definition?.options.join('\n') || '',
    })
    if (definition?.valueType === 'single_select') fields.valueType = 'multi_select'
    baseline = JSON.stringify(fields)
    intent = undefined
    error.value = ''
    notice.value = ''
    form.value?.clearValidate()
  }
  async function save() {
    if (!editable.value || saving.value) return
    const stamp = epoch
    if (!intent && !(await form.value?.validate().catch(() => false))) return
    if (stamp !== epoch || !editable.value || saving.value) return
    const content: PropertyDefinitionFields = {
      name: fields.name.trim(),
      valueType: fields.valueType,
      options:
        fields.valueType === 'text'
          ? []
          : fields.optionsText
              .split('\n')
              .map((value) => value.trim())
              .filter(Boolean),
    }
    const payload = { ...content, propertyKey: fields.propertyKey }
    intent ??= {
      id: editing.value?.id,
      payload: JSON.parse(JSON.stringify(payload)),
      key: crypto.randomUUID(),
    }
    const request = intent
    saving.value = true
    uncertain.value = true
    error.value = ''
    notice.value = ''
    try {
      const { propertyKey: _propertyKey, ...versionFields } = request.payload
      const response = request.id
        ? await versionProperty(request.id, versionFields, request.key)
        : await createProperty(projectId, request.payload, request.key)
      if (stamp !== epoch) return
      intent = undefined
      uncertain.value = false
      editing.value = response.data
      Object.assign(fields, {
        propertyKey: response.data.propertyKey,
        name: response.data.name,
        valueType: response.data.valueType,
        optionsText: response.data.options.join('\n'),
      })
      baseline = JSON.stringify(fields)
      notice.value = `已保存定义版本 ${response.data.versionNo}。历史元素修订保持不变。`
      changed(response.data)
      await load()
    } catch (cause) {
      if (stamp !== epoch) return
      if (
        cause instanceof ApiError &&
        cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
        (cause.code === 601 || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
      ) {
        intent = undefined
        uncertain.value = false
      }
      error.value = cause instanceof Error ? cause.message : '保存失败'
    } finally {
      if (stamp === epoch) saving.value = false
    }
  }
  watch(page, () => {
    void load()
  })
  onBeforeRouteLeave(confirmDiscard)
  onBeforeRouteUpdate((to, from) => to.params.id === from.params.id || confirmDiscard())
  const suspend = () => {
    epoch++
    active.value = false
    controller?.abort()
    loading.value = false
    saving.value = false
  }
  const resume = () => {
    if (active.value || !mountedActive || !visible() || !valid.value) return
    active.value = true
    void load()
  }
  onDeactivated(() => {
    mountedActive = false
    suspend()
  })
  onActivated(() => {
    mountedActive = true
    resume()
  })
  watch(visible, value => value ? resume() : suspend(), { flush: 'sync' })
  onBeforeUnmount(suspend)
  watch(
    () => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions ?? [])],
    () => {
      suspend()
      valid.value = false
      rows.value = []
      total.value = 0
      editing.value = undefined
      Object.assign(fields, { propertyKey: '', name: '', valueType: 'text', optionsText: '' })
      baseline = JSON.stringify(fields)
      intent = undefined
      uncertain.value = false
      notice.value = ''
      error.value = '登录状态或权限已改变，请关闭并重新打开属性配置。'
    },
    { flush: 'sync' },
  )
  void load()
  return {
    active,
    valid,
    rows,
    page,
    total,
    loading,
    saving,
    locked,
    editable,
    uncertain,
    error,
    notice,
    editing,
    form,
    fields,
    dirty,
    load,
    edit,
    save,
    confirmDiscard,
  }
}
