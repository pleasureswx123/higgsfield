import { computed, ref, reactive, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import useUserStore from '@/store/modules/user'
import { listReconciliations, getReconciliation, listReconciliationLines, downloadReconciliation } from '@/api/studio/reconciliations'
import { saveAs } from 'file-saver'

export function useReconciliations() {
  const user = useUserStore()
  const allowed = computed(() => user.permissions.includes('*:*:*') || user.permissions.includes('billing:read'))
  const filters = reactive({ accountId: '', status: '' }), formRef = ref()
  const rows = ref([]), total = ref(0), page = ref(1), loading = ref(false), error = ref('')
  const detailOpen = ref(false), detail = ref(), detailLoading = ref(false), detailError = ref('')
  const lines = ref([]), lineTotal = ref(0), linePage = ref(1), lineStatus = ref('')
  const downloading = ref(false), downloadError = ref('')
  let downloadController
  async function download() {
    if (!alive || !allowed.value || downloading.value || !detailOpen.value || !detail.value?.attachment) return
    const identity = selectedId, attachment = detail.value.attachment, current = new AbortController()
    downloadController = current
    downloading.value = true; downloadError.value = ''
    try {
      const blob = await downloadReconciliation(identity, current.signal)
      if (downloadController !== current || !allowed.value || selectedId !== identity) return
      if (!blob || blob.type?.includes('json') || String(blob.size) !== attachment.byteSize)
        throw new Error('账单下载失败或大小不一致，请刷新后重试')
      saveAs(blob, attachment.fileName)
    } catch (cause) {
      if (downloadController === current) downloadError.value = cause?.message || '账单下载失败'
    } finally {
      if (downloadController === current) { downloading.value = false; downloadController = undefined }
    }
  }
  let listController, detailController, selectedId = '', applied = {}, alive = true, loaded = false
  function closeDetail() {
    downloadController?.abort()
    downloadController = undefined
    downloading.value = false; downloadError.value = ''
    detailController?.abort()
    detailController = undefined
    detailOpen.value = false
    selectedId = ''
    detail.value = undefined
    lines.value = []
    lineTotal.value = 0
    detailLoading.value = false
    detailError.value = ''
  }
  function clear() {
    listController?.abort()
    listController = undefined
    rows.value = []
    total.value = 0
    loading.value = false
    error.value = ''
    loaded = false
    closeDetail()
  }
  async function load() {
    if (!alive || !allowed.value) return
    loaded = true
    listController?.abort()
    const current = new AbortController()
    listController = current
    loading.value = true
    error.value = ''
    try {
      const response = await listReconciliations({ ...applied, pageNum: page.value, pageSize: 20 }, current.signal)
      if (listController === current) { rows.value = response.rows; total.value = response.total }
    } catch (cause) {
      if (listController === current) { rows.value = []; total.value = 0; error.value = cause?.message || '对账批次读取失败' }
    } finally {
      if (listController === current) loading.value = false
    }
  }
  async function search() {
    if (!alive || !allowed.value || !(await formRef.value?.validate().catch(() => false))) return
    applied = { ...(filters.accountId.trim() ? { accountId: filters.accountId.trim() } : {}),
      ...(filters.status ? { status: filters.status } : {}) }
    page.value = 1
    closeDetail()
    await load()
  }
  async function loadDetail() {
    if (!alive || !allowed.value || !selectedId || !detailOpen.value) return
    detailController?.abort()
    const current = new AbortController(), identity = selectedId
    detailController = current
    detailLoading.value = true
    detailError.value = ''
    try {
      const [batch, entries] = await Promise.all([
        getReconciliation(identity, current.signal),
        listReconciliationLines(identity, { pageNum: linePage.value, pageSize: 20,
          ...(lineStatus.value ? { status: lineStatus.value } : {}) }, current.signal),
      ])
      if (detailController === current) {
        detail.value = batch.data
        lines.value = entries.rows
        lineTotal.value = entries.total
      }
    } catch (cause) {
      if (detailController === current) {
        detail.value = undefined
        lines.value = []
        lineTotal.value = 0
        detailError.value = cause?.message || '账单文件明细读取失败'
      }
    } finally {
      if (detailController === current) detailLoading.value = false
    }
  }
  async function select(row) {
    if (!allowed.value || !rows.value.some(value => value.id === row.id)) return
    closeDetail()
    selectedId = row.id
    detailOpen.value = true
    linePage.value = 1
    lineStatus.value = ''
    await loadDetail()
  }
  async function filterLines() { linePage.value = 1; await loadDetail() }
  watch(allowed, value => { clear(); if (value) void load() }, { flush: 'sync' })
  onMounted(load)
  onActivated(() => { if (!loaded) void load() })
  onDeactivated(clear)
  onBeforeUnmount(() => { alive = false; clear() })
  return { allowed, filters, formRef, rows, total, page, loading, error, search, load, select,
    detailOpen, detail, detailLoading, detailError, lines, lineTotal, linePage, lineStatus,
    loadDetail, filterLines, closeDetail, downloading, downloadError, download }
}
