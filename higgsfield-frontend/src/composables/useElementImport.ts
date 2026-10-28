import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { ElMessageBox, type FormInstance } from 'element-plus'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
import { createUpload, readUpload, putUploadPart, completeUpload } from '@/api/assets'
import {
  createElementImport,
  readElementImport,
  listElementImportRows,
  editElementImportRow,
  confirmElementImport,
  type ImportBatch,
  type ImportRow,
} from '@/api/elementImports'
import { hashBlob } from '@/utils/hash'

export function useElementImport(
  projectId: string,
  changed: () => void,
  permissions: () => { canImport: boolean; canUpload: boolean; canCreate: boolean },
  visible: () => boolean = () => true,
) {
  const auth = useAuthStore()
  const form = ref<FormInstance>()
  let epoch = 0,
    editBaseline = ''
  const active = ref(visible())
  let mountedActive = true
  let alive = true
  const available = () => alive && active.value && Boolean(auth.token) && permissions().canImport
  const batch = ref<ImportBatch>(),
    rows = ref<ImportRow[]>([]),
    editing = ref<ImportRow>()
  const batchId = ref(''),
    page = ref(1),
    total = ref(0),
    busy = ref(false),
    error = ref(''),
    stage = ref('')
  const includeProjectName = ref(true),
    fileName = ref(''),
    confirmed = ref(false),
    result = ref(''),
    started = ref(false),
    needsRefresh = ref(true)
  let fixedPrefix = true
  let file: File | undefined,
    uploadId = '',
    sha = '',
    createKey = '',
    completeKey = '',
    importKey = ''
  let editKey = '',
    editPayload = '',
    confirmKey = '',
    confirmRevision = ''
  const editUncertain = ref(false)
  let editIntent: { batchId: string; row: ImportRow; key: string } | undefined
  let controller: AbortController | undefined
  function selectFile(value: File) {
    if (!available() || !permissions().canUpload || busy.value || started.value || batch.value)
      return
    const extension = value.name.split('.').pop()?.toLowerCase()
    const mimeTypes: Record<string, string> = {
      csv: 'text/csv',
      txt: 'text/plain',
      md: 'text/markdown',
      xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      pdf: 'application/pdf',
    }
    const mime = mimeTypes[extension || '']
    if (!mime || !value.size) {
      error.value = '请选择非空 CSV、XLSX、TXT、MD、DOCX 或 PDF 文件'
      return
    }
    file = new File([value], value.name, { type: mime })
    fileName.value = value.name
    sha = ''
    createKey = crypto.randomUUID()
    completeKey = crypto.randomUUID()
    importKey = crypto.randomUUID()
    error.value = ''
  }
  async function execute(action: (signal: AbortSignal) => Promise<void>) {
    if (!available() || busy.value) return
    const current = new AbortController()
    controller = current
    busy.value = true
    error.value = ''
    try {
      await action(current.signal)
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '操作失败，请重试'
    } finally {
      if (controller === current) {
        busy.value = false
        stage.value = ''
      }
    }
  }
  async function load(signal: AbortSignal, identity = batchId.value) {
    needsRefresh.value = true
    confirmed.value = false
    rows.value = []
    // 摘要与分页是独立请求，再读一次修订，避免展示跨修订拼接的复核结果。
    for (let attempt = 0; attempt < 2; attempt++) {
      const info = (await readElementImport(identity, signal)).data
      signal.throwIfAborted()
      if (info.projectId !== projectId) throw new Error('此批次不属于当前项目')
      const response = await listElementImportRows(identity, page.value, signal)
      signal.throwIfAborted()
      const checked = (await readElementImport(identity, signal)).data
      signal.throwIfAborted()
      if (checked.projectId !== projectId) throw new Error('此批次不属于当前项目')
      if (checked.revision !== info.revision) continue
      batch.value = checked
      batchId.value = checked.id
      rows.value = response.rows
      total.value = response.total
      needsRefresh.value = false
      return
    }
    throw new Error('批次正在被修改，请稍后刷新再复核')
  }
  async function upload() {
    if (!available() || !permissions().canUpload || busy.value || !file || batch.value) return
    // 文件与前缀选项在首次提交后固定，重试沿用原请求与幂等键。
    if (!started.value) fixedPrefix = includeProjectName.value
    started.value = true
    const selected = file,
      prefix = fixedPrefix
    await execute(async (signal) => {
      stage.value = '校验并上传文件…'
      if (!sha) {
        const digest = await hashBlob(selected, signal)
        signal.throwIfAborted()
        sha = digest
      }
      signal.throwIfAborted()
      if (!uploadId) {
        const created = await createUpload(projectId, selected, sha, createKey, signal)
        signal.throwIfAborted()
        uploadId = created.data.id
      }
      signal.throwIfAborted()
      const session = (await readUpload(uploadId, signal)).data
      signal.throwIfAborted()
      if (['failed', 'cancelled', 'expired'].includes(session.state))
        throw new Error('上传会话已失效，请关闭后重新导入')
      if (session.state !== 'ready') {
        const size = Number(session.partSize)
        for (let part = 1; part <= session.partCount; part++) {
          signal.throwIfAborted()
          if (session.receivedParts.includes(part)) continue
          stage.value = `上传分片 ${part} / ${session.partCount}…`
          const start = (part - 1) * size,
            blob = selected.slice(start, start + size)
          const partSha = await hashBlob(blob, signal)
          signal.throwIfAborted()
          await putUploadPart(uploadId, part, blob, start, selected.size, partSha, signal, () => {})
        }
        signal.throwIfAborted()
        await completeUpload(uploadId, sha, completeKey, signal)
      }
      stage.value = '创建解析批次…'
      signal.throwIfAborted()
      const response = await createElementImport(projectId, uploadId, prefix, importKey, signal)
      if (signal.aborted) return
      batchId.value = response.data.id
      await load(signal)
    })
  }
  function refresh() {
    if (editing.value || !/^[1-9]\d*$/.test(batchId.value)) return
    return execute((signal) => load(signal))
  }
  function edit(row: ImportRow) {
    if (
      !available() ||
      busy.value ||
      editUncertain.value ||
      needsRefresh.value ||
      batch.value?.status !== 'validated'
    )
      return
    editing.value = JSON.parse(JSON.stringify(row)) as ImportRow
    epoch++
    editBaseline = JSON.stringify(editing.value)
    form.value?.clearValidate?.()
  }
  async function confirmClose() {
    if (!available()) return true
    if (busy.value || editUncertain.value) return false
    if (!editing.value || JSON.stringify(editing.value) === editBaseline) return true
    const stamp = epoch, before = JSON.stringify(editing.value)
    try {
      await ElMessageBox.confirm(
        '未保存的候选修改将被丢弃，已保存的批次内容不变。',
        '放弃候选修改',
        {
          confirmButtonText: '放弃修改',
          cancelButtonText: '继续编辑',
        },
      )
      return stamp === epoch && before === JSON.stringify(editing.value) && !busy.value && !editUncertain.value
    } catch {
      return false
    }
  }
  async function discardEdit() {
    const stamp = epoch
    if (!(await confirmClose()) || stamp !== epoch || busy.value || editUncertain.value) return
    epoch++
    editing.value = undefined
    editBaseline = ''
    editIntent = undefined
  }
  async function save() {
    if (!available() || busy.value || !editing.value || !batch.value) return
    const stamp = epoch, before = JSON.stringify(editing.value)
    if (!editIntent && !(await form.value?.validate().catch(() => false))) return
    if (stamp !== epoch || !available() || busy.value || !editing.value || !batch.value ||
      (!editIntent && before !== JSON.stringify(editing.value))) return
    const row = JSON.parse(JSON.stringify(editing.value)) as ImportRow
    const payload = JSON.stringify(row)
    if (payload !== editPayload) {
      editPayload = payload
      editKey = crypto.randomUUID()
    }
    editIntent ??= { batchId: batch.value.id, row, key: editKey }
    const request = editIntent
    await execute(async (signal) => {
      needsRefresh.value = true
      confirmed.value = false
      editUncertain.value = true
      try {
        await editElementImportRow(request.batchId, request.row, request.key, signal)
      } catch (cause) {
        if (
          !signal.aborted &&
          cause instanceof ApiError &&
          cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
          (cause.code === 601 || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
        ) {
          editIntent = undefined
          editUncertain.value = false
        }
        throw cause
      }
      if (signal.aborted) return
      editIntent = undefined
      editUncertain.value = false
      editing.value = undefined
      await load(signal)
    })
  }
  async function confirm() {
    if (
      !available() ||
      !permissions().canCreate ||
      !batch.value ||
      needsRefresh.value ||
      editing.value ||
      !confirmed.value ||
      batch.value.status !== 'validated'
    )
      return
    const current = batch.value
    if (confirmRevision !== current.revision) {
      confirmRevision = current.revision
      confirmKey = crypto.randomUUID()
    }
    await execute(async (signal) => {
      needsRefresh.value = true
      confirmed.value = false
      const response = await confirmElementImport(current.id, current.revision, confirmKey, signal)
      if (signal.aborted) return
      result.value = `已创建 ${response.data.createdCount} 个元素。`
      // 已收到提交成功回执，即使后续读取失败也不能再次显示为待确认。
      batch.value = { ...current, status: 'finished' }
      changed()
      await load(signal)
    })
  }
  function stop() {
    epoch++
    controller?.abort()
    controller = undefined
    busy.value = false
    stage.value = ''
    needsRefresh.value = true
    confirmed.value = false
  }
  watch(
    () => JSON.stringify([permissions(), auth.user?.permissions || []]),
    () => {
      stop()
      rows.value = []
      total.value = 0
      if (!permissions().canImport) {
        editIntent = undefined
        editUncertain.value = false
        batch.value = undefined
        editing.value = undefined
        result.value = ''
      }
    },
    { flush: 'sync' },
  )
  onBeforeUnmount(() => {
    alive = false
    stop()
  })
  function suspend() {
    if (!active.value) return
    active.value = false
    stop()
  }
  function resume() {
    if (!mountedActive || !visible()) return
    active.value = true
  }
  onDeactivated(() => {
    mountedActive = false
    suspend()
  })
  onActivated(() => {
    mountedActive = true
    resume()
  })
  watch(visible, value => value ? resume() : suspend(), { flush: 'sync' })
  onBeforeRouteLeave(confirmClose)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || confirmClose())
  watch(
    () => auth.token,
    () => {
      stop()
      batch.value = undefined
      rows.value = []
      editing.value = undefined
      batchId.value = ''
      file = undefined
      fileName.value = ''
      result.value = ''
      error.value = ''
      confirmed.value = false
      total.value = 0
      uploadId = ''
      sha = ''
      needsRefresh.value = true
      started.value = false
      page.value = 1
      includeProjectName.value = true
      fixedPrefix = true
      createKey = ''
      completeKey = ''
      importKey = ''
      editKey = ''
      editPayload = ''
      editIntent = undefined
      editUncertain.value = false
      confirmKey = ''
      confirmRevision = ''
    },
    { flush: 'sync' },
  )
  return {
    active,
    form,
    confirmClose,
    discardEdit,
    batch,
    rows,
    editing,
    editUncertain,
    batchId,
    page,
    total,
    busy,
    error,
    stage,
    includeProjectName,
    fileName,
    confirmed,
    result,
    started,
    needsRefresh,
    selectFile,
    upload,
    refresh,
    edit,
    save,
    confirm,
  }
}
