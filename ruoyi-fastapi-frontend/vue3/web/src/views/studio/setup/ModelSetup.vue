<script setup>
import { computed, watch, ref } from 'vue'
import TestEvidence from './TestEvidence.vue'
import TestProgress from './TestProgress.vue'
import { modelPriceSources } from '@/utils/modelPriceSources'
import { useModelSetup } from '@/composables/studio/useModelSetup'
import useSettingsStore from '@/store/modules/settings'
const emit = defineEmits(['advanced', 'busy'])
const settings = useSettingsStore()
const testRuntimeReady = ref(false)
const testEvidence = ref()
const props = defineProps({ initialConnection: { type: String, default: '' }, initialModel: { type: String, default: '' } })
const state = useModelSetup(props)
const { step, pending, error, progress, uncertain, loaded, connectionSaved, missing, connections, accounts, credentials, sources, centers,
  modelVersions, platformEnabled, selection, form, connection, account, credentialVersion,
  modelVersion, modelName, isVideo, videoPreset, test, enabled, priceReady, priceSaved, changePriceVersion, next, back, retry, startTest, refreshTest, changeConnection, changeAccount } = state
watch(() => pending.value || uncertain.value, value => emit('busy', value), { immediate: true })
const titles = ['连接供应商', '确认模型与价格', '测试并启用到全平台']
const testText = computed(() => test.value?.state === 'passed' ? '测试通过' :
  test.value?.state === 'pending' ? (test.value.progress?.stage === 'archiving' || test.value.progress?.stage === 'archive_retry' ? '视频已生成，正在保存结果' : '正在执行生成测试，请等待结果') : test.value ? '测试未通过，需要核查' : '尚未测试')
const readyToEnable = computed(() => enabled.value || (test.value?.state === 'passed' && test.value?.result?.modelVerified))
const availableSources = computed(() => modelPriceSources(sources.value, modelVersion.value?.gatewayAlias || modelName.value))
const source = computed(() => availableSources.value.find(row => row.id === selection.source))
const videoPrices = computed(() => form.videoPrices)
const buttons = computed(() => ['保存连接并继续', enabled.value ? '保存价格并生效' : '保存价格并继续', platformEnabled.value ? '已启用到全平台' : '启用到全平台'][step.value])
const preparingRetest = ref(false)
function prepareTest(retest = false) {
  if (pending.value || uncertain.value || test.value?.state === 'pending') return
  preparingRetest.value = retest
  testEvidence.value?.prepare()
}
async function submitPreparedTest() {
  if (pending.value || uncertain.value || test.value?.state === 'pending') return
  await (preparingRetest.value ? state.retest() : startTest())
}
const beginTest = () => prepareTest(false)
const confirmRetest = () => prepareTest(true)
</script>

