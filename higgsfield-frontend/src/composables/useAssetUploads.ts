import { markRaw, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { bindAsset, bindAssetVersion, completeUpload, createUpload, putUploadPart, readUpload, type Asset } from '@/api/assets'
import { ApiError } from '@/api/client'
import { hashBlob } from '@/utils/hash'
import { assetUploadMime } from '@/utils/assetFormats'

type Stage =
  'queued' | 'hashing' | 'uploading' | 'verifying' | 'binding' | 'done' | 'paused' | 'failed'
export interface UploadItem {
  target?: Pick<Asset, 'id' | 'revision' | 'mediaType' | 'name'>
  id: string
  file: File
  folderId: string | null
  name: string
  stage: Stage
  progress: number
  uploadedBytes: number
  error: string
  sha: string
  uploadId: string
  createKey: string
  completeKey: string
  bindKey: string
}
export function useAssetUploads(projectId: string, changed: () => void) {
  const auth = useAuthStore()
  let active = true, alive = true
  const available = () => active && alive && !!auth.token
  const items = reactive<UploadItem[]>([])
  const running = ref(false)
  let controller: AbortController | undefined
  function validation(file: File, target?: UploadItem['target']) {
    const mime = assetUploadMime(file)
    if (!mime || !file.size) return '请选择非空的图片、视频或 PDF、TXT、MD、HTML、DOCX、PPTX 文档'
    const kind = mime.startsWith('image/') ? 'image' : mime.startsWith('video/') ? 'video' : 'document'
    return target && kind !== target.mediaType ? '新版本必须保持原素材的图片、视频或文档类别' : ''
  }
  function enqueue(files: File[], folderId: string | null, target?: Asset) {
    if (!available()) return
    for (const file of files) {
      const error = validation(file, target)
      items.push({
        target: target ? { id: target.id, revision: target.revision, mediaType: target.mediaType, name: target.name } : undefined,
        id: crypto.randomUUID(),
        file: markRaw(file),
        folderId,
        name: file.name.slice(0, 200),
        stage: error ? 'failed' : 'queued',
        progress: 0,
        uploadedBytes: 0,
        error,
        sha: '',
        uploadId: '',
        createKey: crypto.randomUUID(),
        completeKey: crypto.randomUUID(),
        bindKey: crypto.randomUUID(),
      })
    }
    void drain()
  }
  async function drain() {
    if (!available() || running.value) return
    running.value = true
    try {
      let item: UploadItem | undefined
      while (available() && (item = items.find((value) => value.stage === 'queued'))) {
        controller = new AbortController()
        const signal = controller.signal
        try {
          item.error = ''
          item.stage = 'hashing'
          const current = item
          if (!item.sha)
            item.sha = await hashBlob(item.file, signal, (value) => {
              current.progress = Math.round(value * 100)
            })
          let session
          signal.throwIfAborted()
          if (!item.uploadId) {
            session = (await createUpload(projectId, item.file, item.sha, item.createKey, signal))
              .data
            item.uploadId = session.id
          }
          signal.throwIfAborted()
          // 创建请求的幂等结果可能是旧快照，每次恢复都读取实时分片状态。
          try {
            session = (await readUpload(item.uploadId, signal)).data
          } catch (error) {
            if (!(error instanceof ApiError) || error.code !== 410) throw error
            session = undefined
          }
          signal.throwIfAborted()
          if (!session || ['failed', 'cancelled', 'expired'].includes(session.state)) {
            // 仅终态会话重新创建；网络结果不明和绑定重试继续复用原幂等键。
            item.uploadId = ''
            item.createKey = crypto.randomUUID()
            item.completeKey = crypto.randomUUID()
            item.bindKey = crypto.randomUUID()
            item.uploadedBytes = 0
            item.progress = 0
            session = (await createUpload(projectId, item.file, item.sha, item.createKey, signal)).data
            item.uploadId = session.id
            session = (await readUpload(item.uploadId, signal)).data
          }
          if (session.state !== 'ready') {
            item.stage = 'uploading'
            const size = Number(session.partSize)
            let uploaded = session.receivedParts.reduce(
              (sum, part) => sum + Math.min(size, item!.file.size - (part - 1) * size),
              0,
            )
            item.uploadedBytes = uploaded
            item.progress = Math.floor((uploaded / item.file.size) * 100)
            for (let part = 1; part <= session.partCount; part++) {
              if (session.receivedParts.includes(part)) continue
              const start = (part - 1) * size
              const blob = item.file.slice(start, start + size)
              const sha = await hashBlob(blob, signal)
              signal.throwIfAborted()
              await putUploadPart(
                item.uploadId,
                part,
                blob,
                start,
                item.file.size,
                sha,
                signal,
                (loaded) => {
                  current.uploadedBytes = Math.min(current.file.size, uploaded + loaded)
                  current.progress = Math.min(
                    100,
                    Math.floor(((uploaded + loaded) / current.file.size) * 100),
                  )
                },
              )
              signal.throwIfAborted()
              uploaded += blob.size
            }
            item.stage = 'verifying'
            await completeUpload(item.uploadId, item.sha, item.completeKey, signal)
          }
          signal.throwIfAborted()
          item.stage = 'binding'
          if (item.target) await bindAssetVersion(item.target.id, item.target.revision, item.uploadId, item.bindKey, signal)
          else await bindAsset(projectId, item.uploadId, item.name, item.folderId, item.bindKey, signal)
          signal.throwIfAborted()
          item.uploadedBytes = item.file.size
          item.stage = 'done'
          item.progress = 100
          changed()
        } catch (error) {
          item.stage = signal.aborted ? 'paused' : 'failed'
          item.error = signal.aborted
            ? '已暂停，可继续上传'
            : error instanceof Error
              ? error.message
              : '上传失败'
        }
      }
    } finally {
      controller = undefined
      running.value = false
    }
  }
  function pause() {
    for (const item of items) if (item.stage === 'queued') item.stage = 'paused'
    controller?.abort()
  }
  function pauseItem(item: UploadItem) {
    if (item.stage === 'queued') item.stage = 'paused'
    else if (['hashing', 'uploading', 'verifying', 'binding'].includes(item.stage)) controller?.abort()
  }
  function retry(item: UploadItem) {
    if (!available() || !items.includes(item)) return
    if (!['paused', 'failed'].includes(item.stage)) return
    if (validation(item.file, item.target)) return
    item.stage = 'queued'
    void drain()
  }
  function clearFinished() {
    for (let index = items.length - 1; index >= 0; index--)
      if (items[index]?.stage === 'done') items.splice(index, 1)
  }
  onDeactivated(() => { active = false; pause() })
  onActivated(() => { active = true })
  onBeforeUnmount(() => { alive = false; pause() })
  watch(
    () => auth.token,
    () => {
      pause()
      items.splice(0)
    },
    { flush: 'sync' },
  )
  watch(() => JSON.stringify(auth.user?.permissions || []), pause, { flush: 'sync' })
  return { items, running, enqueue, pause, pauseItem, retry, clearFinished }
}
