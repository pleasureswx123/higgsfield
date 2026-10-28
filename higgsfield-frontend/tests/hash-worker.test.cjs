const { test } = require('node:test')
const assert = require('node:assert/strict')
const { createHash } = require('node:crypto')
const { readFileSync } = require('node:fs')
const { pathToFileURL } = require('node:url')
const { Worker } = require('node:worker_threads')
const ts = require('typescript')

// 执行实际浏览器工作线程源码，仅适配消息入口；对照 Node 原生摘要。
test('分块摘要覆盖空文件、边界前后和跨多个分块', async () => {
  const source = readFileSync(
    new URL('../src/workers/hash.worker.ts', pathToFileURL(__filename)),
    'utf8',
  )
  const compiled = ts
    .transpileModule(source, {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
    })
    .outputText.replace(
      '@noble/hashes/sha2.js',
      pathToFileURL(require.resolve('@noble/hashes/sha2.js')).href,
    )
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
  for (const size of [0, 1, 4 * 1024 * 1024 - 1, 4 * 1024 * 1024, 8 * 1024 * 1024 + 17]) {
    const content = Buffer.alloc(size)
    for (let index = 0; index < size; index++) content[index] = index % 251
    const worker = new Worker(
      `
      const { parentPort } = require('node:worker_threads');
      global.self = { postMessage: value => parentPort.postMessage(value) };
      import(${JSON.stringify(moduleUrl)}).then(() => {
        parentPort.on('message', data => self.onmessage({ data }));
        parentPort.postMessage({ ready: true });
      });
    `,
      { eval: true },
    )
    try {
      const digest = await new Promise((resolve, reject) => {
        let last = 0
        worker.on('error', reject)
        worker.on('message', (message) => {
          if (message.ready) worker.postMessage(new Blob([content]))
          if (message.error) reject(new Error(message.error))
          if (message.progress !== undefined) {
            try {
              assert.ok(message.progress >= last && message.progress <= 1)
              last = message.progress
            } catch (error) {
              reject(error)
            }
          }
          if (message.digest) resolve(message.digest)
        })
      })
      assert.equal(digest, createHash('sha256').update(content).digest('hex'))
    } finally {
      await worker.terminate()
    }
  }
})
