import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createModelVersion, updateModelVersion } from '@/api/studio/models'
import { emptyCapabilities, parseCapabilities } from '@/utils/modelCapabilities'

export function useModelVersionEditor(onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('model:write')
  )
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    model = ref(),
    editing = ref(),
    formRef = ref()
  const form = reactive({ gatewayAlias: '', underlyingModelId: '', region: '', capabilities: '' })
  let alive = true,
    signature = '',
    key = ''
  function start(parent, version) {
    if (!alive || pending.value || !canWrite.value || (version && version.status !== 'draft'))
      return
    model.value = { ...parent }
    editing.value = version ? JSON.parse(JSON.stringify(version)) : undefined
    Object.assign(form, {
      gatewayAlias: version?.gatewayAlias || '',
      underlyingModelId: version?.underlyingModelId || '',
      region: version?.region || '',
      capabilities: JSON.stringify(version?.capabilities || emptyCapabilities(), null, 2),
    })
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
    if (!alive || pending.value || !open.value || !canWrite.value) return
    pending.value = true
    error.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (!alive || !canWrite.value) return
      const payload = {
        gatewayAlias: form.gatewayAlias,
        underlyingModelId: form.underlyingModelId.trim() || null,
        capabilities: parseCapabilities(form.capabilities),
      }
      if (editing.value) payload.revision = editing.value.revision
      else Object.assign(payload, { region: form.region, schemaVersion: 1 })
      const next = JSON.stringify([model.value.id, editing.value?.id, payload])
      if (signature !== next) {
        signature = next
        key = crypto.randomUUID()
      }
      if (editing.value) await updateModelVersion(editing.value.id, payload, key)
      else await createModelVersion(model.value.id, payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive) error.value = cause instanceof Error ? cause.message : '能力版本保存失败'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  onBeforeUnmount(() => {
    alive = false
  })
  return { canWrite, open, pending, error, model, editing, formRef, form, start, close, submit }
}
