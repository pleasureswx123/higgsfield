import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createPriceBook } from '@/api/studio/prices'

export function usePriceBookEditor(onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:write')
  )
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    formRef = ref()
  const form = reactive({
    modelVariantId: '',
    purpose: 'platform',
    accountId: '',
    currency: '',
    name: '',
  })
  let alive = true,
    signature = '',
    key = ''
  function start(modelVariantId = '') {
    if (!alive || pending.value || !canWrite.value) return
    Object.assign(form, {
      modelVariantId,
      purpose: 'platform',
      accountId: '',
      currency: '',
      name: '',
    })
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
        modelVariantId: form.modelVariantId,
        purpose: form.purpose,
        accountId: form.purpose === 'procurement' ? form.accountId : null,
        currency: form.currency,
        name: form.name.trim(),
      }
      const next = JSON.stringify(payload)
      if (next !== signature) {
        signature = next
        key = crypto.randomUUID()
      }
      await createPriceBook(payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive)
        error.value = cause instanceof Error ? cause.message : '价格簿登记未确认成功，请核对后重试'
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