<template>
  <div class="app-container setup-page">
    <header class="setup-heading">
      <div><h2>配置 {{ modelName }}</h2><p>复用供应商配置，确认这个模型的能力、价格和启用状态。</p></div>
      <div class="setup-actions">

        <el-button v-if="enabled && step !== 2" :disabled="pending || uncertain" @click="step = 2">生成测试</el-button>
        <el-button text @click="settings.toggleTheme()">切换主题</el-button>
      </div>
    </header>
    <el-alert v-if="missing.length" type="warning" :closable="false" show-icon
      :title="`当前账号还缺少：${missing.join('、')}`"
      description="请由系统管理员补齐对应权限后重新登录。已保存配置不会丢失。" />
    <el-steps :active="platformEnabled ? 3 : step" finish-status="success" align-center class="setup-steps">
      <el-step v-for="title in titles" :key="title" :title="title" />
    </el-steps>
    <section class="setup-body" v-loading="pending" :element-loading-text="progress || '正在读取配置'">
      <h3>{{ titles[step] }}</h3>
      <el-form label-position="top" :disabled="pending || uncertain || missing.length > 0 || (step === 0 && connectionSaved)" @submit.prevent>
        <template v-if="step === 0">
          <el-form-item label="供应商连接">
            <el-select v-model="selection.connection" @change="changeConnection" placeholder="选择已有连接或新建" filterable>
              <el-option label="＋ 新建供应商连接" value="" />
              <el-option v-for="row in connections" :key="row.id" :value="row.id" :label="`${row.name} · ${row.environment === 'test' ? '测试' : '正式'}`" />
            </el-select>
          </el-form-item>
          <template v-if="!selection.connection">
            <div class="setup-grid">
              <el-form-item label="连接名称"><el-input v-model="form.name" maxlength="200" /></el-form-item>
              <el-form-item label="使用环境"><el-radio-group v-model="form.environment"><el-radio value="test">测试</el-radio><el-radio value="production">正式</el-radio></el-radio-group></el-form-item>
            </div>
            <el-form-item label="供应商 API 基础地址"><el-input v-model="form.baseUrl" placeholder="http://llm-gw.videoplus.cc/" /></el-form-item>
            <p class="setup-hint">已预填 VideoPlus MM 的地址、业务标识和超时。测试环境也可能产生供应商费用。</p>
          </template>
          <p v-else class="setup-note">复用已有连接：{{ connection?.currentVersion?.baseUrl }}。不会改动其地址和超时。</p>
          <el-form-item v-if="selection.connection" label="采购账号">
            <el-select v-model="selection.account" @change="changeAccount" filterable placeholder="选择已有账号或登记">
              <el-option label="＋ 登记采购账号" value="" />
              <el-option v-for="row in accounts" :key="row.id" :value="row.id" :label="`${row.accountCode} · ${row.region}`" />
            </el-select>
          </el-form-item>
          <div v-if="!selection.account" class="setup-grid">
            <el-form-item label="采购账号名称"><el-input v-model="form.accountCode" maxlength="100" /></el-form-item>
            <el-form-item label="供应商侧项目标识"><el-input v-model="form.upstreamProject" placeholder="供应商提供的项目标识" maxlength="100" /></el-form-item>
            <el-form-item label="区域标识"><el-input v-model="form.region" placeholder="default" maxlength="32" /></el-form-item>
          </div>
          <el-form-item v-if="credentials.length" label="API 密钥">
            <el-select v-model="selection.credential" filterable>
              <el-option v-for="row in credentials" :key="row.id" :value="row.id" :label="`${row.name} · 已保存`" />
              <el-option label="＋ 登记新密钥" value="" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="!selection.credential" label="API Key">
            <el-input v-model="form.apiKey" type="password" show-password autocomplete="new-password" placeholder="粘贴供应商密钥，不含 Bearer 前缀" />
          </el-form-item>
          <p class="setup-hint">保存后密钥不回显；已有密钥无需重新输入。责任人自动记录为当前管理员。</p>
        </template>

        <template v-else-if="step === 1">
          <div class="setup-model"><strong>{{ modelName }}</strong><span>{{ modelName === 'mm-h3' ? '视频生成 · 支持首尾帧或参考素材模式' : isVideo ? '视频生成 · 支持普通参考图、虚拟人物与参考视频' : '图片生成与编辑 · 底层 gpt-image-2' }}</span></div>
          <p v-if="!modelVersions.length" class="setup-note">确认价格后自动保存模型参数配置，无需填写版本号。</p>
          <el-form-item v-else label="模型能力版本">
            <el-select v-model="selection.version" @change="changePriceVersion" placeholder="选择现有版本">
              <el-option v-for="row in modelVersions" :key="row.id" :value="row.id" :label="`第 ${row.versionNo} 版 · ${row.region} · ${row.status === 'published' ? '已发布' : row.status === 'verified' ? '已验证' : '待验证'}`" />
            </el-select>
          </el-form-item>
          <p class="setup-note">{{ modelName === 'mm-h3' ? '支持 2K、4～15 秒，每次生成一个视频，按实际秒数与输入图片数量结算。' : isVideo ? `支持 ${videoPreset.resolutions.join(' / ')}，4～15 秒或自动时长，每次生成一个视频。按分辨率及是否输入视频匹配价格，人民币基准价除以填写的汇率后按实际输出 Token 结算。` : '保留比例＋1K / 2K / 4K、画质和图片数量。规格及版本关联由系统处理。' }}</p>
          <el-form-item v-if="videoPrices.length" label="换算汇率（1 USD = 多少 CNY）">
            <el-input v-model="form.exchangeRate" inputmode="decimal" placeholder="例如 6.69" aria-label="美元兑人民币汇率" />
          </el-form-item>
          <p v-if="videoPrices.length" class="setup-hint">下方价格可直接修改，单位为人民币 / 百万输出 Token，系统按上方汇率换算为美元结算。</p>
          <el-table v-if="videoPrices.length" :data="videoPrices">
            <el-table-column prop="resolution" label="分辨率" />
            <el-table-column label="含参考视频（CNY / 百万输出 Token）"><template #default="{ row }"><el-input v-model="row.withVideo" inputmode="decimal" :aria-label="`${row.resolution} 含参考视频价格`" /></template></el-table-column>
            <el-table-column label="无参考视频（CNY / 百万输出 Token）"><template #default="{ row }"><el-input v-model="row.withoutVideo" inputmode="decimal" :aria-label="`${row.resolution} 无参考视频价格`" /></template></el-table-column>
          </el-table>
          <div v-if="modelName === 'mm-h3'" class="setup-grid">
            <el-form-item label="视频合计单价（USD / 秒）"><el-input v-model="form.secondPrice" inputmode="decimal" /></el-form-item>
            <el-form-item label="超过前 5 张的图片单价（USD / 张）"><el-input v-model="form.extraImagePrice" inputmode="decimal" /></el-form-item>
          </div>
          <div v-if="!isVideo" class="setup-grid">
            <el-form-item label="输入单价（USD / 百万 Token）"><el-input v-model="form.inputPrice" /></el-form-item>
            <el-form-item label="输出单价（USD / 百万 Token）"><el-input v-model="form.outputPrice" /></el-form-item>
          </div>
          <p class="setup-hint">项目与采购同价，分别记录 USD；不配置预算、不预占。未启用的模型先保存价格草稿；已启用的模型保存后立即同步生效，无需重新付费测试。历史费用与已提交任务仍用原价格。</p>
          <el-form-item v-if="!isVideo" label="供应商价格依据">
            <el-select v-model="selection.source" filterable :disabled="priceReady" placeholder="选择当前模型的价格依据">
              <el-option label="填写新的确认依据" value="" />
              <el-option v-for="row in availableSources" :key="row.id" :value="row.id" :label="row.label" />
            </el-select>
          </el-form-item>
          <p v-if="!isVideo && source" class="setup-evidence">{{ source.description }}</p>
          <el-input v-else-if="!isVideo" v-model="form.priceEvidence" :disabled="priceReady" type="textarea" :rows="4" placeholder="填写供应商确认价格的依据" />
        </template>

        <template v-else-if="step === 2">
          <div class="test-overview">
            <div><span class="test-eyebrow">{{ isVideo ? '视频模型' : '图片模型' }}</span><h2>{{ modelName }}</h2><p>{{ account?.accountCode }} · USD 按实际用量计费</p></div>
            <el-tag :type="platformEnabled || enabled ? 'success' : 'info'" effect="plain">{{ platformEnabled ? '全平台已启用' : enabled ? '模型已就绪' : '待验证' }}</el-tag>
          </div>
          <TestEvidence ref="testEvidence" hide-entry :submission-error="error" :submitting="pending" :submission-uncertain="uncertain" @start="submitPreparedTest" :test-id="test?.id || ''" :kind="isVideo ? 'video' : 'image'"
            :credential-version-id="credentialVersion?.id || ''" :model-version-id="modelVersion?.id || ''"
            :cost-center-id="selection.center" @ready="testRuntimeReady = $event" />
          <section class="test-workspace">
            <div class="test-section-heading"><h4>生成测试 <span v-if="enabled" class="optional-label">可选</span></h4><span class="service-status" :class="{ ready: testRuntimeReady }"><i></i>{{ testRuntimeReady ? '测试服务就绪' : '测试服务暂未就绪' }}</span></div>
            <p class="test-description">{{ enabled ? '需要验证生成效果或费用记录时，可发起一次新测试。' : '先完成一次生成测试，再启用模型。' }}点击后先预览请求。</p>
            <div v-if="test && test.state !== 'pending'" class="last-test"><span>最近一次测试</span><el-tag size="small" :type="test.state === 'passed' ? 'success' : 'warning'" effect="plain">{{ test.state === 'passed' ? '通过' : '未通过' }}</el-tag><span v-if="test.state === 'failed'">请从模型列表的“测试记录”查看原因。</span></div>
            <TestProgress v-if="test?.state === 'pending'" :message="test.progress?.message || '正在执行生成测试…'" />
            <div class="test-controls">
              <el-form-item label="测试费用归属"><el-select v-model="selection.center" :disabled="test?.state === 'pending'" placeholder="选择费用归属"><el-option v-for="row in centers" :key="row.id" :value="row.id" :label="row.name" /></el-select></el-form-item>
              <el-button v-if="test?.state !== 'pending'" :type="enabled ? 'default' : 'primary'" :disabled="!testRuntimeReady || !selection.center || pending || uncertain" @click="test ? confirmRetest() : beginTest()">{{ test ? '再测试一次' : '生成测试' }}</el-button>
              <el-button v-if="test" text :disabled="pending" @click="refreshTest">刷新状态</el-button>
            </div>
          </section>
          <p class="activation-note">{{ platformEnabled ? '现有和新建项目均可使用，项目权限保持不变。' : readyToEnable ? '模型已具备启用条件，可直接完成全平台启用。' : '测试通过后，下方启用按钮将可用。' }}</p>
        </template>
      </el-form>
      <p v-if="priceSaved" class="saved-note">✓ 价格已保存并同步生效</p>
      <el-alert v-if="error" class="setup-error" :title="error" type="error" :closable="false" show-icon />
      <el-button v-if="error && !uncertain && !missing.length" :loading="pending" @click="retry">重试当前步骤</el-button>
      <div v-if="uncertain" class="setup-retry">
        <p>有一步尚未确认成功。已完成的步骤保留，确认原请求不会重新创建付费测试。</p>
        <el-button :loading="pending" @click="retry">确认原请求并继续</el-button>
      </div>
      <footer class="setup-footer">
        <el-button v-if="step > 0 && !platformEnabled" :disabled="pending || uncertain" @click="back">上一步</el-button>
        <el-button type="primary" :loading="pending" :disabled="platformEnabled || !loaded || uncertain || missing.length > 0 || (step === 2 && !readyToEnable)" @click="next">{{ buttons }}</el-button>
      </footer>
    </section>
    <p class="setup-bottom">已登记的供应商、密钥、价格和测试记录会复用。需要调整历史配置时，返回模型列表，打开该模型的“更多操作”。</p>
  </div>
