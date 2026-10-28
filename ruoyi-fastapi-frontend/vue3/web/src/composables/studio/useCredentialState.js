import { onBeforeUnmount, onDeactivated, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { changeCredentialState } from '@/api/studio/credentials'

export function useCredentialState(refresh) {
  const user = useUserStore()
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    formRef = ref()
  const target = ref(null),
    action = ref('')
  const form = reactive({ reason: '' })
  let alive = true,
    signature = '',
    key = ''
  function available(row, kind) {
    const permission = kind === 'revoke' ? 'credential:revoke' : 'credential:disable'
    const states = {
      drain: ['active'],
      disable: ['draft', 'draining'],
      revoke: ['draft', 'active', 'draining', 'disabled'],
    }
    return (
      (user.permissions.includes('*:*:*') || user.permissions.includes(permission)) &&
      !!states[kind]?.includes(row.state)
    )
  }
  function start(row, kind) {
    if (pending.value || !available(row, kind)) return
    target.value = { ...row }
    action.value = kind
    form.reason = ''
    error.value = ''
    signature = ''
    key = ''
    open.value = true
  }
  function close() {
    if (pending.value) return
    open.value = false
    form.reason = ''
  }
  async function submit() {
    if (pending.value || !target.value || !available(target.value, action.value)) return
    // 先占用提交状态，防止异步表单校验期间重复点击。
    pending.value = true
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      error.value = ''
      const data = { revision: target.value.revision, reason: form.reason.trim() }
      const next = JSON.stringify([target.value.id, action.value, data])
      if (next !== signature) {
        signature = next
        key = crypto.randomUUID()
      }
      await changeCredentialState(target.value.id, action.value, data, key)
      if (!alive) return
      open.value = false
      form.reason = ''
      await refresh()
    } catch (cause) {
      if (alive) error.value = cause instanceof Error ? cause.message : '操作失败，请刷新版本后重试'
    } finally {
      pending.value = false
    }
  }
  onBeforeRouteLeave(() => {
    if (pending.value) return false
    if (open.value && form.reason && !window.confirm('离开将丢弃未提交的操作原因，是否继续？'))
      return false
    close()
    return true
  })
  const beforeUnload = (event) => {
    if (pending.value || (open.value && form.reason)) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onDeactivated(close)
  onBeforeUnmount(() => {
    alive = false
    window.removeEventListener('beforeunload', beforeUnload)
  })
  return { open, pending, error, formRef, form, target, action, available, start, close, submit }
}
