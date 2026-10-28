import {
  computed,
  ref,
  reactive,
  watch,
  onMounted,
  onActivated,
  onDeactivated,
  onBeforeUnmount,
} from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { listGovernedProjects, governProject } from '@/api/studio/governance'

export const governanceActions = {
  active: ['pause', 'archive'],
  paused: ['resume', 'archive'],
  archived: ['restore'],
  pending_delete: [],
}
export function useProjectGovernance() {
  const user = useUserStore()
  const allowed = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('project:govern')
  )
  const filters = reactive({ q: '', status: '' })
  const rows = ref([]),
    page = ref(1),
    total = ref(0),
    loading = ref(false),
    error = ref('')
  const target = ref(),
    action = ref(''),
    reason = ref(''),
    pending = ref(false),
    actionError = ref(''),
    formRef = ref()
  let active = false,
    controller,
    epoch = 0,
    signature = '',
    key = ''
  function clear() {
    controller?.abort()
    controller = undefined
    rows.value = []
    total.value = 0
    loading.value = false
    error.value = ''
  }
  async function load() {
    clear()
    if (!active || !allowed.value) return
    const current = new AbortController()
    controller = current
    loading.value = true
    try {
      const result = await listGovernedProjects(
        {
          q: filters.q,
          ...(filters.status ? { status: filters.status } : {}),
          pageNum: page.value,
          pageSize: 20,
        },
        current.signal
      )
      if (controller === current) {
        rows.value = result.rows
        total.value = result.total
      }
    } catch (cause) {
      if (controller === current) error.value = cause?.message || '项目列表读取失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  function search() {
    page.value = 1
    return load()
  }
  function start(row, operation) {
    if (
      !active ||
      pending.value ||
      !allowed.value ||
      !governanceActions[row.status]?.includes(operation)
    )
      return
    target.value = { ...row }
    action.value = operation
    reason.value = ''
    actionError.value = ''
    signature = ''
    key = ''
  }
  function close() {
    if (!pending.value) {
      target.value = undefined
      actionError.value = ''
    }
  }
  async function submit() {
    if (!active || pending.value || !target.value || !allowed.value) return
    const currentEpoch = epoch
    pending.value = true
    actionError.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (epoch !== currentEpoch || !allowed.value || !target.value) return
      const data = {
        revision: target.value.revision,
        action: action.value,
        reason: reason.value.trim(),
      }
      if (!data.reason || data.reason.length > 4000) throw new Error('请填写治理原因，最多4000字符')
      const id = target.value.id,
        next = JSON.stringify([id, data])
      if (signature !== next) {
        signature = next
        key = crypto.randomUUID()
      }
      await governProject(id, data, key)
      if (epoch === currentEpoch && allowed.value) {
        target.value = undefined
        await load()
      }
    } catch (cause) {
      if (epoch === currentEpoch)
        actionError.value = cause?.message || '治理操作未确认成功，请核对后重试'
    } finally {
      if (epoch === currentEpoch) pending.value = false
    }
  }
  function deactivate() {
    active = false
    epoch++
    clear()
    target.value = undefined
    reason.value = ''
    actionError.value = ''
    pending.value = false
  }
  function activate() {
    if (!active) {
      active = true
      load()
    }
  }
  watch(
    filters,
    () => {
      clear()
      page.value = 1
    },
    { flush: 'sync' }
  )
  watch(
    allowed,
    (value) => {
      if (!value) {
        const wasActive = active
        deactivate()
        active = wasActive
      } else if (active) load()
    },
    { flush: 'sync' }
  )
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  onBeforeRouteLeave(() => !pending.value)
  return {
    allowed,
    filters,
    rows,
    page,
    total,
    loading,
    error,
    target,
    action,
    reason,
    pending,
    actionError,
    formRef,
    load,
    search,
    start,
    close,
    submit,
  }
}
