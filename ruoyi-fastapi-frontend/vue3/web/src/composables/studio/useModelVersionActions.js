import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { changeModelVersionState } from '@/api/studio/models'

const permissions = { verify: 'model:verify', publish: 'model:publish', disable: 'model:publish' }
const statuses = {
  verify: ['draft'],
  publish: ['verified'],
  disable: ['draft', 'verified', 'published'],
}
export function useModelVersionActions(current, onSaved) {
  const user = useUserStore()
  function allowed(action, row = current()) {
    return (
      !!row &&
      statuses[action]?.includes(row.status) &&
      (user.permissions.includes('*:*:*') || user.permissions.includes(permissions[action]))
    )
  }
  const actions = computed(() => Object.keys(permissions).filter((action) => allowed(action)))
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    action = ref(''),
    selected = ref(),
    formRef = ref()
  const form = reactive({ reason: '', verificationRef: '' })
  let alive = true,
    signature = '',
    key = ''
  function start(value) {
    if (!alive || pending.value || !allowed(value)) return
    selected.value = { ...current() }
    action.value = value
    form.reason = ''
    form.verificationRef = ''
    signature = ''
    key = ''
    error.value = ''
    open.value = true
  }
  function close() {
    if (!pending.value) {
      open.value = false
      error.value = ''
    }
  }
  async function submit() {
    if (!alive || pending.value || !open.value || !allowed(action.value, selected.value)) return
    pending.value = true
    error.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (!alive || !allowed(action.value, selected.value)) return
      const payload = { revision: selected.value.revision, reason: form.reason.trim() }
      if (action.value === 'verify') payload.verificationRef = form.verificationRef.trim()
      const next = JSON.stringify([selected.value.id, action.value, payload])
      if (next !== signature) {
        signature = next
        key = crypto.randomUUID()
      }
      await changeModelVersionState(selected.value.id, action.value, payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive)
        error.value =
          cause instanceof Error ? cause.message : '模型状态变更未确认成功，请核对后重试'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  onBeforeUnmount(() => {
    alive = false
  })
  return { actions, open, pending, error, action, selected, formRef, form, start, close, submit }
}
