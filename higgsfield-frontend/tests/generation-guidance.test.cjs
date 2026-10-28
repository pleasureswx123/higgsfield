const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const { renderToString } = require('vue/server-renderer')
const { parse, compileScript } = require('vue/compiler-sfc')
function compile(source, imports) {
  const exports = {}
  runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
    { exports, require: name => imports[name] })
  return exports
}
const helper = compile(readFileSync(join(__dirname, '../src/utils/generationGuidance.ts'), 'utf8'), {})
const filename = join(__dirname, '../src/components/projects/GenerationGuidance.vue')
const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
const component = compile(compileScript(descriptor, { id: 'guidance', inlineTemplate: true }).content,
  { vue, '@/utils/generationGuidance': helper }).default
const render = changes => renderToString(vue.createSSRApp(component, { detail: {
  orchestrationState: 'finished', upstreamState: 'succeeded', cancelState: 'none',
  outputsVisibility: 'visible', outputs: [], archiveSummary: { total: 1, ready: 1, failed: 0, pending: 0 }, ...changes,
} }))

test('提交未知优先说明核查，不把编排阻塞当作确认失败，不渲染内部错误', async () => {
  const html = await render({ orchestrationState: 'blocked', upstreamState: 'unknown', internalError: 'secret-token' })
  assert.match(html, /无法确认供应商是否已受理/)
  assert.match(html, /不要重复生成/)
  assert.doesNotMatch(html, /secret-token|生成失败|任务处理受阻/)
})
test('生成失败与归档失败同时存在时分开说明，不将失败或取消当作免费', async () => {
  const failed = await render({ upstreamState: 'failed', archiveSummary: { total: 2, ready: 1, failed: 1, pending: 0 } })
  assert.match(failed, /未提供可核实的具体失败原因/)
  assert.match(failed, /失败不等于免费/)
  assert.match(failed, /不重新提交模型生成/)
  assert.match(failed, /不按下载成功数量折算/)
  const cancelled = await render({ upstreamState: 'cancelled', cancelState: 'confirmed' })
  assert.match(cancelled, /不将取消自动视为免费/)
})
test('过期输出引导恢复原任务，无媒体权限时不读取隐藏输出细节', async () => {
  const task = { outputs: [{ archiveState: 'source_expired' }], archiveSummary: { total: 1, failed: 1 } }
  assert.match(await render(task), /原任务结果是否可以恢复/)
  assert.doesNotMatch(await render({ ...task, outputsVisibility: 'hidden' }), /部分结果链接已过期/)
})
test('上游成功但归档未完成不宣称长期可用；全部就绪不显示异常提示', async () => {
  assert.match(await render({ archiveSummary: { total: 2, ready: 1, pending: 1, failed: 0 } }), /长期归档是两个独立状态/)
  assert.doesNotMatch(await render({}), /任务状态说明|归档尚未完成/)
  assert.match(await render({ orchestrationState: 'running', upstreamState: 'running' }), /刷新不会重新生成/)
})

test('已记录原因按阶段展示并转义，保留费用说明且不再声称没有原因', async () => {
  const html = await render({ upstreamState: 'failed', diagnostic: {
    code: 'SUBMISSION_AUTH_REJECTED', phase: 'submit', message: '拒绝 <script>secret</script>',
  } })
  assert.match(html, /已记录原因 · 提交阶段/)
  assert.match(html, /SUBMISSION_AUTH_REJECTED/)
  assert.match(html, /&lt;script&gt;secret&lt;\/script&gt;/)
  assert.doesNotMatch(html, /<script>|未提供可核实的具体失败原因/)
  assert.match(html, /不代表费用已结算/)
  const preparing = await render({ orchestrationState: 'preparing', upstreamState: 'not_submitted', diagnostic: {
    code: 'PROVIDER_CREDENTIAL_UNAVAILABLE', phase: 'prepare', message: '固定凭据当前不可用',
  } })
  assert.match(preparing, /已记录原因 · 准备阶段/)
  assert.doesNotMatch(preparing, /已记录原因 · 查询阶段/)
})
