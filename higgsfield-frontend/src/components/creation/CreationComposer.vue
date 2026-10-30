<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount, onActivated } from 'vue'
import { ElInputNumber, ElSwitch, ElPopover, ElInput, ElDialog } from 'element-plus'
import { IconPhoto, IconVideo, IconPlus, IconAt, IconSparkles, IconDiamond, IconMaximize, IconClock, IconVolume, IconVolumeOff, IconArrowLeft, IconArrowRight, IconScissors, IconLayoutColumns } from '@tabler/icons-vue'
import type { ModelCapability, ParameterRule, Scalar } from '@/api/creation'

// 全平台共用的创作栏。只展示和发出操作，不自行请求或持有项目业务状态。
const props = withDefaults(defineProps<{
  kind: 'image' | 'video'
  models?: ModelCapability[]
  selected?: ModelCapability | null
  parameters?: Record<string, Scalar>
  projectRequired?: boolean
  disabled?: boolean
  promptReadonly?: boolean
  loading?: boolean
  saving?: boolean
  checking?: boolean
  referenceCount?: number
  estimate?: string
}>(), { models: () => [], parameters: () => ({}) })
const prompt = defineModel<string>('prompt', { required: true })
const emit = defineEmits<{
  kind: [kind: 'image' | 'video']
  model: [versionId: string]
  parameter: [name: string, value: Scalar | undefined]
  project: []
  reference: [source: 'asset' | 'element', anchor: HTMLElement]
  more: []
  save: []
  generate: []
}>()
const labels: Record<string, string> = {
  aspect_ratio: '比例', aspectRatio: '比例', resolution: '分辨率', quality: '质量',
  duration: '时长', duration_seconds: '时长', size: '尺寸', count: '数量', n: '数量',
  mode: '模式', generation_mode: '模式', bitrate_mode: '码率', num_images: '数量', seed: '种子', audio: '音频', generate_audio: '音频',
}
// 主工具栏按创作操作排序，其他字段在更多设置中编辑。
const parameterGroups = [ ['aspect_ratio', 'aspectRatio'], ['quality'], ['resolution', 'size'], ['duration', 'duration_seconds'], ['count', 'n', 'num_images', 'batch_size'] ]
const quickParameters = computed(() => {
  if (!props.selected) {
    const entries: [string, ParameterRule][] = [['aspect_ratio', { type: 'string', enum: ['Auto', '1:1', '3:2', '2:3', '16:9', '9:16', '4:3', '3:4', '21:9'] }]]
    if (props.kind === 'image') {
      entries.push(['quality', { type: 'string', enum: ['low', 'medium', 'high'] }])
      entries.push(['resolution', { type: 'string', enum: ['1K', '2K', '4K'] }])
      entries.push(['count', { type: 'integer', minimum: 1, maximum: 4 }])
    }
    if (props.kind === 'video') return [
      ['mode', { type: 'string', enum: ['references', 'sequel', 'prequel', 'edit'] }],
      ['resolution', { type: 'string', enum: ['480p', '720p', '1080p'] }],
      ['duration', { type: 'integer', minimum: 4, maximum: 30 }],
      ['count', { type: 'integer', minimum: 1, maximum: 4 }],
      ['bitrate_mode', { type: 'string', enum: ['high', 'standard'] }],
      ['generate_audio', { type: 'boolean' }],
    ] as [string, ParameterRule][]
    return entries
  }
  const properties = props.selected.parametersSchema.properties
  const groups = props.kind === 'video' ? [['mode', 'generation_mode', 'aspect_ratio', 'aspectRatio', 'ratio'], ['resolution', 'size'], ['duration', 'duration_seconds'], ['count', 'n', 'batch_size'], ['quality', 'bitrate_mode'], ['generate_audio', 'audio']] : parameterGroups
  return groups.flatMap(group => {
    const name = group.find(key => properties[key])
    return name ? [[name, properties[name]!] as [string, ParameterRule]] : []
  })
})
const promptInput = ref<HTMLTextAreaElement>()
let promptObserver: ResizeObserver | undefined
let promptWidth = 0
function resizePrompt() {
  const input = promptInput.value
  if (!input) return
  // 先收回高度再测量，删除文字或切换创作类型时也能恢复紧凑布局。
  input.style.height = '0px'
  input.style.height = `${input.scrollHeight}px`
}
watch(prompt, resizePrompt, { flush: 'post' })
onMounted(() => {
  resizePrompt()
  promptObserver = new ResizeObserver(entries => {
    const width = entries[0]?.contentRect.width ?? 0
    if (width !== promptWidth) { promptWidth = width; resizePrompt() }
  })
  if (promptInput.value) promptObserver.observe(promptInput.value)
})
onActivated(() => { void nextTick(resizePrompt) })
onBeforeUnmount(() => promptObserver?.disconnect())
const toolRow = ref<HTMLElement>()
watch(() => props.kind, async () => {
  await nextTick()
  if (toolRow.value) toolRow.value.scrollLeft = 0
})
const catalogModels = computed(() => props.selected && !props.models.some(item => item.versionId === props.selected?.versionId)
  ? [props.selected, ...props.models] : props.models)
