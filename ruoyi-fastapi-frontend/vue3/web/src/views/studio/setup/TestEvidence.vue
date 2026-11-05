<script setup>
import { computed, ref, reactive, watch } from 'vue'
import TestProgress from './TestProgress.vue'
import { useTestEvidence } from '@/composables/studio/useTestEvidence'
import { useTestCapacityRelease } from '@/composables/studio/useTestCapacityRelease'
const props = defineProps({ testId: { type: String, default: '' }, kind: { type: String, default: 'image' }, credentialVersionId: { type: String, default: '' }, modelVersionId: { type: String, default: '' }, costCenterId: { type: String, default: '' }, submissionError: { type: String, default: '' }, submitting: Boolean, submissionUncertain: Boolean, hideEntry: Boolean })
const emit = defineEmits(['ready', 'start'])
const preparing = ref(false)
const testId = computed(() => preparing.value ? '' : props.testId)
// 重新测试预览只读取新请求，不混入上一次测试的响应。
const evidenceProps = reactive({
  get testId() { return testId.value },
  get credentialVersionId() { return props.credentialVersionId },
  get modelVersionId() { return props.modelVersionId },
  get costCenterId() { return props.costCenterId },
})
watch(() => props.testId, (value, old) => { if (value && value !== old) preparing.value = false })
const { runtime, detail, preview, loading, error, copied, videoUrl, health, refresh, copy, loadVideo } = useTestEvidence(evidenceProps, emit)
const capacity = useTestCapacityRelease(() => testId.value, refresh)
const sections = ref(['request', 'response'])
const evidence = computed(() => testId.value ? detail.value : preview.value)
const waiting = computed(() => !!testId.value && (!detail.value || String(detail.value.testState) === '0'))
const hasResponse = computed(() => !!(detail.value?.submissionResponse || detail.value?.response))
watch(hasResponse, value => {
  if (value && !preparing.value && !sections.value.includes('response')) sections.value.push('response')
})
watch(testId, value => { if (value) sections.value = ['response'] })
const json = value => JSON.stringify(value, null, 2)
const poll = computed(() => testId.value ? detail.value?.pollRequest : preview.value?.pollPreview?.request)
const open = ref(false)
function show() { preparing.value = false; open.value = true; refresh() }
function prepare() { preparing.value = true; sections.value = ['request']; open.value = true; refresh() }
const canStart = computed(() => preparing.value && runtime.value?.ready && preview.value?.request && !loading.value && !error.value && !props.submitting && !props.submissionUncertain)
function start() { if (canStart.value) emit('start') }
defineExpose({ show, prepare })
</script>
<template>
  <section class="test-evidence">
    <el-alert v-if="!hideEntry" :title="runtime?.message || '正在确认测试服务状态…'" :type="runtime?.ready ? 'success' : 'info'" :closable="false" show-icon />
    <div v-if="!hideEntry && !runtime?.ready" class="evidence-entry"><el-button text @click="health">刷新服务状态</el-button></div>
    <el-drawer v-model="open" :title="preparing ? '确认测试内容 · 尚未提交' : '测试详情 · 请求与响应'" size="min(860px, 95vw)" append-to-body>
    <TestProgress v-if="submitting || (waiting && hasResponse && !error)" :message="submitting ? '正在提交测试…' : hasResponse ? '已收到响应，正在等待生成和保存完成…' : '正在等待供应商响应…'" />
    <el-alert v-else-if="testId && detail && !waiting && !error" :title="String(detail.testState) === '1' ? '测试已完成，结果已自动更新' : '测试未通过，请查看下方响应和诊断'" :type="String(detail.testState) === '1' ? 'success' : 'warning'" :closable="false" show-icon />
    <el-alert v-if="submissionError" :title="submissionError" type="error" :closable="false" />
    <section v-if="testId && detail?.capacityReviewRequired && !preparing">
      <el-alert title="结果未知，已暂停自动执行并保留供应商名额。请核查后释放；不要重新生成来确认结果。" type="warning" :closable="false" />
      <el-form v-if="capacity.allowed.value" label-position="top" :disabled="capacity.pending.value || capacity.uncertain.value">
        <el-form-item label="核查原因"><el-input v-model="capacity.form.reason" type="textarea" maxlength="4000" /></el-form-item>
        <el-form-item label="证据引用（如 ticket:123）"><el-input v-model="capacity.form.evidenceRef" maxlength="255" /></el-form-item>
        <el-checkbox v-model="capacity.form.acknowledgeSupplierStopped" class="supplier-confirmation">我已核实供应商任务停止或未运行，可以释放名额</el-checkbox>
      </el-form>
      <el-alert v-if="capacity.error.value" :title="capacity.error.value" type="error" :closable="false" />
      <el-button v-if="capacity.allowed.value" type="primary" :loading="capacity.pending.value" @click="capacity.submit">{{ capacity.uncertain.value ? '确认原释放请求' : '核查完成，释放名额' }}</el-button>
    </section>
    <div class="evidence-toolbar"><strong>{{ preparing ? '待发送请求' : '请求与响应' }}</strong><el-button text :loading="loading" @click="refresh">刷新</el-button><el-button v-if="!runtime?.ready" text @click="health">检查服务状态</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <p v-if="!testId && !costCenterId">请先选择下方的测试费用归属，即可查看待发送请求。</p>
    <el-collapse v-model="sections">
      <el-collapse-item name="request" :title="testId ? '1. 实际发送的请求 Request' : '1. 待发送的请求 Request（尚未调用供应商）'">

        <p v-if="testId">{{ detail?.requestSource === 'saved' ? '发送前保存的实际请求快照。' : detail?.requestSource === 'reconstructed_hash_verified' ? '历史请求重建后已核对摘要一致。' : '等待后台保存实际请求；不会用预览冒充已发送内容。' }}</p>
        <pre v-if="evidence?.request">{{ json(evidence.request) }}</pre>
        <details v-if="evidence?.curl"><summary>查看 / 复制 cURL</summary><el-button @click="copy(evidence.curl)">{{ copied ? '已复制' : '复制 cURL' }}</el-button>
          <p>密钥为占位符。查看和复制不收费；替换密钥后自行执行会再次生成并可能收费。</p><pre>{{ evidence.curl }}</pre>
        </details>
      </el-collapse-item>
      <el-collapse-item v-if="!preparing" name="response" :title="kind === 'video' ? '2. 创建视频任务的响应 Response' : '2. 供应商响应 Response'">
        <p v-if="!testId">尚未发送请求，暂无真实响应。</p>
        <template v-else>
          <TestProgress v-if="waiting && !hasResponse && !error" message="请求已提交，正在等待响应…" />
          <p v-else>HTTP：{{ detail?.pollRequest ? (detail?.submissionHttpStatus ?? '历史记录未保存') : (detail?.httpStatus ?? '尚无响应') }}</p>
          <p v-if="detail?.taskId">供应商任务 ID：{{ detail.taskId }}。创建成功后仍需等待视频生成完成。</p>
          <pre v-if="hasResponse || !waiting">{{ detail?.submissionResponse ? json(detail.submissionResponse) : detail?.response && !detail?.pollRequest ? json(detail.response) : '等待供应商创建响应；未收到时不会自动重发生成。' }}</pre>
        </template>
      </el-collapse-item>
      <el-collapse-item v-if="!preparing && kind === 'video'" name="poll" title="3. 查询视频任务 Request / Response（最新一次）">
        <pre v-if="poll">{{ json(poll) }}</pre>
        <p v-if="!testId">创建成功后，用返回的任务 ID 替换 &lt;TASK_ID&gt;；后台自动查询，无需手动执行。</p>
        <p v-else>最新查询 HTTP：{{ detail?.latestPoll?.httpStatus ?? (detail?.pollRequest ? detail?.httpStatus : null) ?? '尚未记录' }} · 查询耗时：{{ detail?.latestPoll?.elapsedSeconds ?? '—' }} 秒 · 收到响应：{{ detail?.latestPoll?.receivedAt || '—' }}</p>
        <pre>{{ detail?.pollRequest && detail?.response ? json(detail.response) : detail?.latestPoll ? json(detail.latestPoll.response) : '暂无查询响应。' }}</pre>
      </el-collapse-item>
    </el-collapse>
    <p v-if="!preparing" class="evidence-note">响应已脱敏，图片 Base64 和临时签名地址已省略。</p>
    <template v-if="testId && detail">
      <p>开始：{{ detail.startedAt || '等待执行' }} · 完成：{{ detail.finishedAt || '尚未完成' }} · 总耗时：{{ detail.elapsedSeconds ?? '—' }} 秒</p>
      <el-alert v-if="detail.storedDiagnostic?.issue && detail.storedDiagnostic.issue !== 'NONE'" type="warning" :closable="false" :title="`测试诊断：${detail.storedDiagnostic.issue}`" />
      <h4>生成结果与实际用量</h4><p v-if="waiting">完成后将在这里自动显示生成结果和实际用量。</p><img v-if="detail.preview" :src="detail.preview" alt="本次测试返回的图片" />
      <el-button v-if="detail.hasVideo && !videoUrl" @click="loadVideo">播放已归档的视频</el-button><video v-if="videoUrl" :src="videoUrl" controls />
      <p v-if="detail.currentValidation?.upstreamState === 'succeeded' && !detail.hasVideo">供应商已生成，正在归档；归档失败单独重试，不重新生成。</p>
      <pre v-if="Object.keys(detail.usage || {}).length">{{ json(detail.usage) }}</pre>
      <p v-if="detail.costVisibility === 'hidden'">费用明细仅向有费用查看权限的管理员开放。</p>
      <p v-else>实际采购费用：{{ detail.billing?.amount != null ? `${detail.billing.amount} ${detail.billing.currency}` : '等待实际用量与费用结算，不代表免费' }}</p>
    </template>
    <template #footer>
      <span v-if="preparing" class="footer-cost">开始后按实际用量计费</span>
      <el-button :disabled="submitting" @click="open = false">{{ preparing && !submissionUncertain ? '暂不测试' : '返回配置' }}</el-button>
      <el-button v-if="preparing" type="primary" :loading="submitting" :disabled="!canStart" @click="start">开始测试（{{ kind === 'video' ? '生成 1 个视频' : '生成 1 张图片' }}）</el-button>
    </template>
    </el-drawer>
  </section>
</template>
<style scoped>
.supplier-confirmation { height:auto; align-items:flex-start; margin:8px 0 12px; }
.supplier-confirmation :deep(.el-checkbox__label) { white-space:normal; line-height:1.5; }
.supplier-confirmation :deep(.el-checkbox__input) { margin-top:3px; }
.test-evidence { margin-bottom: 20px; } .test-evidence:empty { display: none; } .footer-cost { display: inline-block; margin-right: 16px; font-size: 13px; color: var(--el-text-color-secondary); } .evidence-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin: 16px 0; } p { color: var(--el-text-color-secondary); line-height: 1.7; } pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: 14px; border-radius: 8px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); max-height: 280px; overflow: auto; } img, video { max-width: 100%; max-height: 360px; object-fit: contain; } summary { cursor: pointer; color: var(--el-color-primary); margin: 12px 0; } .evidence-note { font-size: 12px; }
</style>
