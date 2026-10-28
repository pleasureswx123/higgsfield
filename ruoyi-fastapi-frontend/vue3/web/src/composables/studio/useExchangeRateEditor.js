import { computed, reactive, ref, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createExchangeRate, publishExchangeRate } from '@/api/studio/prices'
import { exchangeRatePayload, exchangeRatePublishPayload } from '@/utils/exchangeRate'

export function useExchangeRateEditor(onSaved) {
  const user = useUserStore()
  const permission = (code) => user.permissions.includes('*:*:*') || user.permissions.includes(code)
  const canCreate = computed(() => permission('billing:price:write')),
    canPublish = computed(() => permission('billing:price:publish'))
  const open = ref(false),
    pending = ref(false),
    target = ref(),
    error = ref(''),
    formRef = ref()
  const form = reactive({
    baseCurrency: '',
    quoteCurrency: '',
    rate: '',
    sourceId: '',
    validFrom: '',
    validUntil: '',
    reason: '',
  })
  let alive = true,
    signature = '',
    key = ''
  function start(row) {
    if (
      !alive ||
      pending.value ||
      (row ? !canPublish.value || row.status !== 'draft' : !canCreate.value)
    )
      return
    target.value = row ? { ...row } : undefined
    Object.assign(form, {
      baseCurrency: '',
      quoteCurrency: '',
      rate: '',
      sourceId: '',
      validFrom: '',
      validUntil: '',
      reason: '',
    })
    signature = ''
    key = ''
    error.value = ''
    open.value = true
  }
  function close() {
    if (!pending.value) open.value = false
  }
  async function submit() {
    if (
      !alive ||
      pending.value ||
      !open.value ||
      (target.value ? !canPublish.value : !canCreate.value)
    )
      return
    pending.value = true
    error.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (!alive || (target.value ? !canPublish.value : !canCreate.value)) return
      const payload = target.value
        ? exchangeRatePublishPayload(target.value.revision, form.reason)
        : exchangeRatePayload(form)
      const next = JSON.stringify([target.value?.id, payload])
      if (signature !== next) {
        signature = next
        key = crypto.randomUUID()
      }
      if (target.value) await publishExchangeRate(target.value.id, payload, key)
      else await createExchangeRate(payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive) error.value = cause?.message || '汇率操作未确认成功，请核对后重试'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  onBeforeUnmount(() => {
    alive = false
  })
  return {
    canCreate,
    canPublish,
    open,
    pending,
    target,
    error,
    formRef,
    form,
    start,
    close,
    submit,
  }
}
