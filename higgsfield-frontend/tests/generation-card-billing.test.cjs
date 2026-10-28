const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const path = require('node:path')
const ts = require('typescript')
const vue = require('vue')
const { renderToString } = require('vue/server-renderer')
const { parse, compileScript } = require('vue/compiler-sfc')
function evaluate(source, mocks = {}) {
  const exported = {}
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  runInNewContext(code, { exports: exported, require: name => mocks[name] })
  return exported
}
const billing = evaluate(readFileSync(path.join(__dirname, '../src/utils/billing.ts'), 'utf8'))
const file = path.join(__dirname, '../src/components/projects/GenerationCardBilling.vue')
const { descriptor } = parse(readFileSync(file, 'utf8'), { filename: file })
const component = evaluate(compileScript(descriptor, { id: 'card-billing', inlineTemplate: true }).content,
  { vue, '@/utils/billing': billing }).default
const render = task => renderToString(vue.createSSRApp(component, { task }))

test('卡片费用区分无权限、不可用、未知和精确零金额', async () => {
  const summary = { amount: '1234567890123456.1234567890', currency: 'CNY', state: 'calculated' }
  const hidden = await render({ billingVisibility: 'hidden', billingSummary: summary })
  assert.match(hidden, /无费用查看权限/)
  assert.doesNotMatch(hidden, /123456|CNY/)
  assert.match(await render({ billingVisibility: 'unavailable' }), /暂不可用/)
  const unknown = await render({ billingVisibility: 'visible', billingSummary: { ...summary, amount: null, state: 'pending' } })
  assert.match(unknown, /待确认/)
  assert.doesNotMatch(unknown, /CNY|0\.00/)
  const known = await render({ billingVisibility: 'visible', billingSummary: summary })
  assert.match(known, /1234567890123456\.123456789/)
  assert.match(known, /已计算/)
  assert.match(await render({ billingVisibility: 'visible', billingSummary: { ...summary, amount: '0.0000000000' } }), /0.*CNY/)
})
