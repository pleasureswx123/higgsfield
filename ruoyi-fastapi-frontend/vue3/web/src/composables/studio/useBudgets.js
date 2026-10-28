import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'
import useUserStore from '@/store/modules/user'
import { listBudgets, listBudgetPeriods, listBudgetLedger } from '@/api/studio/budgets'

export function useBudgets() {
  const user = useUserStore()
  const canReadLedger = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:read')
  )
  const filters = reactive({ subjectType: '', subjectId: '', purpose: '' }),
    formRef = ref()
  const budget = ref(),
    period = ref()
  const section = () => reactive({ rows: [], total: 0, page: 1, loading: false, error: '' })
  const budgets = section(),
    periods = section(),
    ledger = section()
  const controllers = new Map()
  let active = false
  function clear(state) {
    controllers.get(state)?.abort()
    controllers.delete(state)
    state.rows = []
    state.total = 0
    state.loading = false
    state.error = ''
  }
  function clearPeriods() {
    budget.value = undefined
    period.value = undefined
    clear(periods)
    clear(ledger)
  }
  function clearAll() {
    clear(budgets)
    clearPeriods()
  }
  async function read(state, fetcher) {
    clear(state)
    if (!active) return
    const controller = new AbortController()
    controllers.set(state, controller)
    state.loading = true
    try {
      const result = await fetcher({ pageNum: state.page, pageSize: 20 }, controller.signal)
      if (!controller.signal.aborted) {
        state.rows = result.rows
        state.total = result.total
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        state.error = cause instanceof Error ? cause.message : '预算读取失败'
    } finally {
      if (controllers.get(state) === controller) state.loading = false
    }
  }
  async function load() {
    clearPeriods()
    await read(budgets, (pagination, signal) =>
      listBudgets(
        {
          ...pagination,
          subjectType: filters.subjectType || undefined,
          subjectId: filters.subjectId || undefined,
          purpose: filters.purpose || undefined,
        },
        signal
      )
    )
  }
  async function search() {
    clearAll()
    if (!(await formRef.value?.validate().catch(() => false))) return
    budgets.page = 1
    await load()
  }
  async function loadPeriods() {
    period.value = undefined
    clear(ledger)
    const id = budget.value?.id
    if (id) await read(periods, (params, signal) => listBudgetPeriods(id, params, signal))
  }
  async function selectBudget(row) {
    clearPeriods()
    budget.value = row
    periods.page = 1
    await loadPeriods()
  }
  async function loadLedger() {
    const id = period.value?.id
    if (id && canReadLedger.value)
      await read(ledger, (params, signal) => listBudgetLedger(id, params, signal))
  }
  async function selectPeriod(row) {
    clear(ledger)
    period.value = row
    ledger.page = 1
    await loadLedger()
  }
  function activate() {
    if (!active) {
      active = true
      void load()
    }
  }
  function deactivate() {
    active = false
    clearAll()
  }
  watch(filters, clearAll, { flush: 'sync' })
  watch(
    canReadLedger,
    (allowed) => {
      if (!allowed) {
        period.value = undefined
        clear(ledger)
      }
    },
    { flush: 'sync' }
  )
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  return {
    filters,
    formRef,
    budgets,
    periods,
    ledger,
    budget,
    period,
    canReadLedger,
    search,
    load,
    loadPeriods,
    selectBudget,
    loadLedger,
    selectPeriod,
  }
}
