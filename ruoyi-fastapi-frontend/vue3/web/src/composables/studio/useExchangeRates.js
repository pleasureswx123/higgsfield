import { computed, reactive, ref, watch, onDeactivated, onBeforeUnmount } from 'vue'
import useUserStore from '@/store/modules/user'
import { listExchangeRates } from '@/api/studio/prices'

export function useExchangeRates() {
  const user = useUserStore()
  const allowed = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:read')
  )
  const open = ref(false),
    selected = ref(),
    rows = ref([]),
    total = ref(0),
    page = ref(1),
    loading = ref(false),
    error = ref('')
  const filters = reactive({ baseCurrency: '', quoteCurrency: '' })
  let controller
  function clear() {
    controller?.abort()
    controller = undefined
    rows.value = []
    total.value = 0
    selected.value = undefined
    loading.value = false
    error.value = ''
  }
  async function load() {
    clear()
    if (!allowed.value || !open.value) return
    if (Object.values(filters).some((value) => value && !/^[A-Z]{3}$/.test(value))) {
      error.value = '币种须为三个大写字母'
      return
    }
    const current = new AbortController()
    controller = current
    loading.value = true
    const params = {
      pageNum: page.value,
      pageSize: 20,
      ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
    }
    try {
      const response = await listExchangeRates(params, current.signal)
      if (controller === current) {
        rows.value = response.rows
        total.value = response.total
      }
    } catch (cause) {
      if (controller === current) error.value = cause?.message || '汇率读取失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  function search() {
    page.value = 1
    return load()
  }
  function select(row) {
    if (allowed.value && rows.value.includes(row)) selected.value = row
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
    open,
    (value) => {
      if (value) search()
      else clear()
    },
    { flush: 'sync' }
  )
  watch(
    allowed,
    () => {
      clear()
      open.value = false
    },
    { flush: 'sync' }
  )
  onDeactivated(() => {
    clear()
    open.value = false
  })
  onBeforeUnmount(clear)
  return {
    allowed,
    open,
    selected,
    rows,
    total,
    page,
    loading,
    error,
    filters,
    load,
    search,
    select,
  }
}
