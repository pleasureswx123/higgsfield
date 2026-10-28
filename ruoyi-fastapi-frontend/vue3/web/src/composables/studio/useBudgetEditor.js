import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createBudget, updateBudget } from '@/api/studio/budgets'

const initial = () => ({
  subjectType: 'project',
  subjectId: '',
  purpose: 'platform',
  currency: 'CNY',
  cycleKind: 'monthly',
  businessTimezone: 'Asia/Shanghai',
})
export function useBudgetEditor(onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:budget')
  )
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    editing = ref(),
    formRef = ref()
  const form = reactive(initial())
  let alive = true,
    signature = '',
    key = ''
  function start(row) {
    if (!canWrite.value || pending.value) return
    editing.value = row ? { ...row } : undefined
    Object.assign(form, initial())
    error.value = ''
    signature = ''
    key = ''
    open.value = true
  }
  function close() {
    if (!pending.value) {
      open.value = false
      editing.value = undefined
      error.value = ''
    }
  }
  async function submit() {
    if (!alive || pending.value || !open.value || !canWrite.value) return
    pending.value = true
    error.value = ''
    try {
      if (!editing.value && !(await formRef.value?.validate().catch(() => false))) return
      if (!alive || !canWrite.value) return
      const row = editing.value
      const payload = row
        ? { revision: row.revision, active: !row.active }
        : {
            subject: { [form.subjectType === 'project' ? 'projectId' : 'userId']: form.subjectId },
            purpose: form.purpose,
            currency: form.currency,
            cycleKind: form.cycleKind,
            businessTimezone: form.businessTimezone.trim(),
          }
      const next = JSON.stringify([row?.id || null, payload])
      if (next !== signature) {
        signature = next
        key = crypto.randomUUID()
      }
      if (row) await updateBudget(row.id, payload, key)
      else await createBudget(payload, key)
      if (alive) {
        open.value = false
        onSaved()
      }
    } catch (cause) {
      if (alive)
        error.value = cause instanceof Error ? cause.message : '预算保存未确认成功，请核对后重试'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  onBeforeUnmount(() => {
    alive = false
  })
  return { canWrite, open, pending, error, editing, formRef, form, start, close, submit }
}
