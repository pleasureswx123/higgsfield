import assert from 'node:assert/strict'
import test from 'node:test'
import { File } from 'node:buffer'
import { readFile } from 'node:fs/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { documentUploadItem, documentHash, uploadDocument, DOCUMENT_MAX_BYTES } from '../../src/utils/documentUpload.js'

function fixture() {
  const item = documentUploadItem(new File(['name,price\na,1\n'], '价格.csv'))
  const stored = new Set(), calls = [], progress = []
  let fail = true
  const api = {
    async createDocumentUpload(data, key) { calls.push(['create', data, key]); return { data: { id: '9' } } },
    async getDocumentUpload() { return { data: { purpose: 'price_source', state: 'uploading',
      byteSize: String(item.file.size), partSize: '5', partCount: Math.ceil(item.file.size / 5), receivedParts: [...stored] } } },
    async putDocumentPart(id, part, blob, start, total, sha) {
      assert.equal(sha, await documentHash(blob, new AbortController().signal))
      assert.equal(start, (part - 1) * 5)
      assert.equal(total, item.file.size)
      calls.push(['part', part])
      stored.add(part)
      if (part === 2 && fail) { fail = false; throw Error('已存分片但响应丢失') }
    },
    async completeDocumentUpload(id, sha, key) { calls.push(['complete', key]); return { data: { state: 'ready' } } },
  }
  return { item, api, calls, progress, signal: new AbortController().signal }
}

test('实际 SHA-256、类型与容量边界', async () => {
  const signal = new AbortController().signal
  assert.equal(await documentHash(new Blob(['abc']), signal), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  for (const file of [new File([''], 'a.csv'), new File(['x'], 'a.pdf'), { name: 'a.txt', size: DOCUMENT_MAX_BYTES + 1 }])
    assert.throws(() => documentUploadItem(file))
  for (const [name, mime] of [['a.PNG', 'image/png'], ['a.jpeg', 'image/jpeg'], ['a.webp', 'image/webp']])
    assert.equal(documentUploadItem(new File(['example'], name)).mime, mime)
  assert.equal(documentUploadItem(new File(['x'], 'a.xlsx'), 'reconciliation').purpose, 'reconciliation')
  assert.throws(() => documentUploadItem(new File(['x'], 'a.csv'), 'unknown'))
})

test('对账上传使用独立用途，不接受价格证据会话', async () => {
  const item = documentUploadItem(new File(['key,USD,1'], 'bill.csv'), 'reconciliation')
  const api = {
    async createDocumentUpload(data) { assert.equal(data.purpose, 'reconciliation'); return { data: { id: '123' } } },
    async getDocumentUpload() { return { data: { purpose: 'price_source', state: 'ready', byteSize: String(item.file.size) } } },
  }
  await assert.rejects(uploadDocument(item, api, new AbortController().signal, () => {}), /不一致/)
})

test('响应丢失后重读服务端分片，不重建会话或重传已保存内容', async () => {
  const { item, api, calls, signal } = fixture()
  const key = item.createKey
  await assert.rejects(uploadDocument(item, api, signal, () => {}), /响应丢失/)
  assert.equal(await uploadDocument(item, api, signal, () => {}), '9')
  assert.equal(calls.filter(c => c[0] === 'create').length, 1)
  assert.equal(calls.find(c => c[0] === 'create')[2], key)
  assert.deepEqual(calls.filter(c => c[0] === 'part').map(c => c[1]), [1, 2, 3])
})

test('完成响应丢失后读取 ready，不重复发完成请求', async () => {
  const { item, api, signal } = fixture()
  item.id = '9'
  let state = 'verifying', complete = 0
  api.getDocumentUpload = async () => ({ data: { purpose: 'price_source', state, byteSize: String(item.file.size),
    partSize: '5', partCount: 3, receivedParts: [1, 2, 3] } })
  api.completeDocumentUpload = async () => { complete++; state = 'ready'; throw Error('断网') }
  await assert.rejects(uploadDocument(item, api, signal, () => {}), /断网/)
  assert.equal(await uploadDocument(item, api, signal, () => {}), '9')
  assert.equal(complete, 1)
})

test('取消、用途不匹配和失效会话均不继续发分片', async () => {
  const { item, api, calls } = fixture()
  item.id = '9'
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(uploadDocument(item, api, controller.signal, () => {}))
  for (const changes of [{ purpose: 'reconciliation', state: 'ready' }, { purpose: 'price_source', state: 'failed' }]) {
    api.getDocumentUpload = async () => ({ data: { ...changes, byteSize: String(item.file.size) } })
    await assert.rejects(uploadDocument(item, api, new AbortController().signal, () => {}))
  }
  assert.equal(calls.length, 0)
})

test('分片请求保留二进制、摘要和范围，不走 JSON 加密封装', async () => {
  const calls = [], context = createContext({ encodeURIComponent })
  const module = new SourceTextModule(await readFile(new URL('../../src/api/studio/documentUploads.js', import.meta.url), 'utf8'), { context })
  await module.link(() => new SyntheticModule(['default'], function () {
    this.setExport('default', config => { calls.push(config); return Promise.resolve({}) })
  }, { context }))
  await module.evaluate()
  const blob = new Blob(['test']), signal = new AbortController().signal
  await module.namespace.putDocumentPart('123', 2, blob, 4, 8, 'digest', signal)
  assert.equal(calls[0].data, blob)
  assert.equal(calls[0].headers.encrypt, false)
  assert.equal(calls[0].headers['Content-Range'], 'bytes 4-7/8')
  assert.equal(calls[0].headers['X-Content-SHA256'], 'digest')
  assert.equal(calls[0].headers['Content-Type'], 'application/octet-stream')
  assert.equal(calls[0].signal, signal)
})
