import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, ref, reactive, watch, effectScope } from 'vue'
import { randomUUID } from 'node:crypto'
import { appendSetupRoute, setupPriceItems, sameSetupPrice, activeSetupPrice, setupRows } from '../../src/utils/modelSetup.js'
import { findVideoModel, sdCapabilities, editedVideoItems } from '../../src/utils/videoModels.js'

test('按项目追加开放模型保留其他模型、候选和原优先级，重复执行无新增', () => {
  const before = { revision: '3', routes: [{ modelId: '4', accountId: '5', enabled: false, priority: 8,
    credentials: [{ credentialId: '9', priority: 7, maxConcurrency: 3 }] },
  { modelId: '8', accountId: '6', enabled: true, priority: 1, credentials: [] }] }
  const after = appendSetupRoute(before, '4', '5', '10')
  assert.equal(before.routes[0].enabled, false)
  assert.equal(after.routes[0].priority, 8)
  assert.deepEqual(after.routes[0].credentials[0], before.routes[0].credentials[0])
  assert.deepEqual(after.routes[1], before.routes[1])
  assert.deepEqual(appendSetupRoute(after, '4', '5', '10'), after)
})

test('精确匹配两套Token单价，不能将细微价格差异当成已配置', () => {
  const items = setupPriceItems('5', '30')
  assert.equal(sameSetupPrice({ items: items.map(row => ({ ...row, unitPrice: row.unitPrice + '.0000000000' })) }, items), true)
  assert.equal(sameSetupPrice({ items: [{ ...items[0], unitPrice: '5.0000000001' }, items[1]] }, items), false)
  assert.throws(() => setupPriceItems('0', '30'))
  assert.throws(() => setupPriceItems('5', 'NaN'))
})

test('生效区间取最新事件，已结束或未来生效不算当前生效', () => {
  const now = Date.parse('2026-11-02T00:00:00Z')
  const activation = { id: '1', effectiveFrom: '2026-10-01T00:00:00Z', effectiveUntil: null }
  assert.equal(activeSetupPrice([{ diff: { after: activation } }], now), true)
  assert.equal(activeSetupPrice([{ diff: { after: { ...activation, effectiveUntil: '2026-11-01T00:00:00Z' } } },
    { diff: { after: activation } }], now), false)
})

test('读取所有分页，不把后页已有配置判断为缺失', async () => {
  const pages = []
  const result = await setupRows(async query => {
    pages.push(query.pageNum)
    return { rows: [query.pageNum], total: 2, hasNext: query.pageNum < 2 }
  })
  assert.deepEqual(result, [1, 2]); assert.deepEqual(pages, [1, 2])
})

