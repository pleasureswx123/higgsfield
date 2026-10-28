import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { createPriceSource } from '@/api/studio/prices'
import { priceSourcePayload } from '@/utils/priceSource'
import * as documentApi from '@/api/studio/documentUploads'
import { documentUploadItem, uploadDocument } from '@/utils/documentUpload'

export function usePriceSourceEditor(onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:write')
  )
  const open = ref(false),
    pending = ref(false),
    error = ref(''),
    formRef = ref(), fileName = ref(''), uploadStage = ref(''), uploadProgress = ref(0)
  const form = reactive({
    sourceType: 'vendor_document',
    sourceUrl: '',
    excerpt: '',
    observedAt: '',
  })
  let alive = true,
    signature = '',
    key = '', item, uploadController
  function selectFile(file) {
    if (pending.value || !canWrite.value) return
    form.uploadId = ''
    item = undefined
    fileName.value = ''
    uploadStage.value = ''
    uploadProgress.value = 0
    error.value = ''
    if (!file) return
    try { item = documentUploadItem(file); fileName.value = file.name }
    catch (cause) { error.value = cause.message }
  }
  async function upload() {
    if (!alive || !open.value || pending.value || !canWrite.value || !item) return
    pending.value = true
    error.value = ''
    const current = new AbortController()
    uploadController = current
    try {
      const id = await uploadDocument(item, documentApi, current.signal, (stage, value) => {
        if (alive && canWrite.value && !current.signal.aborted) { uploadStage.value = stage; uploadProgress.value = value }
      })
      if (alive && canWrite.value && !current.signal.aborted) form.uploadId = id
    } catch (cause) {
      if (alive) error.value = cause?.message || '上传未确认成功，可重试当前文件'
    } finally {
      if (alive) pending.value = false
      uploadController = undefined
    }
  }
  function start() {
    if (!alive || pending.value || !canWrite.value) return
    Object.assign(form, {
      sourceType: 'vendor_document',
      sourceUrl: '',
      excerpt: '',
      observedAt: '',
    })
    selectFile()
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
      if (item && !form.uploadId) throw new Error('请先上传并校验已选择的附件，或移除附件')
      const payload = priceSourcePayload(form)
      const next = JSON.stringify(payload)
      if (next !== signature) {
        signature = next
        key = crypto.randomUUID()
      }
      const response = await createPriceSource(payload, key)
      if (alive && canWrite.value) {
        open.value = false
        onSaved(response.data)
      }
    } catch (cause) {
      if (alive)
        error.value =
          cause instanceof Error ? cause.message : '价格来源登记未确认成功，请核对后重试'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  watch(canWrite, (allowed) => {
    if (!allowed) {
      uploadController?.abort()
      form.uploadId = ''
    }
  }, { flush: 'sync' })
  onBeforeUnmount(() => {
    alive = false
    uploadController?.abort()
  })
  return { canWrite, open, pending, error, formRef, form, fileName, uploadStage, uploadProgress, selectFile, upload, start, close, submit }
}
