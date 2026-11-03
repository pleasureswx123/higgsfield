import { computed, ref, reactive, onMounted, onActivated, onDeactivated, onBeforeUnmount, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import * as api from '@/api/studio/modelSetup'
import { modelPriceSources } from '@/utils/modelPriceSources'
import { mmImagen2Capabilities } from '@/utils/mmImagen2'
import { findVideoModel, sdCapabilities, sdPriceItems, editedVideoItems } from '@/utils/videoModels'
import { setupRows, setupPriceItems, sameSetupPrice, activeSetupPrice, activeSetupActivation, appendSetupRoute } from '@/utils/modelSetup'

/** 接入步骤复用已有接口；任何写入结果不明都保留原请求，绝不自动再申请测试。 */
export function useModelSetup(options = {}) {
  const user = useUserStore()
  const required = {
    'provider:read': '查看供应商', 'provider:write': '配置供应商',
    'credential:read': '查看密钥', 'credential:write': '保存密钥',
    'credential:test': '测试连接', 'credential:activate': '启用密钥',
    'model:read': '查看模型', 'model:write': '配置模型', 'model:verify': '验证模型', 'model:publish': '启用模型',
    'billing:price:read': '查看价格', 'billing:price:write': '配置价格', 'billing:price:publish': '启用价格',
    'provider:route': '配置全平台模型',
  }
  if (options.supplierOnly) {
    for (const key of Object.keys(required)) if (!['provider:read', 'provider:write', 'credential:read', 'credential:write'].includes(key)) delete required[key]
  }
  const missing = computed(() => user.permissions.includes('*:*:*') ? [] :
    Object.entries(required).filter(([key]) => !user.permissions.includes(key)).map(([, label]) => label))
  const step = ref(0), pending = ref(false), error = ref(''), progress = ref(''), uncertain = ref(false)
  const loaded = ref(false), connectionSaved = ref(false)
  const connections = ref([]), accounts = ref([]), credentials = ref([]), sources = ref([]), centers = ref([])
  const modelVersions = ref([]), platformEnabled = ref(false)
  const connection = ref(), account = ref(), credential = ref(), credentialVersion = ref()
  const model = ref(), modelVersion = ref(), variant = ref(), test = ref(), priceReady = ref(false)
  const videoPreset = computed(() => findVideoModel(model.value?.code))
  const modelName = computed(() => videoPreset.value?.alias || model.value?.displayName || 'mm-imagen2')
  const isVideo = computed(() => model.value?.kind === 'video')
  let pricingVariants = [], editorModel = null
  const priceSaved = ref(false)
  const selection = reactive({ connection: options.initialConnection || '', account: '', credential: '', version: '', source: '', center: '' })
  const form = reactive({ name: 'VideoPlus MM', baseUrl: 'http://llm-gw.videoplus.cc/', environment: 'test',
    accountCode: 'videoplus-mm-main', region: 'default', upstreamProject: '', apiKey: '',
    exchangeRate: '6.69', videoPrices: [], secondPrice: '0.13', extraImagePrice: '0.04', inputPrice: '5', outputPrice: '30', priceEvidence: '供应商确认 mm-imagen2 按实际输入、输出 Token 计费。输入 5 USD/百万 Token，输出 30 USD/百万 Token；按张计价常量不适用。' })
  let active = true, session = user.token, timer, lastAction
  const attempts = new Map()
  let pendingPrices = []
  const check = () => {
    if (!active || session !== user.token || missing.value.length) throw new Error('登录状态或权限已变化，请重新进入接入页面')
  }
  async function read(action) { check(); const result = await action(); check(); return result }
  const rows = (loader, params) => setupRows(query => read(() => loader(query)), params)
  async function write(label, invoke, payload) {
    check()
    let attempt = attempts.get(label)
    if (!attempt) {
      attempt = { key: crypto.randomUUID(), payload: structuredClone(payload), invoke }
      attempts.set(label, attempt)
    }
    if (attempt.done) return attempt.result
    progress.value = label.split(/\s[\[{]/)[0]
    // 失败后保留同一个载荷和幂等键；后续步骤不会执行。
    uncertain.value = true
    let response
    try { response = await attempt.invoke(attempt.payload, attempt.key) }
    catch (cause) {
      // 明确的模型发布前置校验失败不是网络结果未知，不锁定用户重复确认。
      if (cause?.errorCode === 'PRICE_MODEL_NOT_PUBLISHED') {
        attempts.delete(label)
        uncertain.value = false
      }
      throw cause
    }
    check()
    attempt.done = true
    attempt.result = response.data
    attempt.payload = undefined
    uncertain.value = false
    return response.data
  }
  async function run(action) {
    if (pending.value || !active || missing.value.length) return
    pending.value = true
    error.value = ''
    lastAction = action
    try { await action() }
    catch (cause) { if (active && session === user.token) error.value = cause?.message || '操作未完成，请核对后重试' }
    finally { pending.value = false; progress.value = '' }
  }
  const retry = () => run(lastAction)
  function stopPoll() { clearTimeout(timer); timer = undefined }
  function clearRelated() {
    stopPoll()
    account.value = credential.value = credentialVersion.value = model.value = modelVersion.value = variant.value = test.value = undefined
    accounts.value = credentials.value = modelVersions.value = []
    selection.account = selection.credential = selection.version = ''
    priceReady.value = false
    pendingPrices = []
    platformEnabled.value = false
    attempts.clear()
    editorModel = null
  }
  async function loadCredentials() {
    credential.value = credentialVersion.value = undefined
    credentials.value = selection.account ? await rows(api.listCredentials, { accountId: selection.account }) : []
    credentials.value = credentials.value.filter(row => ['draft', 'active'].includes(row.status))
    selection.credential = credentials.value.length === 1 ? credentials.value[0].id : ''
  }
  async function loadConnection() {
    clearRelated()
    connection.value = selection.connection ? (await read(() => api.getProviderConnection(selection.connection))).data : undefined
    accounts.value = connection.value ? await rows(api.listProviderAccounts, { connectionId: connection.value.id }) : []
    accounts.value = accounts.value.filter(row => row.status === 'active')
    selection.account = accounts.value.length === 1 ? accounts.value[0].id : ''
    if (selection.account) await loadCredentials()
  }
  async function initialize() {
    if (missing.value.length) return
    connections.value = await rows(api.listProviderConnections)
    connections.value = connections.value.filter(row => row.status !== 'disabled')
    // 只有唯一候选才自动选中，多供应商时由管理员明确选择。
    if (!selection.connection && connections.value.length === 1) selection.connection = connections.value[0].id
    await loadConnection()
    if (options.supplierOnly) { loaded.value = true; return }
    sources.value = await rows(api.listPriceSources)
    const candidates = modelPriceSources(sources.value, modelVersion.value?.gatewayAlias || modelName.value)
    if (candidates.length === 1) selection.source = candidates[0].id
    centers.value = (await rows(api.listTestCostCenters)).filter(row => row.active)
    selection.center = centers.value.find(row => row.code === 'admin_test' || row.name === '管理员测试')?.id ||
      (centers.value.length === 1 ? centers.value[0].id : '')
    loaded.value = true
    // 从模型列表进入已配置模型时，只读取现有绑定，跳过重复填写供应商。
    if (options.initialModel && selection.account && selection.credential) await saveConnection(false)
  }
  const changeConnection = () => {
    if (!pending.value && !uncertain.value) return run(loadConnection)
  }
  const changeAccount = () => {
    if (!pending.value && !uncertain.value) return run(async () => { attempts.clear(); await loadCredentials() })
  }
  const validCredential = row => ['draft', 'active'].includes(row.state)
    && row.connectionVersionId === connection.value.currentVersion.id
    && Date.parse(row.validFrom) <= Date.now() && (!row.validUntil || Date.parse(row.validUntil) > Date.now())
  async function loadModel(createMissing = true) {
    const models = await rows(api.listModels, { connectionId: connection.value.id })
    model.value = models.find(row => options.initialModel ? row.id === options.initialModel : row.code === 'mm-imagen2')
    if (options.initialModel && (!model.value || (model.value.code !== 'mm-imagen2' && !videoPreset.value)))
      throw new Error('此模型尚未接入当前配置流程，请返回模型列表查看接入详情')
    if (!model.value) model.value = await write('登记图片模型', api.createModelProfile, {
      connectionId: connection.value.id, code: 'mm-imagen2', displayName: 'mm-imagen2', kind: 'image',
    })
    modelVersions.value = (await rows(query => api.listModelVersions(model.value.id, query)))
      .filter(row => row.region === account.value.region && row.gatewayAlias === (videoPreset.value?.alias || 'mm-imagen2') && row.status !== 'disabled')
    if (!modelVersions.value.length && createMissing) {
      const version = await write('配置模型能力', (data, key) => api.createModelVersion(model.value.id, data, key), {
        region: account.value.region, gatewayAlias: videoPreset.value?.alias || 'mm-imagen2', underlyingModelId: isVideo.value ? null : 'gpt-image-2',
        schemaVersion: 1, capabilities: isVideo.value ? sdCapabilities(videoPreset.value) : mmImagen2Capabilities(),
      })
      modelVersions.value = [version]
    }
    if (!modelVersions.value.some(row => row.id === selection.version))
      selection.version = modelVersions.value.length === 1 ? modelVersions.value[0].id : ''
    if (editorModel !== model.value.id) { editorModel = model.value.id; await loadPriceEditor() }
  }
  async function loadPriceEditor() {
    form.videoPrices = videoPreset.value && modelName.value !== 'mm-h3' ? videoPreset.value.resolutions.map(resolution => ({ resolution,
      withVideo: sdPriceItems(modelName.value, resolution, true)[0].unitPrice,
      withoutVideo: sdPriceItems(modelName.value, resolution, false)[0].unitPrice })) : []
    form.exchangeRate = '6.69'; priceSaved.value = false
    if (!selection.version) return
    modelVersion.value = (await read(() => api.getModelVersion(selection.version))).data
    const variants = await rows(query => api.listModelVariants(selection.version, query))
    let rate
    for (const item of variants) {
      const books = await rows(api.listPriceBooks, { modelVariantId: item.id, purpose: 'platform', currency: 'USD' })
      if (!books.length) continue
      const versions = await rows(api.listPriceVersions, { priceBookId: books[0].id })
      let selected
      for (const version of versions.filter(row => row.status === 'published')) {
        if (activeSetupPrice(await rows(query => api.listPriceHistory(version.id, query)))) { selected = version; break }
      }
      selected ||= versions.find(row => row.status === 'draft')
      if (!selected) continue
      const rules = selected.items
      if (!isVideo.value) {
        for (const [code, field] of [['input', 'inputPrice'], ['output', 'outputPrice']]) {
          const rule = rules.find(row => row.itemCode === code)
          if (rule) form[field] = String(Number(rule.unitPrice) * 1000000 / Number(rule.unitQuantity))
        }
      } else if (modelName.value === 'mm-h3') {
        form.secondPrice = rules.find(row => row.itemCode === 'output_seconds')?.unitPrice || '0.13'
        form.extraImagePrice = rules.find(row => row.itemCode === 'input_images' && Number(row.quantityFrom) === 5)?.unitPrice || '0.04'
      } else {
        const rule = rules.find(row => row.itemCode === 'video_tokens')
        const target = form.videoPrices.find(row => row.resolution === item.dimensions.resolution)
        if (!rule || !target) throw new Error('已有价格格式无法在此编辑，请核查价格配置')
        const nextRate = String(Number(rule.unitQuantity) / 1000000)
        if (rate && rate !== nextRate) throw new Error('现有规格使用不同汇率，请先核查价格配置')
        rate = nextRate; form.exchangeRate = rate
        target[item.dimensions.has_video_input ? 'withVideo' : 'withoutVideo'] = rule.unitPrice
      }
    }
  }
  const changePriceVersion = () => run(loadPriceEditor)
  async function saveConnection(createMissing = true) {
    if (!selection.credential && !/^[\x21-\x7e]{8,4096}$/.test(form.apiKey))
      throw new Error('请输入完整 API Key，不带 Bearer 前缀和空格')
    if (!selection.account && (!form.upstreamProject.trim() || !form.accountCode.trim() || !/^[a-z][a-z0-9_-]*$/.test(form.region)))
      throw new Error('请填写采购账号、供应商项目标识和有效区域')
    if (!selection.connection) {
      if (!form.name.trim() || !form.upstreamProject.trim() || !form.accountCode.trim())
        throw new Error('请填写连接名称、采购账号和供应商项目标识')
      if (!/^[a-z][a-z0-9_-]*$/.test(form.region)) throw new Error('区域标识需以小写字母开头')
      const url = new URL(form.baseUrl)
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash)
        throw new Error('请填写不含密钥、查询参数的 HTTP/HTTPS 基础地址')
      connection.value = await write('保存供应商连接', (data, key) => api.saveProviderConnection(null, data, key), {
        name: form.name.trim(), environment: form.environment, baseUrl: form.baseUrl, adapterVersion: 'videoplus-v1',
        config: { allowedHosts: [url.hostname], bizId: 'op', connectTimeoutSeconds: 15,
          readTimeoutSeconds: 180, operationTimeoutSeconds: 240, taskTimeoutSeconds: 3600 },
      })
      selection.connection = connection.value.id
      if (!connections.value.some(row => row.id === connection.value.id)) connections.value.push(connection.value)
    }
    if (!selection.account) {
      if (!form.upstreamProject.trim() || !form.accountCode.trim()) throw new Error('请填写采购账号和供应商项目标识')
      account.value = await write('保存采购账号', api.createProviderAccount, { connectionId: connection.value.id,
        accountCode: form.accountCode.trim(), region: form.region, upstreamProject: form.upstreamProject.trim() })
      selection.account = account.value.id
      if (!accounts.value.some(row => row.id === account.value.id)) accounts.value.push(account.value)
    } else account.value = accounts.value.find(row => row.id === selection.account) || account.value
    if (!account.value) throw new Error('请选择供应商账号')
    if (!selection.credential) {
      if (!/^[\x21-\x7e]{8,4096}$/.test(form.apiKey)) throw new Error('请输入完整 API Key，不带 Bearer 前缀和空格')
      credential.value = await write('保存 API 密钥', (data, key) => api.saveCredential(null, data, key), {
        accountId: account.value.id, ownerId: String(user.id), name: `${account.value.accountCode} 图片密钥`,
        connectionVersionId: connection.value.currentVersion.id, apiKey: form.apiKey,
        validFrom: new Date().toISOString(), validUntil: null,
      })
      selection.credential = credential.value.id
      if (!credentials.value.some(row => row.id === credential.value.id)) credentials.value.push(credential.value)
      form.apiKey = ''
    } else credential.value = credentials.value.find(row => row.id === selection.credential) || credential.value
    const versions = await rows(query => api.listCredentialVersions(credential.value.id, query))
    credentialVersion.value = versions.filter(validCredential).sort((a, b) => b.versionNo - a.versionNo)[0]
    if (!credentialVersion.value) throw new Error('该密钥已到期或未绑定当前连接，请在高级管理中轮换密钥')
    if (options.supplierOnly) { connectionSaved.value = true; return }
    await loadModel(createMissing)
    if (modelVersion.value) await loadTests()
    connectionSaved.value = true
    step.value = 1
  }
  async function selectModelVersion() {
    modelVersion.value = (await read(() => api.getModelVersion(selection.version))).data
    if (!isVideo.value && Object.keys(modelVersion.value.capabilities.variantDimensions || {}).length)
      throw new Error('此版本包含自定义规格，请使用高级管理，助手不会覆盖现有能力')
    const variants = await rows(query => api.listModelVariants(modelVersion.value.id, query))
    pricingVariants = []
    const dimensions = isVideo.value && modelName.value !== 'mm-h3' ? videoPreset.value.resolutions.flatMap(resolution => [false, true].map(has_video_input => ({ resolution, has_video_input }))) : [{}]
    for (const entry of dimensions) {
      let saved = variants.find(row => Object.keys(row.dimensions).length === Object.keys(entry).length && Object.entries(entry).every(([key, value]) => row.dimensions[key] === value))
      if (!saved) saved = await write(`保存模型规格 ${modelVersion.value.id} ${JSON.stringify(entry)}`,
        (data, key) => api.createModelVariant(modelVersion.value.id, data, key), { dimensions: entry })
      pricingVariants.push(saved)
    }
    variant.value = pricingVariants[0]
    modelVersion.value = (await read(() => api.getModelVersion(modelVersion.value.id))).data
  }
  async function savePrices() {
    if (!selection.version && !modelVersions.value.length) await loadModel()
    if (!selection.version) throw new Error('请选择要接入的模型版本')
    const imageItems = isVideo.value ? null : setupPriceItems(form.inputPrice.trim(), form.outputPrice.trim())
    if (isVideo.value) { selection.source = ''; form.priceEvidence = modelName.value === 'mm-h3' ? '供应商确认 H3：输出与参考视频合计每秒 0.13 USD，输入图片前五张免费，超过五张每张 0.04 USD。' : `${modelName.value}：按完成后的 completion_tokens 计费；人民币基准价按 1 USD = 6.69 CNY 换算，分辨率和实际视频输入分别计价。` }
    if (!selection.source && !form.priceEvidence.trim()) throw new Error('请填写供应商价格确认依据')
    if (isVideo.value) {
      if (modelName.value === 'mm-h3') editedVideoItems(modelName.value, {}, form)
      else for (const row of form.videoPrices) for (const has_video_input of [false, true]) editedVideoItems(modelName.value, { resolution: row.resolution, has_video_input }, form)
      form.priceEvidence = JSON.stringify({ model: modelName.value, exchangeRate: form.exchangeRate, prices: form.videoPrices, secondPrice: form.secondPrice, extraImagePrice: form.extraImagePrice })
    }
    await selectModelVersion()
    pendingPrices = []
    for (const selectedVariant of pricingVariants) {
    variant.value = selectedVariant
    const items = isVideo.value ? editedVideoItems(modelName.value, selectedVariant.dimensions, form) : imageItems
    // 只新增价格版本；旧正文保持不变，最后原子切换两套生效区间。
    const plans = []
    for (const purpose of ['procurement', 'platform']) {
      const books = await rows(api.listPriceBooks, { modelVariantId: variant.value.id, purpose, currency: 'USD',
        ...(purpose === 'procurement' ? { accountId: account.value.id } : {}) })
      const book = books[0]
      const versions = book ? await rows(api.listPriceVersions, { priceBookId: book.id }) : []
      let chosen, oldActivation, current = false
      for (const version of versions) {
        if (version.status === 'published') {
          const history = await rows(query => api.listPriceHistory(version.id, query))
          const activation = activeSetupActivation(history)
          if (activation) {
            oldActivation = activation
            if (sameSetupPrice(version, items)) { chosen = version; current = true }
            break
          }
        }
      }
      if (!chosen) chosen = versions.find(row => row.status === 'draft' && sameSetupPrice(row, items) && row.sourceIds.length)
      plans.push({ purpose, book, version: chosen, current, oldActivation })
    }
    let sourceId = selection.source
    if (plans.some(plan => !plan.current && !plan.version) && !sourceId) {
      const savedSource = await write(`登记价格依据 ${form.priceEvidence}`,  api.createPriceSource, { sourceType: 'manual_confirmation',
        sourceUrl: null, excerpt: form.priceEvidence.trim(), observedAt: new Date().toISOString() })
      sourceId = savedSource.id
      if (!sources.value.some(row => row.id === sourceId)) sources.value.unshift(savedSource)
      selection.source = sourceId
    }
    for (const plan of plans) {
      if (plan.current) { pendingPrices.push({ version: plan.version, oldActivation: plan.oldActivation, current: true }); continue }
      const name = `${plan.purpose === 'procurement' ? '采购' : '平台'} ${variant.value.id}`
      let book = plan.book
      if (!book) book = await write(`保存${name}价格簿`, api.createPriceBook, { modelVariantId: variant.value.id,
        purpose: plan.purpose, accountId: plan.purpose === 'procurement' ? account.value.id : null,
        currency: 'USD', name: `${modelName.value}${name}价USD` })
      let version = plan.version
      if (!version) version = await write(`保存${name}价格 ${JSON.stringify(items)}`, api.createPriceVersion, { priceBookId: book.id,
        roundingMode: 'half_up', calculationScale: 10, items, sourceIds: [sourceId] })
      // 后端要求模型先发布；此处只保存草稿，测试启用后再发布价格。
      pendingPrices.push({ name, version, oldActivation: plan.oldActivation })
    }
    }
    priceReady.value = true
    if (enabled.value) { await publishPrices(); priceSaved.value = true }
    await loadTests()
    step.value = 2
  }
  async function loadTests() {
    stopPoll()
    const history = await rows(query => api.listCredentialTests(credentialVersion.value.id, query))
    test.value = history.find(row => row.modelVersionId === modelVersion.value.id &&
      row.connectionVersionId === connection.value.currentVersion.id)
    schedulePoll()
  }
  function schedulePoll() {
    stopPoll()
    if (active && test.value?.state === 'pending') timer = setTimeout(refreshTest, 4000)
  }
  async function refreshTest() {
    if (!test.value || pending.value || !active) { schedulePoll(); return }
    try { test.value = (await read(() => api.getCredentialTest(test.value.id))).data; error.value = '' }
    catch (cause) { if (active) error.value = cause?.message || '暂时无法读取测试结果，正在自动重试'; schedulePoll(); return }
    schedulePoll()
  }
  async function requestTest(retest = false) {
    if (test.value && !(retest && ['passed', 'failed'].includes(test.value.state))) throw new Error('已存在此模型的测试记录，请先核查原记录；不会重复发起付费测试')
    if (!selection.center) throw new Error('请选择测试费用归属')
    const label = retest ? `重新测试模型（原记录 ${test.value.id}）` : '申请模型生成测试'
    const result = await write(label, (data, key) => api.createCredentialTest(credentialVersion.value.id, data, key), {
      modelVersionId: modelVersion.value.id, costCenterId: selection.center, acknowledgePotentialCharge: true,
    })
    test.value = (await read(() => api.getCredentialTest(result.id))).data
    schedulePoll()
  }
  const enabled = computed(() => credentialVersion.value?.state === 'active' && modelVersion.value?.status === 'published')
  async function publishPrices() {
    if (!pendingPrices.length) return
    if (pendingPrices.every(row => row.current)) { pendingPrices = []; return }
    const items = pendingPrices.map(({version, oldActivation}) => ({ versionId: version.id, revision: version.revision, expectedActivationId: oldActivation?.id || null }))
    await write(`同步发布价格 ${JSON.stringify(items)}`, api.publishModelPrices, { items, reason: '管理员在模型配置页确认价格和换算汇率，项目与采购同价' })
    pendingPrices = []
    // 本轮发布已确认；再次编辑（包括恢复旧数值）必须建立新的价格版本。
    for (const label of attempts.keys()) if (/^保存(采购|平台).*价格 |^同步发布价格 /.test(label)) attempts.delete(label)
  }
  async function activate() {
    if (!enabled.value) {
      if (test.value?.state !== 'passed' || !test.value.result?.modelVerified)
        throw new Error('请先等待模型生成测试通过')
      if (credentialVersion.value.state === 'draft') {
        await write('启用已测试密钥', (data, key) => api.changeCredentialState(credentialVersion.value.id, 'activate', data, key), {
          revision: credentialVersion.value.revision, testId: test.value.id,
          expectedConfigHash: test.value.configHash, reason: '模型接入助手：模型生成测试通过',
        })
        credentialVersion.value = (await rows(query => api.listCredentialVersions(credential.value.id, query)))
          .find(row => row.id === credentialVersion.value.id)
      }
      if (modelVersion.value.status === 'draft') {
        await write('登记模型测试证据', (data, key) => api.changeModelVersionState(modelVersion.value.id, 'verify', data, key), {
          revision: modelVersion.value.revision, verificationRef: `供应商凭据测试记录 ${test.value.id}：模型生成成功`,
          reason: '模型接入助手：管理员确认已通过的模型测试',
        })
        modelVersion.value = (await read(() => api.getModelVersion(modelVersion.value.id))).data
      }
      if (modelVersion.value.status === 'verified') {
        await write('启用模型', (data, key) => api.changeModelVersionState(modelVersion.value.id, 'publish', data, key), {
          revision: modelVersion.value.revision, reason: '模型接入助手：测试通过，启用模型',
        })
        modelVersion.value = (await read(() => api.getModelVersion(modelVersion.value.id))).data
      }
    }
    if (!enabled.value) throw new Error('模型或密钥尚未启用，请刷新配置核对')
    await publishPrices()
    const current = (await read(() => api.getPlatformRouting())).data
    const payload = appendSetupRoute(current, model.value.id, account.value.id, credential.value.id)
    const label = '启用全平台默认模型'
    if (JSON.stringify(payload.routes) !== JSON.stringify(current.routes) || (attempts.has(label) && !attempts.get(label).done))
      await write(label, api.savePlatformRouting, payload)
    platformEnabled.value = true
  }
  const next = () => run([saveConnection, savePrices, activate][step.value])
  const startTest = () => run(requestTest)
  const retest = () => run(() => requestTest(true))
  function back() {
    if (pending.value || uncertain.value) return
    step.value = Math.max(0, step.value - 1)
    priceReady.value = false
    priceSaved.value = false
  }
  function beforeUnload(event) {
    if (pending.value || uncertain.value) { event.preventDefault(); event.returnValue = '' }
  }
  function suspend() { active = false; stopPoll(); form.apiKey = ''; attempts.clear(); uncertain.value = false }
  onBeforeRouteLeave(() => !pending.value && !uncertain.value)
  onMounted(() => { window.addEventListener('beforeunload', beforeUnload); run(initialize) })
  onActivated(() => { if (!active) { active = true; session = user.token; step.value = 0; connectionSaved.value = loaded.value = false; platformEnabled.value = false; run(initialize) } })
  onDeactivated(suspend)
  onBeforeUnmount(() => { suspend(); window.removeEventListener('beforeunload', beforeUnload) })
  watch(() => [user.token, JSON.stringify(user.permissions)], () => {
    suspend(); connection.value = undefined; clearRelated(); sources.value = connections.value = []
    platformEnabled.value = false
    Object.keys(selection).forEach(key => { selection[key] = '' })
    step.value = 0
    loaded.value = connectionSaved.value = false
    error.value = '登录状态或权限已变化，请重新进入页面'
  }, { flush: 'sync' })
  return { step, pending, error, progress, uncertain, loaded, connectionSaved, missing, connections, accounts, credentials, sources, centers,
    modelVersions, platformEnabled, selection, form, connection, account, credentialVersion,
    modelVersion, modelName, isVideo, videoPreset, test, enabled, priceReady, priceSaved, changePriceVersion, next, back, retry, startTest, retest, refreshTest, changeConnection, changeAccount }
}
