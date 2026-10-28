import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createBudgetPeriod, adjustBudgetLimit } from '@/api/studio/budgets'
import { budgetPeriodPayload } from '@/utils/budgetPeriod'

export function useBudgetPeriodEditor(onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:budget')
  )
  const budget = ref(),
    period = ref(),
    open = ref(false),
    pending = ref(false),
    error = ref(''),
    formRef = ref()
  const form = reactive({ month: '', start: '', amount: '', reason: '' })
  let alive = true,
    signature = '',
    key = ''
  function start(selectedBudget, selectedPeriod) {
    if (!alive || pending.value || !canWrite.value) return
    budget.value = { ...selectedBudget }
    period.value = selectedPeriod ? { ...selectedPeriod } : undefined
    Object.assign(form, {
      month: '',
      start: '',
      amount: selectedPeriod?.limitAmount || '',
      reason: '',
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
    if (!alive || pending.value || !canWrite.value || !open.value) return
    pending.value = true
    error.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (!alive || !canWrite.value) return
      const payload = budgetPeriodPayload(budget.value, period.value, form)
      const next = JSON.stringify([budget.value.id, period.value?.id, payload])
      if (next !== signature) {
        signature = next
        key = crypto.randomUUID()
      }
      if (period.value) await adjustBudgetLimit(period.value.id, payload, key)
      else await createBudgetPeriod(budget.value.id, payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive) error.value = cause instanceof Error ? cause.message : '预算周期保存失败'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  onBeforeUnmount(() => {
    alive = false
  })
  return { budget, period, open, pending, error, formRef, form, canWrite, start, close, submit }
}
