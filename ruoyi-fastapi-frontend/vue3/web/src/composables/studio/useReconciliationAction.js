import { computed, reactive, ref, watch, onDeactivated, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { changeReconciliationLine } from '@/api/studio/reconciliations'

export function useReconciliationAction(onSaved) {
  const user = useUserStore()
  const allowed = computed(() => user.permissions.includes('*:*:*') ||
    (user.permissions.includes('billing:read') && user.permissions.includes('billing:reconcile')))
  const target = ref(), pending = ref(false), error = ref(''), formRef = ref()
  const form = reactive({ subjectId: '', reason: '' })
  let epoch = 0, key = '', signature = ''
  function reset() {
    epoch++
    target.value = undefined
    pending.value = false
    error.value = ''
    form.subjectId = ''; form.reason = ''; key = ''; signature = ''
  }
  function canStart(row, action) {
    if (action === 'resolve') return allowed.value && !pending.value && row?.status === 'disputed' && !!row.observationId
    return allowed.value && !pending.value && ['match', 'confirm'].includes(action) &&
      ['unmatched', 'matched'].includes(row?.status) &&
      (action === 'match' || (row.status === 'matched' && !!row.subjectId))
  }
  function start(row, action) {
    if (!canStart(row, action)) return
    reset()
    target.value = { id: row.id, revision: row.revision, action, externalLineKey: row.externalLineKey,
      amount: row.acceptedAmount ?? row.amount, currency: row.acceptedCurrency || row.currency, subjectId: row.subjectId,
      observationId: row.observationId, sourceAmount: row.sourceEvidence?.amount, sourceCurrency: row.sourceEvidence?.currency }
    form.subjectId = row.subjectId || ''
  }
  function close() { if (!pending.value) reset() }
  async function submit() {
    if (!target.value || !allowed.value || pending.value) return
    const current = epoch
    pending.value = true
    error.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (current !== epoch || !allowed.value) return
      const snapshot = target.value
      const data = { revision: snapshot.revision, reason: form.reason.trim() }
      if (!data.reason || data.reason.length > 2000) throw new Error('请填写操作依据，最多2000字符')
      if (snapshot.action === 'match' || snapshot.action === 'resolve') {
        const subjectId = form.subjectId.trim()
        if (!/^[1-9][0-9]{0,18}$/.test(subjectId) || BigInt(subjectId) > 9223372036854775807n)
          throw new Error('请输入有效计费对象ID')
        data.subjectId = subjectId
      }
      if (snapshot.action === 'resolve') data.observationId = snapshot.observationId
      const next = JSON.stringify([snapshot.id, snapshot.action, data])
      if (next !== signature) { signature = next; key = crypto.randomUUID() }
      await changeReconciliationLine(snapshot.id, snapshot.action, data, key)
      if (current === epoch && allowed.value) { reset(); await onSaved() }
    } catch (cause) {
      if (current === epoch) error.value = cause?.message || '操作结果未确认，请保留内容重试或刷新核对'
    } finally {
      if (current === epoch) pending.value = false
    }
  }
  function preventUnload(event) {
    if (pending.value) { event.preventDefault(); event.returnValue = '' }
  }
  globalThis.addEventListener?.('beforeunload', preventUnload)
  watch(allowed, value => { if (!value) reset() }, { flush: 'sync' })
  onDeactivated(reset)
  onBeforeUnmount(() => { reset(); globalThis.removeEventListener?.('beforeunload', preventUnload) })
  onBeforeRouteLeave(() => !pending.value)
  return { allowed, target, pending, error, form, formRef, canStart, start, close, submit }
}
