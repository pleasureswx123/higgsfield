const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const path = require('node:path')
const ts = require('typescript')
const vue = require('vue')
const { renderToString } = require('vue/server-renderer')
const { parse, compileScript } = require('vue/compiler-sfc')

const file = path.join(__dirname, '../src/components/projects/GenerationOutputMetadata.vue')
const { descriptor } = parse(readFileSync(file, 'utf8'), { filename: file })
const compiled = compileScript(descriptor, { id: 'output-metadata', inlineTemplate: true }).content
const code = ts.transpileModule(compiled, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const exported = {}
runInNewContext(code, { exports: exported, require: name => {
  if (name === 'vue') return vue
  throw new Error(`不支持的运行时依赖：${name}`)
} })
const render = output => renderToString(vue.createSSRApp(exported.default, { output }))

test('作品工作状态与真实输出规格独立显示，精确时长及修订提示词安全渲染', async () => {
  const html = await render({ kind: 'video', workStatus: 'review', actualMetadata: {
    width: 1920, height: 1080, durationSeconds: '12.123456', format: 'mp4', revisedPrompt: '<script>供应商文本</script>',
  } })
  assert.match(html, /作品工作状态：待审核/)
  assert.match(html, /1920 px/)
  assert.match(html, /1080 px/)
  assert.match(html, /12\.123456 秒/)
  assert.match(html, /mp4/)
  assert.match(html, /&lt;script&gt;供应商文本&lt;\/script&gt;/)
  assert.doesNotMatch(html, /<script>/)
})

test('缺失规格不伪造零值或从参数推断，未知状态与未设置区分', async () => {
  const missing = await render({ kind: 'video', workStatus: 'future', actualMetadata: {}, parameters: { width: 2048 } })
  assert.match(missing, /状态未知/)
  assert.equal((missing.match(/未记录/g) || []).length, 4)
  assert.doesNotMatch(missing, /2048|0 px|0 秒|供应商修订提示词/)
  const text = await render({ kind: 'text', workStatus: 'none', actualMetadata: {} })
  assert.match(text, /作品工作状态：未设置/)
  assert.doesNotMatch(text, /实际宽度|实际时长/)
})
