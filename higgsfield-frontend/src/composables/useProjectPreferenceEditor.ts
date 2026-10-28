import { ref, reactive, computed, watch, onBeforeUnmount, onDeactivated, onActivated } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessageBox } from 'element-plus'
import type { Project } from '@/api/projects'
import { getProjectPreference, getProjectCollections, putProjectPreference, type ProjectCollection } from '@/api/projectPreferences'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

export function useProjectPreferenceEditor(changed: () => void) {
  const auth = useAuthStore(), open = ref(false), target = ref<Project | null>(null)
  const form = ref<FormInstance>(), loading = ref(false), saving = ref(false), uncertain = ref(false), error = ref('')
  const collections = ref<ProjectCollection[]>([]), ready = ref(false)
  const fields = reactive({ revision: '0', isPinned: false, isHidden: false, collectionId: null as string | null, orderNum: 0 })
  const rules: FormRules = { orderNum: [{ type: 'integer', min: -2147483648, max: 2147483647, required: true, message: '请输入有效整数排序', trigger: 'change' }] }
  const locked = computed(() => saving.value || uncertain.value)
  const baseline = ref('')
  const signature = () => JSON.stringify([fields.isPinned, fields.isHidden, fields.collectionId, fields.orderNum])
  const dirty = computed(() => open.value && Boolean(baseline.value) && signature() !== baseline.value)
  let epoch = 0, active = true, reader: AbortController | undefined, writer: AbortController | undefined
  let intent: { id: string; key: string; data: typeof fields } | undefined
  async function load() {
    if (!target.value || !active || locked.value) return
    reader?.abort(); reader = new AbortController()
    const signal = reader.signal, ticket = ++epoch, id = target.value.id
    loading.value = true; ready.value = false; error.value = ''; collections.value = []
    try {
      const preference = await getProjectPreference(id, signal)
      const items: ProjectCollection[] = []
      for (let page = 1; ; page++) {
        const response = await getProjectCollections(page, signal)
        items.push(...response.rows)
        if (!response.hasNext) break
      }
      if (ticket !== epoch || signal.aborted) return
      Object.assign(fields, preference.data); baseline.value = signature(); collections.value = items; ready.value = true
    } catch (cause) {
      if (ticket === epoch && !signal.aborted) error.value = cause instanceof Error ? cause.message : '个人偏好加载失败'
    } finally { if (ticket === epoch) loading.value = false }
  }
  function start(project: Project) {
    if (locked.value) return
    target.value = project; open.value = true; void load()
  }
  function dismiss() {
    if (locked.value) return
    epoch++; reader?.abort(); open.value = false; target.value = null; ready.value = false; baseline.value = ''
  }
  function confirmDiscard() {
    if (locked.value) return false
    if (!dirty.value) return true
    const ticket = epoch
    return ElMessageBox.confirm('个人项目偏好尚未保存，是否放弃修改？', '未保存的修改', {
      confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning',
    }).then(() => ticket === epoch && !locked.value).catch(() => false)
  }
  async function close() {
    const ticket = epoch
    if (await confirmDiscard() && ticket === epoch) dismiss()
  }
  async function save() {
    if (!active || saving.value || !target.value || !ready.value) return
    const ticket = epoch
    if (!intent) {
      if (!(await form.value?.validate().catch(() => false)) || ticket !== epoch || !active || saving.value) return
      // 保存有限字段快照，不携带读取结果中的 projectId。
      intent = { id: target.value.id, key: crypto.randomUUID(), data: {
        revision: fields.revision, isPinned: fields.isPinned, isHidden: fields.isHidden,
        collectionId: fields.collectionId, orderNum: fields.orderNum,
      } }
    }
    const current = intent
    saving.value = true; uncertain.value = true; error.value = ''; writer = new AbortController()
    try {
      await putProjectPreference(current.id, current.data, current.key, writer.signal)
      if (ticket !== epoch || !active) return
      intent = undefined; uncertain.value = false; saving.value = false; dismiss(); changed()
    } catch (cause) {
      if (ticket !== epoch || !active) return
      const definite = cause instanceof ApiError && ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') || (cause.code >= 400 && cause.code < 500))
      if (definite) { intent = undefined; uncertain.value = false; ready.value = false }
      error.value = cause instanceof Error ? cause.message : '保存结果尚未确认，请重试同一请求'
    } finally { if (ticket === epoch) saving.value = false }
  }
  function clear() {
    epoch++; reader?.abort(); writer?.abort(); intent = undefined
    open.value = false; target.value = null; collections.value = []; error.value = ''
    saving.value = false; loading.value = false; uncertain.value = false; ready.value = false
    baseline.value = ''
    Object.assign(fields, { revision: '0', isPinned: false, isHidden: false, collectionId: null, orderNum: 0 })
  }
  watch(() => [auth.token, auth.user?.permissions.join('|')], clear, { flush: 'sync' })
  onBeforeRouteLeave(confirmDiscard)
  onDeactivated(() => { active = false; epoch++; reader?.abort(); writer?.abort(); saving.value = false; loading.value = false })
  onActivated(() => { active = true; if (open.value && !uncertain.value && !dirty.value) void load() })
  onBeforeUnmount(clear)
  return { open, target, form, fields, rules, collections, loading, saving, uncertain, locked, ready, error, start, close, load, save }
}
