import { computed, reactive, ref, watch, onDeactivated, onBeforeUnmount } from 'vue'
import useUserStore from '@/store/modules/user'
import { simulatePrice } from '@/api/studio/prices'
import { priceSimulationPayload, simulationFields } from '@/utils/priceSimulation'

export function usePriceSimulation(versionId) {
  const user = useUserStore()
  const allowed = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:read')
  )
  const form = reactive({
    dimensions: '{}',
    exchangeRateVersionId: '',
    ...Object.fromEntries(simulationFields.map(([name]) => [name, ''])),
  })
  const result = ref(),
    error = ref(''),
    pending = ref(false),
    formRef = ref()
  let controller,
    epoch = 0
  function clear() {
    epoch++
    controller?.abort()
    controller = undefined
    result.value = undefined
    error.value = ''
    pending.value = false
  }
  async function submit() {
    if (pending.value || !allowed.value || !versionId()) return
    clear()
    const attempt = epoch,
      id = versionId()
    pending.value = true
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (epoch !== attempt || !allowed.value) return
      const payload = priceSimulationPayload(form)
      const current = new AbortController()
      controller = current
      const response = await simulatePrice(id, payload, current.signal)
      if (epoch === attempt) result.value = response.data
    } catch (cause) {
      if (epoch === attempt) error.value = cause?.message || '价格试算失败'
    } finally {
      if (epoch === attempt) pending.value = false
    }
  }
  watch(form, clear, { flush: 'sync' })
  watch(versionId, clear, { flush: 'sync' })
  watch(allowed, clear, { flush: 'sync' })
  onDeactivated(clear)
  onBeforeUnmount(clear)
  return { allowed, form, formRef, result, error, pending, submit }
}
