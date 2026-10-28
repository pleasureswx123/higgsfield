// 浏览器内摘要使用有界内存；服务端仍执行独立大小、摘要和真实内容校验。
export const DOCUMENT_MAX_BYTES = 64 * 1024 * 1024
const mimeTypes = { csv: 'text/csv', txt: 'text/plain', png: 'image/png', jpg: 'image/jpeg',
  jpeg: 'image/jpeg', webp: 'image/webp',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }

export function documentUploadItem(file, purpose = 'price_source') {
  if (!['price_source', 'reconciliation'].includes(purpose)) throw new Error('不支持的管理上传用途')
  const mime = mimeTypes[file?.name?.split('.').pop().toLowerCase()]
  if (!mime || !Number.isSafeInteger(file.size) || file.size <= 0 || file.size > DOCUMENT_MAX_BYTES)
    throw new Error('请选择非空且不超过 64 MiB 的 CSV、TXT、XLSX、PNG、JPEG 或 WebP 文件')
  if (purpose === 'reconciliation' && !['text/csv', mimeTypes.xlsx].includes(mime)) throw new Error('对账导入支持标准 CSV 或 XLSX 文件')
  if (file.name.length > 255 || /[\u0000-\u001f]/.test(file.name)) throw new Error('文件名过长或包含控制字符')
  return { file, mime, purpose, sha: '', id: '', createKey: crypto.randomUUID(), completeKey: crypto.randomUUID() }
}

export async function documentHash(blob, signal) {
  signal.throwIfAborted()
  if (!crypto.subtle) throw new Error('当前浏览器环境不支持安全摘要，请使用 HTTPS 或本机开发地址')
  const bytes = await blob.arrayBuffer()
  signal.throwIfAborted()
  const result = await crypto.subtle.digest('SHA-256', bytes)
  signal.throwIfAborted()
  return Array.from(new Uint8Array(result), value => value.toString(16).padStart(2, '0')).join('')
}

export async function uploadDocument(item, api, signal, progress, hash = documentHash) {
  signal.throwIfAborted()
  progress('计算摘要', 0)
  item.sha ||= await hash(item.file, signal)
  if (!item.id) {
    const response = await api.createDocumentUpload({ purpose: item.purpose, fileName: item.file.name,
      byteSize: String(item.file.size), mimeType: item.mime, sha256: item.sha }, item.createKey, signal)
    item.id = response.data.id
  }
  signal.throwIfAborted()
  // 幂等创建回执可能是旧状态，恢复时始终查询服务端当前分片。
  const { data: session } = await api.getDocumentUpload(item.id, signal)
  signal.throwIfAborted()
  if (session.purpose !== item.purpose || String(session.byteSize) !== String(item.file.size))
    throw new Error('上传会话与当前文件不一致，请重新选择文件')
  if (!['created', 'uploading', 'verifying', 'ready'].includes(session.state))
    throw new Error('上传会话已失效，请重新选择文件')
  if (session.state === 'ready') { progress('已校验', 100); return item.id }
  const partSize = Number(session.partSize), count = session.partCount
  if (!Number.isSafeInteger(partSize) || partSize <= 0 || count !== Math.ceil(item.file.size / partSize)
      || !Array.isArray(session.receivedParts) || session.receivedParts.some(n => !Number.isInteger(n) || n < 1 || n > count))
    throw new Error('上传分片协议无效')
  const received = new Set(session.receivedParts)
  for (let part = 1; part <= count; part++) {
    signal.throwIfAborted()
    if (!received.has(part)) {
      const start = (part - 1) * partSize, blob = item.file.slice(start, start + partSize)
      await api.putDocumentPart(item.id, part, blob, start, item.file.size, await hash(blob, signal), signal)
    }
    progress('上传中', Math.floor(part * 100 / count))
  }
  signal.throwIfAborted()
  progress('服务端校验', 100)
  const response = await api.completeDocumentUpload(item.id, item.sha, item.completeKey, signal)
  signal.throwIfAborted()
  if (response.data.state !== 'ready') throw new Error('服务端尚未确认文件校验完成，请重试')
  progress('已校验', 100)
  return item.id
}