async function harness({ existing = false, failTest = false, fresh = false, options = {}, noVersions = false, video = false } = {}) {
  const hooks = {}, writes = [], timers = []
  const user = reactive({ id: 101, token: 'session-a', permissions: ['*:*:*'] })
  const db = {
    connection: { id: '1', name: 'VideoPlus MM', status: 'active', environment: 'test', currentVersion: { id: '11', baseUrl: 'http://llm-gw.videoplus.cc/' } },
    account: { id: '2', connectionId: '1', accountCode: 'main', region: 'default', status: 'active' },
    credential: { id: '3', name: '已存密钥', accountId: '2', status: 'active' },
    credentialVersion: { id: '31', state: existing ? 'active' : 'draft', versionNo: 1, revision: '1', connectionVersionId: '11', validFrom: '2026-01-01T00:00:00Z', validUntil: null },
    model: { id: '4', connectionId: '1', code: 'mm-imagen2', displayName: 'mm-imagen2', kind: 'image' },
    version: { id: '41', modelId: '4', region: 'default', gatewayAlias: 'mm-imagen2', status: existing ? 'published' : 'draft', versionNo: 1, revision: '2', capabilities: { variantDimensions: {} } },
    variant: { id: '42', dimensions: {} },
    sources: [{ id: '6', excerpt: 'mm-imagen2 供应商确认价格' }], books: [], prices: [], tests: [], routes: { revision: '2', routes: [] },
  }
  const page = values => ({ rows: values, total: values.length, hasNext: false })
  if (video) {
    const preset = findVideoModel('mm-eva-sd-2.5')
    db.model = { ...db.model, code: preset.code, displayName: preset.name, kind: 'video' }
    db.version = { ...db.version, gatewayAlias: preset.alias, capabilities: sdCapabilities(preset) }
    options = { ...options, initialModel: db.model.id }
  }
  const videoVariants = []
  const present = { connection: !fresh, account: !fresh, credential: !fresh, model: !fresh, version: !fresh && !noVersions, variant: !fresh }
  const api = {
    listProviderConnections: async () => page(present.connection ? [db.connection] : []), getProviderConnection: async () => ({ data: db.connection }),
    listProviderAccounts: async () => page(present.account ? [db.account] : []), listCredentials: async () => page(present.credential ? [db.credential] : []),
    listCredentialVersions: async () => page([db.credentialVersion]), listModels: async () => page(present.model ? [db.model] : []),
    listModelVersions: async () => page(present.version ? [db.version] : []), getModelVersion: async () => ({ data: db.version }),
    listModelVariants: async () => page(video ? videoVariants : present.variant ? [db.variant] : []), listPriceSources: async () => page(fresh ? [] : db.sources),
    listTestCostCenters: async () => page([{ id: '7', name: '管理员测试', active: true }]),
    listPriceBooks: async query => page(db.books.filter(row => row.purpose === query.purpose && (!video || row.modelVariantId === query.modelVariantId))),
    listPriceVersions: async query => page(db.prices.filter(row => row.priceBookId === query.priceBookId).toReversed()),
    listPriceHistory: async () => page([{ diff: { after: { id: 'h1', effectiveFrom: '2026-01-01T00:00:00Z', effectiveUntil: null } } }]),
    listCredentialTests: async () => page(db.tests), getCredentialTest: async id => ({ data: db.tests.find(row => row.id === id) }),
    listGovernedProjects: async () => page([{ id: '8', name: '测试项目', status: 'active' }]),
    getPlatformRouting: async () => ({ data: db.routes }),
  }
  const write = (name, handler) => async (...args) => { writes.push({ name, args }); return { data: await handler(...args) } }
  api.saveProviderConnection = write('connection', () => { present.connection = true; return db.connection })
  api.createProviderAccount = write('account', () => { present.account = true; return db.account })
  api.saveCredential = write('credential', () => { present.credential = true; return db.credential })
  api.createModelProfile = write('model', () => { present.model = true; return db.model })
  api.createModelVersion = write('modelVersion', () => { present.version = true; return db.version })
  api.createModelVariant = write('variant', (_id, data) => {
    if (video) { const row = { id: String(100 + videoVariants.length), dimensions: data.dimensions }; videoVariants.push(row); return row }
    present.variant = true; db.version = { ...db.version, revision: '3' }; return db.variant
  })
  api.createPriceSource = write('source', data => ({ ...data, id: '6' }))
  api.createPriceBook = write('book', data => { const row = { ...data, id: String(db.books.length + 10) }; db.books.push(row); return row })
  api.createPriceVersion = write('price', data => { const row = { ...data, id: String(db.prices.length + 20), revision: '1', status: 'draft' }; db.prices.push(row); return row })
  api.publishPrice = write('publishPrice', id => {
    if (db.version.status !== 'published') throw Object.assign(new Error('价格发布要求对应模型能力已发布'), { errorCode: 'PRICE_MODEL_NOT_PUBLISHED' })
    db.prices.find(row => row.id === id).status = 'published'; return { id }
  })
  api.publishModelPrices = write('batchPrices', async data => { for (const item of data.items) if (db.prices.find(row => row.id === item.versionId).status !== 'published') await api.publishPrice(item.versionId); return {} })
  const testKeys = new Set()
  api.createCredentialTest = write('test', (_id, data, key) => {
    if (!testKeys.has(key)) {
      testKeys.add(key); db.tests.push({ id: '50', state: 'pending', modelVersionId: data.modelVersionId,
        credentialVersionId: '31', connectionVersionId: '11', configHash: 'a'.repeat(64), result: {} })
      if (failTest) throw new Error('模拟响应中断')
    }
    return { id: '50', state: 'pending' }
  })
  api.changeCredentialState = write('activateCredential', () => { db.credentialVersion = { ...db.credentialVersion, state: 'active', revision: '2' }; return db.credentialVersion })
  api.changeModelVersionState = write('modelState', (_id, action) => {
    db.version = { ...db.version, status: action === 'verify' ? 'verified' : 'published', revision: String(Number(db.version.revision) + 1) }
    return db.version
  })
  api.savePlatformRouting = write('routing', (data) => { db.routes = data; return data })
  if (existing) for (const [index, purpose] of ['procurement', 'platform'].entries()) {
    db.books.push({ id: String(10 + index), purpose }); db.prices.push({ id: String(20 + index), priceBookId: String(10 + index),
      status: 'published', items: setupPriceItems('5', '30'), sourceIds: ['6'], revision: '1' })
  }
  const context = createContext({ structuredClone, URL, Date, crypto: { randomUUID },
    setTimeout: fn => { timers.push(fn); return timers.length }, clearTimeout() {},
    window: { addEventListener() {}, removeEventListener() {} } })
  const vue = { computed, ref, reactive, watch, onMounted: fn => { hooks.mount = fn },
    onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
  const mocks = { vue, 'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user }, '@/api/studio/modelSetup': api }
  const modules = {}
  for (const [key, file] of [['@/utils/modelPriceSources', 'modelPriceSources'], ['@/utils/modelSetup', 'modelSetup'], ['@/utils/mmImagen2', 'mmImagen2'], ['@/utils/videoModels', 'videoModels']]) {
    modules[key] = new SourceTextModule(await readFile(new URL(`../../src/utils/${file}.js`, import.meta.url), 'utf8'), { context })
    await modules[key].link(() => {}); await modules[key].evaluate()
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useModelSetup.js', import.meta.url), 'utf8'), { context })
  await module.link(name => modules[name] || new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useModelSetup(options))
  hooks.mount(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.error.value, '')
  return { state, db, writes, user, hooks, close() { hooks.unmount(); scope.stop() } }
}

test('已有配置一路复用，启用全平台默认模型，无重复价格或付费测试', async () => {
  const h = await harness({ existing: true })
  await h.state.next(); assert.equal(h.state.step.value, 1)
  await h.state.next(); assert.equal(h.state.step.value, 2)
  await h.state.next(); assert.equal(h.state.platformEnabled.value, true, h.state.error.value)
  assert.deepEqual(h.writes.map(row => row.name), ['routing'])
  assert.equal(h.state.step.value, 2)
  h.close()
})

test('缺少价格时补两套价格，测试响应中断以同一请求恢复，再启用到全平台', async () => {
  const h = await harness({ failTest: true })
  await h.state.next(); await h.state.next()
  assert.equal(h.state.step.value, 2, h.state.error.value)
  assert.equal(h.writes.filter(row => row.name === 'price').length, 2)
  assert.equal(h.writes.filter(row => row.name === 'publishPrice').length, 0)
  await h.state.startTest(); assert.equal(h.state.uncertain.value, true)
  assert.equal(h.hooks.leave(), false)
  await h.state.retry()
  const attempts = h.writes.filter(row => row.name === 'test')
  assert.equal(attempts.length, 2); assert.equal(attempts[0].args[2], attempts[1].args[2])
  assert.equal(h.db.tests.length, 1)
  h.db.tests[0] = { ...h.db.tests[0], state: 'passed', result: { modelVerified: true } }
  await h.state.refreshTest(); await h.state.next()
  assert.equal(h.state.platformEnabled.value, true, h.state.error.value)
  assert.deepEqual(h.writes.filter(row => ['activateCredential', 'modelState'].includes(row.name)).map(row => row.name), ['activateCredential', 'modelState', 'modelState'])
  assert.equal(h.writes.filter(row => row.name === 'publishPrice').length, 2)
  const modelPublished = h.writes.findIndex(row => row.name === 'modelState' && row.args[1] === 'publish')
  assert.ok(h.writes.findIndex(row => row.name === 'publishPrice') > modelPublished)
  h.close()
})

test('撤销权限后不保留密钥输入，不继续写入', async () => {
  const h = await harness()
  h.state.form.apiKey = 'secret-only-in-memory'
  h.user.permissions = []
  assert.equal(h.state.form.apiKey, '')
  await h.state.next(); assert.equal(h.writes.length, 0)
  h.close()
})

test('首次接入自动建立关联、清空密钥，并使用新增规格后的最新模型修订', async () => {
  const h = await harness({ fresh: true })
  Object.assign(h.state.form, { upstreamProject: 'vendor-project', apiKey: 'fixture-key-only' })
  await h.state.next()
  assert.equal(h.state.step.value, 1, h.state.error.value)
  assert.equal(h.state.form.apiKey, '')
  assert.deepEqual(h.writes.map(row => row.name), ['connection', 'account', 'credential', 'model', 'modelVersion'])
  const secretWrite = h.writes.find(row => row.name === 'credential')
  assert.equal(secretWrite.args[1].ownerId, '101')
  assert.equal(secretWrite.args[1].connectionVersionId, '11')
  await h.state.next()
  assert.equal(h.state.step.value, 2, h.state.error.value)
  assert.equal(h.state.modelVersion.value.revision, '3')
  assert.equal(h.writes.filter(row => row.name === 'source').length, 1)
  h.close()
})


test('从已有模型列表直达模型配置，只读复用供应商，绝不自动测试或写入', async () => {
  const h = await harness({ existing: true, options: { initialConnection: '1', initialModel: '4' } })
  assert.equal(h.state.step.value, 1, h.state.error.value)
  assert.equal(h.state.connectionSaved.value, true)
  assert.equal(h.writes.length, 0)
  h.close()
})


test('简化供应商表单仅保存连接账号密钥，不创建模型价格或付费测试', async () => {
  const h = await harness({ fresh: true, options: { supplierOnly: true } })
  Object.assign(h.state.form, { upstreamProject: 'op', apiKey: 'fixture-key-only' })
  await h.state.next()
  assert.equal(h.state.connectionSaved.value, true, h.state.error.value)
  assert.deepEqual(h.writes.map(row => row.name), ['connection', 'account', 'credential'])
  assert.equal(h.state.form.apiKey, '')
  h.close()
})

test('新登记模型直达价格配置，只有点击确认才创建能力预设，不自动付费测试', async () => {
  const h = await harness({ noVersions: true, options: { initialConnection: '1', initialModel: '4' } })
  assert.equal(h.state.step.value, 1, h.state.error.value)
  assert.equal(h.writes.length, 0)
  await h.state.next()
  assert.equal(h.state.step.value, 2, h.state.error.value)
  assert.equal(h.writes.filter(row => row.name === 'modelVersion').length, 1)
  assert.equal(h.writes.filter(row => row.name === 'test').length, 0)
  h.close()
})

test('视频六种计价规格分别保存双账价格，经手动测试后统一启用，不改供应商密钥', async () => {
  const h = await harness({ video: true })
  assert.equal(h.state.step.value, 1)
  await h.state.next()
  assert.equal(h.state.error.value, '')
  assert.equal(h.writes.filter(row => row.name === 'variant').length, 6)
  assert.equal(h.db.prices.length, 12)
  assert.equal(h.writes.filter(row => row.name === 'test').length, 0)
  await h.state.startTest()
  h.db.tests[0] = { ...h.db.tests[0], state: 'passed', result: { modelVerified: true } }
  await h.state.refreshTest(); await h.state.next()
  assert.equal(h.state.platformEnabled.value, true, h.state.error.value)
  assert.equal(h.writes.filter(row => row.name === 'publishPrice').length, 12)
  assert.equal(h.writes.filter(row => row.name === 'credential' || row.name === 'connection').length, 0)
  assert.equal(h.writes.filter(row => row.name === 'test').length, 1)
  const original = JSON.stringify(h.db.prices)
  h.state.back()
  h.state.form.exchangeRate = '7.123456'
  h.state.form.videoPrices[0].withVideo = '43.1234567890'
  await h.state.next()
  assert.equal(h.state.error.value, '')
  assert.equal(h.state.priceSaved.value, true)
  assert.equal(JSON.stringify(h.db.prices.slice(0, 12)), original)
  assert.equal(h.writes.filter(row => row.name === 'test').length, 1)
  const changed = h.db.prices.slice(12)
  assert.equal(changed.length, 12)
  assert.ok(changed.every(row => row.items[0].unitQuantity === '7123456'))
  assert.equal(changed.filter(row => row.items[0].unitPrice === '43.1234567890').length, 2)
  await h.state.changePriceVersion()
  assert.equal(h.state.form.exchangeRate, '7.123456')
  assert.equal(h.state.form.videoPrices[0].withVideo, '43.1234567890')
  h.close()
})

test('非法汇率或价格在任何写入之前提示，不创建价格和付费任务', async () => {
  const h = await harness({ video: true })
  h.state.form.exchangeRate = '0'
  await h.state.next()
  assert.ok(h.state.error.value)
  assert.equal(h.writes.length, 0)
  h.state.form.exchangeRate = '6.69'
  h.state.form.videoPrices[0].withVideo = '-1'
  await h.state.next()
  assert.ok(h.state.error.value)
  assert.equal(h.writes.length, 0)
  h.close()
})

test('SD 换算不先舍入美元单价，H3 独立更新秒价和图片价', () => {
  const sd = editedVideoItems('mm-eva-sd-2.5', { resolution: '720p', has_video_input: true }, {
    exchangeRate: '6.69', videoPrices: [{ resolution: '720p', withVideo: '42', withoutVideo: '70' }] })
  assert.equal(sd[0].unitQuantity, '6690000')
  assert.equal(sd[0].unitPrice, '42')
  const h3 = editedVideoItems('mm-h3', {}, { secondPrice: '0.15', extraImagePrice: '0.06' })
  assert.equal(h3.find(row => row.itemCode === 'output_seconds').unitPrice, '0.15')
  assert.equal(h3.find(row => row.itemCode === 'input_images' && row.quantityFrom === '5').unitPrice, '0.06')
})

test('已通过模型可手动再测一次，执行中不能重复提交', async () => {
  const h = await harness({ existing: true })
  await h.state.next()
  h.state.test.value = { id: 'previous', state: 'passed', result: { modelVerified: true } }
  await h.state.retest()
  assert.equal(h.writes.filter(row => row.name === 'test').length, 1, h.state.error.value)
  h.state.test.value = { ...h.state.test.value, state: 'pending' }
  await h.state.retest()
  assert.equal(h.writes.filter(row => row.name === 'test').length, 1)
  h.close()
})
