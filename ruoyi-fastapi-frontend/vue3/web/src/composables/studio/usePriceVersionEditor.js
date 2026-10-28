import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createPriceVersion, updatePriceVersion } from '@/api/studio/prices'
import { priceVersionPayload } from '@/utils/priceVersion'

export function usePriceVersionEditor(onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:write')
  )
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    model = ref(),
    editing = ref(),
    formRef = ref()
  const form = reactive({ calculationScale: 10, items: [], sourceIds: '' })
  let alive = true,
    signature = '',
    key = ''
  function start(parent, version) {
    if (!alive || pending.value || !canWrite.value || (version && version.status !== 'draft'))
      return
    model.value = { ...parent }
    editing.value = version ? JSON.parse(JSON.stringify(version)) : undefined
    Object.assign(form, {
      calculationScale: version?.calculationScale ?? 10,
      items: JSON.parse(JSON.stringify(version?.items || [])),
      sourceIds: (version?.sourceIds || []).join(', '),
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
      const payload = priceVersionPayload(form)
      if (editing.value) payload.revision = editing.value.revision
      else payload.priceBookId = model.value.id
      const next = JSON.stringify([model.value.id, editing.value?.id, payload])
      if (signature !== next) {
        signature = next
        key = crypto.randomUUID()
      }
      if (editing.value) await updatePriceVersion(editing.value.id, payload, key)
      else await createPriceVersion(payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive) error.value = cause instanceof Error ? cause.message : '价格版本保存失败'
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