</template>

<style scoped>
.test-overview { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding-bottom: 24px; border-bottom: 1px solid var(--el-border-color-lighter); }
.test-eyebrow { font-size: 12px; color: var(--el-text-color-secondary); }
.test-overview h2 { margin: 8px 0; font-size: 24px; font-weight: 600; }
.test-overview p, .test-description { color: var(--el-text-color-secondary); font-size: 14px; line-height: 1.7; margin: 0; }
.test-workspace { padding: 24px 0 8px; }
.test-section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; }
.test-section-heading h4 { margin: 0; font-size: 16px; }
.optional-label { margin-left: 8px; font-size: 12px; font-weight: 400; color: var(--el-text-color-secondary); }
.service-status { display: inline-flex; align-items: center; gap: 6px; color: var(--el-text-color-secondary); font-size: 12px; }
.service-status i { width: 6px; height: 6px; border-radius: 50%; background: var(--el-text-color-placeholder); }
.service-status.ready i { background: var(--el-color-success); }
.last-test { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 16px; font-size: 13px; color: var(--el-text-color-secondary); }
.test-controls { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 12px; margin-top: 24px; }
.test-controls .el-form-item { width: 260px; max-width: 100%; margin-bottom: 0; }
.test-controls .el-button + .el-button { margin-left: 0; }
.activation-note, .saved-note { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; margin: 20px 0 0; }

