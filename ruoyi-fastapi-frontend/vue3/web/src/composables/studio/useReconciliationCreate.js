import { computed, ref, reactive, watch, onBeforeUnmount, onDeactivated } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import * as uploadApi from '@/api/studio/documentUploads'
import { createReconciliation } from '@/api/studio/reconciliations'
import { documentUploadItem, uploadDocument } from '@/utils/documentUpload'
import { reconciliationInput } from '@/utils/reconciliationInput'

export function useReconciliationCreate(onSaved) {
  const user = useUserStore()
  const allowed = computed(() => user.permissions.includes('*:*:*') ||
    (user.permissions.includes('billing:read') && user.permissions.includes('billing:reconcile')))
  const open = ref(false), pending = ref(false), error = ref(''), formRef = ref(), receipt = ref()
  const fileName = ref(''), stage = ref(''), progress = ref(0)
  const form = reactive({ accountId: '', period: [] })
  let item, controller, epoch = 0, key = '', signature = ''
  function reset() {
    epoch++
    controller?.abort()
    controller = undefined
    item = undefined
    key = ''; signature = ''; fileName.value = ''; stage.value = ''; progress.value = 0
    receipt.value = undefined; open.value = false; pending.value = false; error.value = ''
    form.accountId = ''; form.period = []
  }
  function start() { if (allowed.value && !pending.value) { reset(); open.value = true } }
  function close() { if (!pending.value) reset() }
  function selectFile(file) {
    if (pending.value || !allowed.value || receipt.value) return
    item = undefined; fileName.value = ''; stage.value = ''; progress.value = 0; error.value = ''
    if (!file) return
    try { item = documentUploadItem(file, 'reconciliation'); fileName.value = file.name }
    catch (cause) { error.value = cause.message }
  }
  async function submit() {
    if (!allowed.value || !open.value || pending.value || receipt.value) return
    const current = epoch
    pending.value = true
    error.value = ''
    controller = new AbortController()
    const signal = controller.signal
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (current !== epoch || !allowed.value) return
      const data = reconciliationInput(form)
      if (!item) throw new Error('请选择标准 CSV 账单文件')
      data.uploadId = await uploadDocument(item, uploadApi, signal, (label, value) => {
        if (current === epoch) { stage.value = label; progress.value = value }
      })
      if (current !== epoch || !allowed.value || signal.aborted) return
      const next = JSON.stringify(data)
      if (next !== signature) { signature = next; key = crypto.randomUUID() }
      stage.value = '受理账单'
      const response = await createReconciliation(data, key)
      if (current === epoch && allowed.value) {
        receipt.value = response.data
        stage.value = '已受理，等待解析'
        await onSaved()
      }
    } catch (cause) {
      if (current === epoch) error.value = cause?.message || '受理结果未确认，请保留原内容重试'
    } finally {
      if (current === epoch) { pending.value = false; controller = undefined }
    }
  }
  const preventUnload = event => { if (pending.value) { event.preventDefault(); event.returnValue = '' } }
  globalThis.addEventListener?.('beforeunload', preventUnload)
  watch(allowed, value => { if (!value) reset() }, { flush: 'sync' })
  onBeforeRouteLeave(() => !pending.value)
  onDeactivated(reset)
  onBeforeUnmount(() => { reset(); globalThis.removeEventListener?.('beforeunload', preventUnload) })
  return { allowed, open, pending, error, formRef, receipt, fileName, stage, progress, form, start, close, selectFile, submit }
}