const modelOptions = computed(() => props.kind === 'image'
  ? catalogModels.value.filter(model => model.displayName === 'mm-imagen2' || model.menuMeta.aliases.includes('mm-imagen2'))
  : catalogModels.value)
const pendingImageModel = computed(() => props.kind === 'image' && !modelOptions.value.length && !props.loading)
const showPendingImageModel = computed(() => pendingImageModel.value && 'mm-imagen2'.includes(modelQuery.value.trim().toLowerCase()))
const menu = ref('')
const modelQuery = ref('')
const filteredModels = computed(() => modelOptions.value.filter(model =>
  [model.displayName, ...model.menuMeta.aliases, model.menuMeta.family].join(' ').toLowerCase().includes(modelQuery.value.toLowerCase())))
const valueOf = (name: string) => props.parameters[name] ?? props.selected?.defaultParameters[name] ?? (!props.selected ? (props.kind === 'video' ? { mode: 'references', resolution: '1080p', duration: 12, count: 1, bitrate_mode: 'high', generate_audio: true } as Record<string, Scalar> : { aspect_ratio: 'Auto', quality: 'high', resolution: '2K', count: 1 } as Record<string, Scalar>)[name] : undefined)
const isRatio = (name: string) => ['aspect_ratio', 'aspectRatio', 'ratio'].includes(name)
const isBatch = (name: string, rule: ParameterRule) => ['count', 'n', 'num_images', 'batch_size'].includes(name)
  && rule.type === 'integer' && !rule.enum && (rule.minimum ?? 1) <= 4
const batchMin = (rule: ParameterRule) => Math.max(1, rule.minimum ?? 1)
const batchMax = (rule: ParameterRule) => Math.min(4, rule.maximum ?? 4)
const batchValue = (name: string, rule: ParameterRule) => Math.min(batchMax(rule), Math.max(batchMin(rule), Number(valueOf(name) ?? 1)))
function stepBatch(name: string, rule: ParameterRule, offset: number) {
  const next = batchValue(name, rule) + offset
  if (props.disabled || next < batchMin(rule) || next > batchMax(rule)) return
  emit('parameter', name, next)
}
const resolutionHint = (name: string, value: Scalar) => name === 'resolution'
  ? ({ '1K': '1024 px', '2K': '2048 px', '4K': '4096 px' }[String(value).toUpperCase()] ?? '') : ''