.setup-page { color: var(--el-text-color-primary); max-width: 1080px; margin: 0 auto; }
.setup-heading, .setup-actions, .setup-footer { display: flex; align-items: center; gap: 12px; }
.setup-heading { justify-content: space-between; flex-wrap: wrap; margin-bottom: 24px; }
.setup-heading h2 { margin: 0 0 8px; font-size: 24px; }
.setup-heading p, .setup-hint, .setup-bottom { color: var(--el-text-color-secondary); line-height: 1.7; }
.setup-steps { margin: 24px 0 32px; }
.setup-body { background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 28px; }
.setup-body h3 { margin-top: 0; margin-bottom: 24px; }
.setup-body :deep(.el-select) { width: 100%; }
.setup-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 24px; }
.setup-model { display: flex; flex-direction: column; gap: 8px; background: var(--el-fill-color-light); padding: 20px; border-radius: 8px; margin-bottom: 24px; }
.setup-model strong { font-size: 20px; }
.setup-model span { color: var(--el-text-color-secondary); }
.setup-note, .setup-evidence { padding: 16px; background: var(--el-fill-color-light); border-radius: 8px; line-height: 1.8; overflow-wrap: anywhere; }
.setup-evidence { white-space: pre-wrap; max-height: 260px; overflow: auto; }
.setup-footer { border-top: 1px solid var(--el-border-color-light); padding-top: 20px; margin-top: 28px; justify-content: flex-end; }
.setup-error, .setup-retry, .project-selector { margin-top: 20px; }
.setup-body :deep(.el-alert) { margin-bottom: 18px; }
.setup-bottom { text-align: center; font-size: 13px; }
@media (max-width: 700px) { .setup-grid { grid-template-columns: 1fr; } .setup-body { padding: 18px; } .setup-steps :deep(.el-step__title) { font-size: 13px; } }
</style>
