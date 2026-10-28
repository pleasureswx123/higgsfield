import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createModelProfile } from '@/api/studio/models'

export function useModelProfileEditor(onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('model:write')
  )
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    formRef = ref()
  const form = reactive({ connectionId: '', code: '', displayName: '', kind: 'image' })
  let alive = true,
    signature = '',
    key = ''
  function start(connectionId = '') {
    if (!alive || pending.value || !canWrite.value) return
    Object.assign(form, { connectionId, code: '', displayName: '', kind: 'image' })
    error.value = ''
    signature = ''
    key = ''
    open.value = true
  }
  function close() {
    if (!pending.value) {
      open.value = false
      error.value = ''
    }
  }
  async function submit() {
    if (!alive || pending.value || !open.value || !canWrite.value) return
    pending.value = true
    error.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (!alive || !canWrite.value) return
      const payload = {
        connectionId: form.connectionId,
        code: form.code,
        displayName: form.displayName.trim(),
        kind: form.kind,
      }
      const next = JSON.stringify(payload)
      if (next !== signature) {
        signature = next
        key = crypto.randomUUID()
      }
      await createModelProfile(payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive)
        error.value =
          cause instanceof Error ? cause.message : '模型身份登记未确认成功，请核对后重试'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  onBeforeUnmount(() => {
    alive = false
  })
  return { canWrite, open, pending, error, formRef, form, start, close, submit }
}