const isDuration = (name: string) => ['duration', 'duration_seconds'].includes(name)
const isMode = (name: string) => ['mode', 'generation_mode'].includes(name)
const modeIcons: Record<string, typeof IconArrowLeft> = { references: IconLayoutColumns, sequel: IconArrowRight, prequel: IconArrowLeft, edit: IconScissors }
const audioConfirm = ref<string | null>(null)
function toggleAudio(name: string) {
  if (props.disabled) return
  if (valueOf(name) === true) { menu.value = ''; audioConfirm.value = name }
  else changeParameter(name, true)
}
function confirmAudioOff() {
  if (audioConfirm.value && !props.disabled) changeParameter(audioConfirm.value, false)
  audioConfirm.value = null
}
function durationChoices(rule: ParameterRule) {
  if (rule.enum) return rule.enum.filter((value): value is number => typeof value === 'number' && value > 0 && value <= 30).sort((a, b) => a - b)
  const min = Math.max(1, Math.ceil(rule.minimum ?? 4)), max = Math.min(30, Math.floor(rule.maximum ?? 30))
  return Array.from({ length: Math.max(0, max - min + 1) }, (_, index) => min + index)
}
function durationIndex(name: string, rule: ParameterRule) { return Math.max(0, durationChoices(rule).indexOf(Number(valueOf(name)))) }
function setDuration(name: string, rule: ParameterRule, event: Event) {
  const value = durationChoices(rule)[Number((event.target as HTMLInputElement).value)]
  if (!props.disabled && value !== undefined) emit('parameter', name, value)
}
const referenceVideoLabel = computed(() => ['sequel', 'prequel'].includes(String(valueOf('mode') ?? valueOf('generation_mode'))) ? '待延长视频' : valueOf('mode') === 'edit' ? '待编辑视频' : '参考视频')
const displayValue = (name: string, value: Scalar | undefined) => {
  if (isMode(name) && typeof value === 'string') return ({ references: 'References', sequel: 'Sequel', prequel: 'Prequel', edit: 'Edit video' }[value] ?? value)
  if (['duration', 'duration_seconds'].includes(name) && typeof value === 'number') return `${value}s`
  if (['audio', 'generate_audio'].includes(name) && typeof value === 'boolean') return value ? 'On' : 'Off'
  if (['quality', 'bitrate_mode'].includes(name) && typeof value === 'string') return ({ low: 'Low', medium: 'Medium', high: 'High', standard: 'Standard' }[value.toLowerCase()] ?? value)
  return value
}
function ratioStyle(value: Scalar) {
  const match = /^(\d+):(\d+)$/.exec(String(value))
  if (!match) return {}
  const ratio = Number(match[1]) / Number(match[2])
  return { width: `${ratio >= 1 ? 17 : 17 * ratio}px`, height: `${ratio >= 1 ? 17 / ratio : 17}px` }
}
function changeParameter(name: string, value: Scalar | undefined) {
  emit('parameter', name, value)
  menu.value = ''
}
function reference(source: 'asset' | 'element', event: MouseEvent) {
  menu.value = ''
  if (props.projectRequired) emit('project')
  else emit('reference', source, (event.currentTarget as HTMLElement).closest('.composer-main-panel') as HTMLElement)
}
watch(() => [props.kind, props.selected?.versionId, props.disabled], () => { menu.value = ''; audioConfirm.value = null })
</script>

