import request from '@/utils/request'

const root = '/api/admin/v1/document-uploads'
export const createDocumentUpload = (data, key, signal) => request({
  url: root, method: 'post', data, signal,
  headers: { 'Idempotency-Key': key, repeatSubmit: false },
})
export const getDocumentUpload = (id, signal) => request({
  url: `${root}/${encodeURIComponent(id)}`, signal,
})
export const putDocumentPart = (id, part, data, start, total, sha, signal) => request({
  url: `${root}/${encodeURIComponent(id)}/parts/${part}`, method: 'put', data, signal,
  timeout: 120000,
  headers: { 'Content-Type': 'application/octet-stream', repeatSubmit: false, encrypt: false,
    'Content-Range': `bytes ${start}-${start + data.size - 1}/${total}`, 'X-Content-SHA256': sha },
})
export const completeDocumentUpload = (id, sha256, key, signal) => request({
  url: `${root}/${encodeURIComponent(id)}/complete`, method: 'post', data: { sha256 }, signal,
  timeout: 120000, headers: { 'Idempotency-Key': key, repeatSubmit: false },
})
