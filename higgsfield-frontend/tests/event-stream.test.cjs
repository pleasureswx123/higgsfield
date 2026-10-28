const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const exported = {}
const source = readFileSync(require('node:path').join(__dirname, '../src/utils/eventStream.ts'), 'utf8')
runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, { exports: exported, TextDecoder })

test('逐字节分片保留中文与CRLF，忽略心跳并合并多行data', async () => {
  const bytes = new TextEncoder().encode(': heartbeat\r\n\r\nid: 9:9007199254740993\r\nevent: task.state\r\ndata: 中文\r\ndata: 第二行\r\n\r\ndata: 最后\n\n')
  const stream = new ReadableStream({ start(controller) { for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close() } })
  const events = []
  for await (const event of exported.parseEventStream(stream)) events.push(event)
  assert.equal(events.length, 2)
  assert.equal(events[0].data, '中文\n第二行')
  assert.equal(events[0].event, 'task.state')
  assert.equal(events[1].id, '9:9007199254740993')
})
test('没有空行的半个事件不提交，消费方退出取消读取', async () => {
  const encoder = new TextEncoder()
  const incomplete = new ReadableStream({ start(c) { c.enqueue(encoder.encode('data: partial')); c.close() } })
  const events = []
  for await (const event of exported.parseEventStream(incomplete)) events.push(event)
  assert.equal(events.length, 0)
  let cancelled = false
  const live = new ReadableStream({ start(c) { c.enqueue(encoder.encode('data: ready\n\n')) }, cancel() { cancelled = true } })
  for await (const event of exported.parseEventStream(live)) { assert.equal(event.data, 'ready'); break }
  assert.equal(cancelled, true)
})
