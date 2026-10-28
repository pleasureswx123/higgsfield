import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createModelVariant } from '@/api/studio/models'
import { variantPayload } from '@/utils/modelVariant'

export function useModelVariantEditor(current, onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () =>
      current().status === 'draft' &&
      (user.permissions.includes('*:*:*') || user.permissions.includes('model:write'))
  )
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    selected = ref(),
    formRef = ref(),
    form = reactive(Object.create(null))
  let alive = true,
    signature = '',
    key = ''
  function start() {
    if (!alive || pending.value || !canWrite.value) return
    selected.value = JSON.parse(JSON.stringify(current()))
    for (const name of Object.keys(form)) delete form[name]
    for (const name of Object.keys(selected.value.capabilities.variantDimensions)) form[name] = ''
    open.value = true
    error.value = ''
    signature = ''
    key = ''
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
      const payload = variantPayload(selected.value.capabilities.variantDimensions, form)
      const next = JSON.stringify([selected.value.id, payload])
      if (signature !== next) {
        signature = next
        key = crypto.randomUUID()
      }
      await createModelVariant(selected.value.id, payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive) error.value = cause instanceof Error ? cause.message : '规格登记失败'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  onBeforeUnmount(() => {
    alive = false
  })
  return { canWrite, open, pending, error, selected, formRef, form, start, close, submit }
}