<template>
  <div class="creation-composer-bar" :class="{ 'is-video': kind === 'video' }" aria-label="通用创作栏">
    <div class="composer-mode-rail" aria-label="创作类型">
      <button type="button" :aria-pressed="kind === 'image'" :class="{ selected: kind === 'image' }" :disabled="disabled" @click="emit('kind', 'image')"><IconPhoto :size="17" /><span>图片</span></button>
      <button type="button" :aria-pressed="kind === 'video'" :class="{ selected: kind === 'video' }" :disabled="disabled" @click="emit('kind', 'video')"><IconVideo :size="17" /><span>视频</span></button>
    </div>
    <div class="composer-main-panel">
      <div v-if="$slots.images" class="composer-selected-images"><slot name="images" /></div>
      <div class="composer-entry-surface">
      <div class="composer-input-tools">
        <textarea ref="promptInput" v-model="prompt" rows="1" aria-label="创作描述" :placeholder="kind === 'video' ? '描述你想创作的视频…' : '描述你想创作的画面…'" :disabled="disabled || promptReadonly" maxlength="20000"></textarea>
        <div class="composer-toolbar">
          <div class="composer-reference-tools">
            <button type="button" aria-label="添加参考素材" :disabled="disabled" @click="reference('asset', $event)"><IconPlus :size="16" /></button>
            <button type="button" aria-label="引用元素" :disabled="disabled" @click="reference('element', $event)"><IconAt :size="16" /></button>
          </div>
          <button v-if="projectRequired" type="button" class="composer-tool" @click="emit('project')"><IconSparkles :size="16" />选择项目与模型 ›</button>
          <ElPopover v-else placement="top-start" trigger="click" :width="420" :visible="menu === 'models'" :disabled="disabled" @update:visible="menu = $event ? 'models' : ''" popper-class="creation-control-popover">
            <template #reference><button type="button" class="composer-tool composer-model" :disabled="disabled" aria-label="创作模型" @click="modelQuery = ''"><IconSparkles :size="16" />{{ kind === 'image' ? 'mm-imagen2' : selected?.displayName || '选择模型' }} <span>›</span></button></template>
            <ElInput v-model="modelQuery" placeholder="搜索模型名称" aria-label="搜索模型名称" clearable />
            <div class="model-menu-list">
              <p v-if="loading" role="status">正在读取模型…</p>
              <p v-else-if="!filteredModels.length && !showPendingImageModel" class="parameter-label">暂无匹配的可用模型</p>
              <p v-if="kind === 'image' && (filteredModels.length || showPendingImageModel)" class="model-menu-heading">图片生成模型</p>
              <div v-if="showPendingImageModel" class="model-menu-option model-pending" aria-label="mm-imagen2 待接入">
                <span class="model-menu-icon"><IconPhoto :size="24" /></span><span><strong>mm-imagen2</strong><small>待配置供应商连接与项目授权</small></span><span class="model-status">待接入</span>
              </div>
              <button v-for="model in filteredModels" :key="model.versionId" type="button" class="model-menu-option" :class="{ active: selected?.versionId === model.versionId }" @click="emit('model', model.versionId); menu = ''">
                <IconSparkles :size="22" /><span><strong>{{ model.displayName }}</strong><small>{{ [model.menuMeta.family, model.menuMeta.releaseLabel, model.menuMeta.tier].filter(Boolean).join(' · ') }}</small></span><span v-if="selected?.versionId === model.versionId">✓</span>
              </button>
            </div>
            <div v-if="kind === 'image'" class="model-pricing-note">
              <div><span>输入 Token</span><strong>$5.00 / 1M</strong></div>
              <div><span>输出 Token</span><strong>$30.00 / 1M</strong></div>
              <p>按上游实际返回的输入、输出 Token 结算，金额单位 USD。</p>
            </div>
          </ElPopover>
        <div class="composer-tool-strip">
          <div ref="toolRow" class="composer-tool-row">
          <div class="composer-tool-content">
          <template v-for="[name, rule] in quickParameters" :key="name">
            <div v-if="isBatch(name, rule)" class="composer-batch" aria-label="生成数量">
              <button type="button" aria-label="减少生成数量" :disabled="disabled || batchValue(name, rule) <= batchMin(rule)" @click="stepBatch(name, rule, -1)">−</button>
              <span aria-live="polite">{{ batchValue(name, rule) }}/{{ batchMax(rule) }}</span>
              <button type="button" aria-label="增加生成数量" :disabled="disabled || batchValue(name, rule) >= batchMax(rule)" @click="stepBatch(name, rule, 1)">＋</button>
            </div>
            <button v-else-if="rule.type === 'boolean' && ['audio', 'generate_audio'].includes(name)" type="button" class="composer-tool" :disabled="disabled" aria-label="生成声音" :aria-pressed="valueOf(name) === true" @click="toggleAudio(name)"><IconVolume v-if="valueOf(name) === true" :size="16" /><IconVolumeOff v-else :size="16" />{{ displayValue(name, valueOf(name)) }}</button>
            <ElPopover v-else placement="top" trigger="click" :width="isDuration(name) ? 320 : name === 'resolution' && kind === 'image' ? 300 : name === 'bitrate_mode' ? 240 : 210" :show-arrow="false" :visible="menu === name" :disabled="disabled" @update:visible="menu = $event ? name : ''" :popper-class="kind === 'video' ? 'creation-control-popover creation-video-popover' : isRatio(name) ? 'creation-control-popover creation-ratio-popover' : name === 'quality' ? 'creation-control-popover creation-quality-popover' : name === 'resolution' ? 'creation-control-popover creation-resolution-popover' : 'creation-control-popover'">
              <template #reference><button type="button" class="composer-tool" :disabled="disabled" :aria-label="labels[name] || name"><component :is="modeIcons[String(valueOf(name))] || IconLayoutColumns" v-if="isMode(name)" :size="16" /><IconMaximize v-else-if="isRatio(name)" :size="16" /><IconDiamond v-else-if="['quality', 'bitrate_mode', 'resolution'].includes(name)" :size="16" /><IconClock v-else-if="['duration', 'duration_seconds'].includes(name)" :size="16" />{{ displayValue(name, valueOf(name)) ?? labels[name] ?? name }}</button></template>
              <label v-if="!isMode(name)" class="parameter-label">{{ labels[name] || name }}</label>
              <div v-if="isDuration(name) && durationChoices(rule).length" class="duration-control">
                <output>{{ displayValue(name, valueOf(name)) }}</output>
                <input type="range" :min="0" :max="durationChoices(rule).length - 1" :step="1" :value="durationIndex(name, rule)" :disabled="disabled" aria-label="视频时长" :aria-valuetext="`${valueOf(name)} 秒`" @input="setDuration(name, rule, $event)" />
              </div>
              <div v-else-if="rule.enum" class="parameter-options" :class="{ 'ratio-options': isRatio(name), 'quality-options': name === 'quality', 'resolution-options': name === 'resolution' }">
                <button v-for="(value, index) in rule.enum" :key="index" type="button" :aria-pressed="valueOf(name) === value" :class="{ active: valueOf(name) === value }" @click="changeParameter(name, value)">
                  <component :is="modeIcons[String(value)] || IconLayoutColumns" v-if="isMode(name)" :size="20" /><span v-if="isRatio(name)" class="ratio-icon-slot"><IconMaximize v-if="String(value).toLowerCase() === 'auto'" :size="17" /><span v-else class="ratio-icon" :style="ratioStyle(value)"></span></span><span class="parameter-option-copy">{{ displayValue(name, value) }}<small v-if="name === 'bitrate_mode'">{{ value === 'high' ? '压缩较少 · 文件较大' : value === 'standard' ? '压缩较多 · 文件较小' : '' }}</small></span><small v-if="resolutionHint(name, value)">{{ resolutionHint(name, value) }}</small>
                </button>
              </div>
              <ElSwitch v-else-if="rule.type === 'boolean'" :model-value="valueOf(name) === true" @update:model-value="changeParameter(name, $event)" />
              <ElInputNumber v-else-if="rule.type === 'integer' || rule.type === 'number'" :model-value="typeof valueOf(name) === 'number' ? valueOf(name) as number : undefined" :min="rule.minimum ?? undefined" :max="rule.maximum ?? undefined" :precision="rule.type === 'integer' ? 0 : undefined" @update:model-value="emit('parameter', name, $event)" />
              <ElInput v-else :model-value="String(valueOf(name) ?? '')" :maxlength="rule.maxLength ?? undefined" @update:model-value="emit('parameter', name, $event)" />
            </ElPopover>
          </template>
          </div>
          </div>

        </div>
        </div>
      </div>
      <slot name="video" :label="referenceVideoLabel"><button v-if="kind === 'video'" type="button" class="composer-video-reference" :disabled="disabled" aria-label="添加参考视频" @click="reference('asset', $event)"><IconPlus :size="18" /><span>{{ referenceVideoLabel }}</span></button></slot>
      <button type="button" class="composer-generate" :aria-busy="checking" :disabled="disabled || checking || (!projectRequired && !selected)" @click="projectRequired ? emit('project') : emit('generate')">
        <strong>{{ projectRequired ? '选择项目' : '生成' }}<span v-if="checking" class="generate-spinner" aria-hidden="true"></span></strong>
      </button>
      </div>
    </div>
    <ElDialog :model-value="audioConfirm !== null" title="关闭声音？" width="min(420px, 92vw)" append-to-body align-center :show-close="false" class="composer-audio-dialog" @close="audioConfirm = null">
      <p>本次生成的视频将不包含生成音频。</p>
      <template #footer><button type="button" class="audio-cancel" @click="audioConfirm = null">取消</button><button type="button" class="audio-confirm" :disabled="disabled" @click="confirmAudioOff">关闭声音</button></template>
    </ElDialog>
  </div>
</template>

<style scoped>
.creation-composer-bar { display:flex; align-items:stretch; gap:7px; width:100%; text-align:left; }
.composer-mode-rail { display:flex; flex-direction:column; flex:0 0 70px; align-self:flex-end; height:120px; padding:4px; border-radius:25px; background:var(--surface); box-shadow:0 3px 6px #0002; }
.composer-mode-rail button { display:grid; justify-items:center; align-content:center; flex:1; gap:5px; min-height:49px; border:0; border-radius:21px; background:transparent; color:var(--muted-foreground); font-size:11px; cursor:pointer; }
.composer-mode-rail button.selected { background:var(--surface-raised); color:var(--foreground); font-weight:650; }
.composer-main-panel { display:flex; flex-direction:column; flex:1; min-width:0; padding:4px; gap:0; background:var(--surface); border:0; border-radius:25px; box-shadow:0 4px 10px #0002; }
.composer-entry-surface { display:flex; align-items:flex-end; width:100%; gap:8px; padding:16px 12px 12px; border-radius:21px; background:var(--surface-raised); }
.composer-selected-images { display:flex; align-items:center; flex:none; gap:8px; width:100%; min-height:68px; overflow-x:auto; overflow-y:hidden; padding:8px; scrollbar-width:none; }
.composer-selected-images::-webkit-scrollbar { display:none; }
.composer-input-tools { flex:1; min-width:0; display:flex; flex-direction:column; }
.composer-input-tools textarea { width:100%; flex:none; min-height:49px; max-height:min(320px, 45dvh); overflow-y:auto; scrollbar-width:thin; scrollbar-color:var(--muted-foreground) transparent; resize:none; border:0; outline:none; background:transparent; color:var(--foreground); font:inherit; font-size:14px; line-height:1.5; }
.composer-toolbar { display:flex; align-items:center; gap:4px; min-width:0; padding-top:8px; }
.composer-tool-strip { display:flex; align-items:center; flex:1; gap:4px; min-width:0; }
.composer-tool-row { flex:1; min-width:0; overflow-x:auto; scrollbar-width:none; }
.composer-tool-content { display:flex; align-items:center; flex-wrap:nowrap; gap:5px; width:max-content; }
.composer-tool-row::-webkit-scrollbar { display:none; }
.composer-reference-tools { display:flex; border-radius:8px; background:var(--surface-hover); }
.composer-reference-tools button { display:flex; align-items:center; padding:6px; border:0; background:transparent; color:var(--foreground); cursor:pointer; }
.composer-tool { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; min-height:34px; flex-shrink:0; border:0; border-radius:8px; padding:4px 9px; background:var(--surface-hover); color:var(--foreground); font-size:13px; font-weight:600; cursor:pointer; }
.composer-tool:hover,.composer-reference-tools button:hover { background:var(--border); }
.composer-model { min-width:160px; width:auto; max-width:220px; overflow:hidden; text-overflow:ellipsis; }
.composer-model > svg { color:var(--primary); flex-shrink:0; }
.composer-model > span:last-child { margin-left:auto; }
.composer-overflow { margin-left:auto; }
.composer-reference-tools { flex-shrink:0; height:34px; }
.reference-count { font-size:10px; }
.composer-model :deep(.el-select__wrapper) { min-height:28px; background:var(--surface-hover); border-radius:8px; box-shadow:none; }
.composer-page { padding:4px 6px; }
.is-video .composer-tool-content { gap:4px; }
.is-video .composer-tool-row::-webkit-scrollbar { display:none; }
.is-video .composer-model { min-width:130px; max-width:160px; }
.is-video .composer-tool { font-size:12px; padding:4px 7px; }
.is-video .composer-batch button { padding:6px; }
.is-video .composer-overflow { padding:4px; }
.is-video .composer-reference-tools button { padding:5px; }
.composer-video-reference { display:flex; flex-direction:column; justify-content:space-between; align-items:flex-start; flex:0 0 78px; height:90px; padding:10px; border:1px solid var(--border); border-radius:12px; color:var(--foreground); background:linear-gradient(var(--surface),var(--surface-hover)); cursor:pointer; font-size:12px; font-weight:650; }
@media(max-width:650px) { .composer-video-reference { flex-basis:52px; padding:7px; font-size:10px; } }
.composer-generate { display:grid; align-content:center; justify-items:center; gap:4px; flex:0 0 80px; height:90px; min-height:90px; border:0; border-radius:13px; background:var(--primary); color:var(--primary-foreground); box-shadow:0 3px 0 color-mix(in srgb,var(--primary) 65%,black); font-size:12px; cursor:pointer; }
.composer-generate strong { display:flex; align-items:center; gap:6px; font-weight:700; }
.composer-generate .generate-spinner { width:12px; height:12px; border:2px solid currentColor; border-right-color:transparent; border-radius:50%; animation:generate-spin .7s linear infinite; }
.composer-generate[aria-busy="true"] { cursor:wait; }
@keyframes generate-spin { to { transform:rotate(360deg); } }
.composer-generate span { font-size:11px; }
button:disabled { opacity:.45; cursor:not-allowed; }
button:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
.composer-input-tools textarea:focus-visible { outline:none; }
.parameter-label { display:block; margin-bottom:10px; color:var(--foreground); }
.parameter-chevron { color:var(--muted-foreground); }
@media(max-width:650px) { .composer-mode-rail { flex-basis:54px; } .composer-main-panel { padding:9px; gap:7px; } .composer-generate { flex-basis:76px; } .composer-model { width:135px; } .composer-tool { padding:4px 6px; } .composer-save span { display:none; } }
.parameter-options { display:grid; gap:4px; }
.ratio-options { grid-template-columns:1fr 1fr; gap:0; }
.ratio-options button { min-height:52px; padding:14px 16px; border-radius:0; border-top:1px solid var(--border); font-size:15px; font-weight:600; }
.ratio-options button:nth-child(odd) { border-right:1px solid var(--border); }
.ratio-icon-slot { display:flex; align-items:center; justify-content:center; width:18px; height:18px; color:var(--muted-foreground); flex-shrink:0; }
.parameter-options button,.model-menu-option { display:flex; align-items:center; gap:10px; width:100%; padding:10px; background:transparent; color:var(--foreground); border:0; border-radius:7px; text-align:left; cursor:pointer; }
.parameter-options button:hover,.parameter-options button.active,.model-menu-option:hover,.model-menu-option.active { background:var(--surface-hover); }
.parameter-options small { margin-left:auto; color:var(--muted-foreground); }
.ratio-icon { display:inline-block; width:16px; height:12px; border:1px solid currentColor; border-radius:2px; flex-shrink:0; }
.model-menu-heading { margin:8px 10px; color:var(--muted-foreground); font-size:12px; }
.model-menu-icon { width:44px; height:44px; display:grid; place-items:center; border-radius:12px; background:var(--surface-hover); }
.model-pending { cursor:default; }
.model-status { font-size:11px; color:var(--muted-foreground); white-space:nowrap; }
.model-pricing-note { margin-top:12px; padding:14px 10px 2px; border-top:1px solid var(--border); font-size:12px; }
.model-pricing-note > div { display:flex; justify-content:space-between; margin-bottom:8px; }
.model-pricing-note p { margin:12px 0 0; line-height:1.6; color:var(--muted-foreground); }
.model-menu-list { max-height:360px; overflow:auto; margin-top:10px; }
.model-menu-option > span:first-of-type { flex:1; }
.model-pending > .model-menu-icon { flex:0 0 44px; }
.model-pending > span:nth-child(2) { flex:1; }
.model-menu-option strong,.model-menu-option small { display:block; }
.model-menu-option small { color:var(--muted-foreground); margin-top:4px; }
.composer-batch { flex-shrink:0; height:34px; display:flex; align-items:center; background:var(--surface-hover); border-radius:8px; font-size:12px; }
.composer-batch button { border:0; padding:6px 9px; color:var(--foreground); background:transparent; cursor:pointer; }
</style>

<style scoped>
/* 引用区与输入区分别成层，尺寸与参考图保持一致。 */
.composer-mode-rail { height:116px; }
.composer-tool,.composer-reference-tools,.composer-batch { min-height:28px; height:28px; border-radius:6px; }
.composer-toolbar { padding-top:4px; }
.composer-input-tools textarea { min-height:48px; padding:0 4px; }
.composer-generate { flex-basis:120px; height:80px; min-height:80px; border-radius:12px; }
.composer-video-reference { flex-basis:80px; height:80px; }
@media(max-width:650px) { .composer-entry-surface { gap:6px; padding:12px 8px 8px; } .composer-generate { flex-basis:80px; } }
:global(.dark .composer-main-panel),:global(.dark .composer-mode-rail) { background:#1d1f20; }
:global(.dark .composer-entry-surface) { background:#262829; }
:global(.dark .composer-tool),:global(.dark .composer-reference-tools),:global(.dark .composer-batch) { background:#303233; }
</style>

<style>
.creation-control-popover.el-popover { background:var(--surface-raised); color:var(--foreground); border:1px solid var(--border); border-radius:14px; max-width:calc(100vw - 24px); box-shadow:0 12px 36px #0004; }
</style>

<style>
.creation-ratio-popover.el-popover { padding:0; border-radius:24px; overflow:hidden; }
.creation-ratio-popover .parameter-label { margin:0; padding:14px 16px; font-size:12px; color:var(--muted-foreground); }
</style>

<style>
.creation-quality-popover.el-popover { padding:0; border-radius:24px; overflow:hidden; }
.creation-quality-popover .parameter-label { margin:0; padding:14px 16px; font-size:12px; color:var(--muted-foreground); }
.creation-quality-popover .quality-options { gap:0; }
.creation-quality-popover .quality-options button { min-height:47px; padding:12px 16px; border-radius:0; border-top:1px solid var(--border); font-size:16px; font-weight:600; }
</style>

<style>
.creation-resolution-popover.el-popover { padding:0; border-radius:24px; overflow:hidden; }
.creation-resolution-popover .parameter-label { margin:0; padding:14px 16px; font-size:12px; color:var(--muted-foreground); }
.creation-resolution-popover .resolution-options { gap:0; }
.creation-resolution-popover .resolution-options button { min-height:74px; padding:12px 16px; border-radius:0; border-top:1px solid var(--border); display:flex; flex-direction:column; align-items:flex-start; gap:5px; font-size:16px; font-weight:600; }
.creation-resolution-popover .resolution-options small { margin-left:0; font-size:14px; color:var(--muted-foreground); }
</style>

<style>
.creation-video-popover.el-popover { padding:0; border-radius:20px; overflow:hidden; }
.creation-video-popover .parameter-label { margin:0; padding:12px 16px; color:var(--muted-foreground); font-size:12px; }
.creation-video-popover .parameter-options { gap:0; }
.creation-video-popover .parameter-options button { min-height:40px; padding:11px 16px; border-radius:0; font-weight:600; }
.creation-video-popover .parameter-option-copy small { display:block; margin-top:5px; font-size:12px; font-weight:400; }
.creation-video-popover .duration-control { display:flex; align-items:center; flex-wrap:wrap; gap:12px; margin:0 16px 16px; padding:10px 12px; border:1px solid var(--border); border-radius:6px; }
.duration-control output { font-size:13px; min-width:30px; }
.duration-control input { flex:1; min-width:0; appearance:none; height:32px; background:transparent; cursor:ew-resize; }
.duration-control input::-webkit-slider-runnable-track { height:32px; background:transparent; }
.duration-control input::-webkit-slider-thumb { appearance:none; width:4px; height:32px; border-radius:2px; background:var(--foreground); }
.duration-control input::-moz-range-thumb { width:4px; height:32px; border:0; border-radius:2px; background:var(--foreground); }
.duration-control input:focus-visible { outline:2px solid var(--focus); outline-offset:3px; }
.composer-video-reference span { font-size:11px; }
.composer-audio-dialog.el-dialog { border-radius:24px; padding:24px; background:var(--surface); color:var(--foreground); }
.composer-audio-dialog p { color:var(--muted-foreground); line-height:1.7; }
.composer-audio-dialog .el-dialog__footer { padding-top:20px; display:flex; justify-content:flex-end; gap:8px; }
.composer-audio-dialog button { padding:13px 24px; border:0; border-radius:13px; font-weight:600; cursor:pointer; }
.audio-cancel { background:var(--surface-hover); color:var(--foreground); }
.audio-confirm { background:var(--foreground); color:var(--background); }
</style>
