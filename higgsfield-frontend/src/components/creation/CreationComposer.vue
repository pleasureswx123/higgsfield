<script setup lang="ts">
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import StudioPopover from '@/components/ui/StudioPopover.vue'
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount, onActivated } from 'vue'
import { ElInputNumber } from 'element-plus'
import { IconPhoto, IconVideo, IconPlus, IconAt, IconSparkles, IconDiamond, IconMaximize, IconClock, IconVolume, IconVolumeOff, IconArrowLeft, IconArrowRight, IconScissors, IconLayoutColumns } from '@tabler/icons-vue'
import { imageSize, imageSizeIssue } from '@/utils/imageSize'
import type { ModelCapability, ParameterRule, Scalar } from '@/api/creation'

// 全平台共用的创作栏。只展示和发出操作，不自行请求或持有项目业务状态。
const props = withDefaults(defineProps<{
  kind: 'image' | 'video'
  models?: ModelCapability[]
  selected?: ModelCapability | null
  parameters?: Record<string, Scalar>
  projectRequired?: boolean
  generationBlock?: string
  disabled?: boolean
  promptReadonly?: boolean
  loading?: boolean
  saving?: boolean
  checking?: boolean
  jobBusy?: boolean
  jobLabel?: string
  jobSpinning?: boolean
  activeTask?: boolean
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
  aspect_ratio: '比例', aspectRatio: '比例', ratio: '比例', resolution: '分辨率', quality: '质量',
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
      ['ratio', { type: 'string', enum: ['16:9', '9:16', '1:1', '21:9'] }],
      ['resolution', { type: 'string', enum: ['480p', '720p', '1080p'] }],
      ['duration', { type: 'integer', minimum: 4, maximum: 15 }],
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
const modelOptions = computed(() => catalogModels.value.filter(model => model.kind === props.kind))
const menu = ref('')
const modelQuery = ref('')
const filteredModels = computed(() => modelOptions.value.filter(model =>
  [model.displayName, ...model.menuMeta.aliases, model.menuMeta.family].join(' ').toLowerCase().includes(modelQuery.value.toLowerCase())))
const valueOf = (name: string) => props.parameters[name] ?? props.selected?.defaultParameters[name] ?? (!props.selected ? (props.kind === 'video' ? { mode: 'references', resolution: '1080p', duration: 12, count: 1, bitrate_mode: 'high', generate_audio: true } as Record<string, Scalar> : { aspect_ratio: '1:1', quality: 'high', resolution: '2K', count: 1 } as Record<string, Scalar>)[name] : undefined)
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
  ? imageSize(String(valueOf('aspect_ratio') ?? 'Auto'), String(value)).replace('x', ' × ') : ''
const sizeIssue = computed(() => props.kind === 'image' && props.selected
  ? imageSizeIssue(imageSize(String(valueOf('aspect_ratio') ?? 'Auto'), String(valueOf('resolution') ?? '2K')))
  : '')
function resolutionIssue(name: string, value: Scalar) {
  return props.kind === 'image' && props.selected && name === 'resolution'
    ? imageSizeIssue(imageSize(String(valueOf('aspect_ratio') ?? 'Auto'), String(value))) : ''
}
const parameterDisabled = (name: string) => props.disabled || (props.kind === 'image' && name === 'resolution' && valueOf('aspect_ratio') === 'Auto')
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
  if (props.kind === 'image' && name === 'resolution' && valueOf('aspect_ratio') === 'Auto') return '自动'
  if (isMode(name) && typeof value === 'string') return ({ references: 'References', sequel: 'Sequel', prequel: 'Prequel', edit: 'Edit video' }[value] ?? value)
  if (['duration', 'duration_seconds'].includes(name) && typeof value === 'number') return value === -1 ? '自动时长' : `${value}s`
  if (value === 'adaptive') return '自动比例'
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
  if (parameterDisabled(name) || (value !== undefined && resolutionIssue(name, value))) return
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
  <div class="creation-composer-bar" :class="{ 'is-video': kind === 'video', 'is-saving': saving }" aria-label="通用创作栏">
    <div class="composer-mode-rail" aria-label="创作类型">
      <button type="button" :aria-pressed="kind === 'image'" :class="{ selected: kind === 'image' }" :disabled="disabled || saving" @click="emit('kind', 'image')"><IconPhoto :size="17" /><span>图片</span></button>
      <button type="button" :aria-pressed="kind === 'video'" :class="{ selected: kind === 'video' }" :disabled="disabled || saving" @click="emit('kind', 'video')"><IconVideo :size="17" /><span>视频</span></button>
    </div>
    <div class="composer-main-panel">
      <div v-if="$slots.images && referenceCount" class="composer-selected-images"><slot name="images" /></div>
      <div class="composer-entry-surface">
      <div class="composer-input-tools">
        <slot name="prompt"><textarea ref="promptInput" v-model="prompt" rows="1" aria-label="创作描述" :placeholder="kind === 'video' ? '描述你想创作的视频…' : '描述你想创作的画面…'" :disabled="disabled || promptReadonly" maxlength="20000"></textarea></slot>
        <div class="composer-toolbar">
          <div class="composer-reference-tools">
            <button type="button" aria-label="添加参考素材" :disabled="disabled" @click="reference('asset', $event)"><IconPlus :size="16" /></button>
            <button type="button" aria-label="引用元素" :disabled="disabled" @click="reference('element', $event)"><IconAt :size="16" /></button>
            <slot name="history" />
          </div>
          <button v-if="projectRequired" type="button" class="composer-tool" @click="emit('project')"><IconSparkles :size="16" />选择项目与模型 ›</button>
          <StudioPopover v-else placement="top-start" trigger="click" :width="340" :visible="menu === 'models'" :disabled="disabled" @update:visible="menu = $event ? 'models' : ''" popper-class="creation-control-popover">
            <template #reference><button type="button" class="composer-tool composer-model" :disabled="disabled" aria-label="创作模型" @click="modelQuery = ''"><IconSparkles :size="16" />{{ selected?.displayName || '选择模型' }} <span>›</span></button></template>
            <Input v-model="modelQuery" placeholder="搜索模型名称" aria-label="搜索模型名称" />
            <div class="model-menu-list">
              <p v-if="loading" role="status">正在读取模型…</p>
              <p v-else-if="!filteredModels.length" class="parameter-label">暂无匹配的可用模型</p>
              <button v-for="model in filteredModels" :key="model.versionId" type="button" class="model-menu-option" :class="{ active: selected?.versionId === model.versionId }" @click="emit('model', model.versionId); menu = ''">
                <IconSparkles :size="17" /><span><strong>{{ model.displayName }}</strong><small>{{ [model.menuMeta.family, model.menuMeta.releaseLabel, model.menuMeta.tier].filter(Boolean).join(' · ') }}</small></span><span v-if="selected?.versionId === model.versionId">✓</span>
              </button>
            </div>
          </StudioPopover>
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
            <StudioPopover v-else placement="top" trigger="click" :width="isRatio(name) ? 224 : isDuration(name) ? 264 : name === 'resolution' && kind === 'image' ? 228 : name === 'bitrate_mode' ? 214 : 180" :show-arrow="false" :visible="menu === name" :disabled="parameterDisabled(name)" @update:visible="menu = $event ? name : ''" :popper-class="kind === 'video' ? 'creation-control-popover creation-video-popover' : isRatio(name) ? 'creation-control-popover creation-ratio-popover' : name === 'quality' ? 'creation-control-popover creation-quality-popover' : name === 'resolution' ? 'creation-control-popover creation-resolution-popover' : 'creation-control-popover'">
              <template #reference><button type="button" class="composer-tool" :disabled="parameterDisabled(name)" :title="name === 'resolution' && parameterDisabled(name) ? '尺寸由模型自动决定，切换固定比例可选择分辨率' : undefined" :aria-label="labels[name] || name"><component :is="modeIcons[String(valueOf(name))] || IconLayoutColumns" v-if="isMode(name)" :size="16" /><IconMaximize v-else-if="isRatio(name)" :size="16" /><IconDiamond v-else-if="['quality', 'bitrate_mode', 'resolution'].includes(name)" :size="16" /><IconClock v-else-if="['duration', 'duration_seconds'].includes(name)" :size="16" />{{ displayValue(name, valueOf(name)) ?? labels[name] ?? name }}</button></template>
              <label v-if="!isMode(name)" class="parameter-label">{{ labels[name] || name }}</label>
              <div v-if="isDuration(name) && durationChoices(rule).length" class="duration-control">
                <output>{{ displayValue(name, valueOf(name)) }}</output>
                <input type="range" :min="0" :max="durationChoices(rule).length - 1" :step="1" :value="durationIndex(name, rule)" :disabled="disabled" aria-label="视频时长" :aria-valuetext="`${valueOf(name)} 秒`" @input="setDuration(name, rule, $event)" />
              </div>
              <div v-else-if="rule.enum" class="parameter-options" :class="{ 'ratio-options': isRatio(name), 'quality-options': name === 'quality', 'resolution-options': name === 'resolution' }">
                <button v-for="(value, index) in rule.enum" :key="index" type="button" :aria-pressed="valueOf(name) === value" :disabled="Boolean(resolutionIssue(name, value))" :title="resolutionIssue(name, value) || undefined" :class="{ active: valueOf(name) === value }" @click="changeParameter(name, value)">
                  <component :is="modeIcons[String(value)] || IconLayoutColumns" v-if="isMode(name)" :size="20" /><span v-if="isRatio(name)" class="ratio-icon-slot"><IconMaximize v-if="String(value).toLowerCase() === 'auto'" :size="17" /><span v-else class="ratio-icon" :style="ratioStyle(value)"></span></span><span class="parameter-option-copy">{{ displayValue(name, value) }}<small v-if="name === 'bitrate_mode'">{{ value === 'high' ? '压缩较少 · 文件较大' : value === 'standard' ? '压缩较多 · 文件较小' : '' }}</small></span><small v-if="resolutionHint(name, value)">{{ resolutionHint(name, value) }}{{ resolutionIssue(name, value) ? ' · 不支持当前比例' : '' }}</small>
                </button>
              </div>
              <Switch v-else-if="rule.type === 'boolean'" :model-value="valueOf(name) === true" @update:model-value="changeParameter(name, $event)" />
              <ElInputNumber v-else-if="rule.type === 'integer' || rule.type === 'number'" :model-value="typeof valueOf(name) === 'number' ? valueOf(name) as number : undefined" :min="rule.minimum ?? undefined" :max="rule.maximum ?? undefined" :precision="rule.type === 'integer' ? 0 : undefined" @update:model-value="emit('parameter', name, $event)" />
              <Input v-else :model-value="String(valueOf(name) ?? '')" :maxlength="rule.maxLength ?? undefined" @update:model-value="emit('parameter', name, $event)" />
            </StudioPopover>
          </template>
          </div>
          </div>

        </div>
        </div>
      </div>
      <slot name="video" :label="referenceVideoLabel"><button v-if="kind === 'video'" type="button" class="composer-video-reference" :disabled="disabled" aria-label="添加参考视频" @click="reference('asset', $event)"><IconPlus :size="18" /><span>{{ referenceVideoLabel }}</span></button></slot>
      <button type="button" class="composer-generate" :title="generationBlock || (activeTask ? '本次内容已提交，请修改创作内容后再生成' : undefined)" :aria-busy="checking || jobBusy" :disabled="Boolean(generationBlock) || disabled || saving || checking || jobBusy || activeTask || (!projectRequired && (!selected || Boolean(sizeIssue)))" @click="projectRequired ? emit('project') : emit('generate')">
        <strong>{{ projectRequired ? '选择项目' : checking ? (jobLabel || '提交中…') : jobBusy ? (jobLabel || '等待启动') : activeTask ? '已提交' : '生成' }}<span v-if="checking || (jobBusy && jobSpinning !== false)" class="generate-spinner" aria-hidden="true"></span></strong>
      </button>
      </div>
      <p v-if="sizeIssue" class="composer-size-error" role="alert">{{ sizeIssue }}</p>
    </div>
    <Dialog :open="audioConfirm !== null" @update:open="value => { if (!value) audioConfirm = null }">
      <DialogContent class="composer-audio-dialog studio-dialog">
        <DialogHeader><DialogTitle>关闭声音？</DialogTitle><DialogDescription>本次生成的视频将不包含生成音频。</DialogDescription></DialogHeader>
        <DialogFooter><button type="button" class="audio-cancel" @click="audioConfirm = null">取消</button><button type="button" class="audio-confirm" :disabled="disabled" @click="confirmAudioOff">关闭声音</button></DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.composer-size-error { margin:6px 4px 0; color:var(--el-color-danger); font-size:12px; line-height:1.5; }
.creation-composer-bar { display:flex; align-items:stretch; gap:7px; width:100%; text-align:left; }
.composer-mode-rail { display:flex; flex-direction:column; flex:0 0 70px; align-self:flex-start; height:120px; padding:4px; border-radius:25px; background:var(--surface); box-shadow:0 3px 6px #0002; }
.composer-mode-rail button { display:grid; justify-items:center; align-content:center; flex:1; gap:5px; min-height:49px; border:0; border-radius:21px; background:transparent; color:var(--muted-foreground); font-size:11px; cursor:pointer; }
.composer-mode-rail button.selected { background:var(--surface-raised); color:var(--foreground); font-weight:650; }
.composer-main-panel { display:flex; flex-direction:column; flex:1; min-width:0; padding:4px; gap:0; background:var(--surface); border:0; border-radius:25px; box-shadow:0 4px 10px #0002; }
.composer-entry-surface { position:relative; display:flex; align-items:flex-end; width:100%; gap:8px; padding:12px; border-radius:21px; background:var(--surface-raised); }
.composer-selected-images { display:flex; align-items:center; flex:none; gap:8px; width:100%; min-height:68px; overflow-x:auto; overflow-y:hidden; padding:8px; scrollbar-width:none; }
.composer-selected-images::-webkit-scrollbar { display:none; }
.composer-input-tools { flex:1; min-width:0; display:flex; flex-direction:column; }
.composer-input-tools textarea { width:100%; flex:none; min-height:49px; max-height:min(320px, 45dvh); overflow-y:auto; scrollbar-width:thin; scrollbar-color:var(--muted-foreground) transparent; resize:none; border:0; outline:none; background:transparent; color:var(--foreground); font:inherit; font-size:14px; line-height:1.5; }
.composer-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:4px; min-width:0; padding-top:8px; }
.composer-tool-strip { display:flex; align-items:center; flex:1; gap:4px; min-width:0; }
.composer-tool-row { flex:1; min-width:0; overflow-x:auto; scrollbar-width:none; }
.composer-tool-content { display:flex; align-items:center; flex-wrap:nowrap; gap:5px; width:max-content; }
.composer-tool-row::-webkit-scrollbar { display:none; }
.composer-reference-tools { display:flex; border-radius:8px; background:var(--surface-hover); }
.composer-reference-tools button { display:flex; align-items:center; padding:6px; border:0; background:transparent; color:var(--foreground); cursor:pointer; }
.composer-tool { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; min-height:34px; flex-shrink:0; border:0; border-radius:8px; padding:4px 9px; background:var(--surface-hover); color:var(--foreground); font-size:13px; font-weight:600; cursor:pointer; }

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
.is-saving button:disabled { opacity:1; }
button:disabled { opacity:.45; cursor:not-allowed; }
button:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
.composer-input-tools textarea:focus-visible { outline:none; }
.parameter-label { display:block; margin-bottom:10px; color:var(--foreground); }
.parameter-chevron { color:var(--muted-foreground); }
@media(max-width:650px) { .composer-mode-rail { flex-basis:54px; } .composer-main-panel { padding:9px; gap:7px; } .composer-generate { flex-basis:76px; } .composer-model { width:135px; } .composer-tool { padding:4px 6px; } .composer-save span { display:none; } }
.parameter-options, .model-menu-list { display:grid; gap:2px; }
.parameter-options button, .model-menu-option {
  display:flex; align-items:center; gap:8px; width:100%; min-height:34px;
  padding:7px 10px; border:0; border-radius:6px; background:transparent;
  color:var(--foreground); font-size:13px; line-height:19px; font-weight:500; text-align:left; cursor:pointer;
}
.parameter-options button:disabled { cursor:not-allowed; }
.parameter-options button.active, .model-menu-option.active { background:var(--surface-hover); }
.ratio-options { grid-template-columns:repeat(2,minmax(0,1fr)); gap:2px 4px; }
.ratio-options .parameter-option-copy { white-space:nowrap; }
.ratio-icon-slot { display:grid; place-items:center; flex:0 0 16px; color:var(--muted-foreground); }
.ratio-icon { display:inline-block; width:16px; height:12px; border:1px solid currentColor; border-radius:2px; }
.parameter-options small, .model-menu-option small {
  font-size:12px; line-height:17px; font-weight:400; color:var(--muted-foreground);
}
.parameter-options button > small { margin-left:auto; }
.creation-resolution-popover .resolution-options button { align-items:flex-start; flex-direction:column; gap:1px; }
.creation-resolution-popover .resolution-options small { margin-left:0; }
.parameter-option-copy small, .model-menu-option small { display:block; margin-top:2px; }
.model-menu-list { margin-top:6px; max-height:320px; overflow:auto; }
.model-menu-option > span:first-of-type { min-width:0; flex:1; overflow-wrap:anywhere; }
.model-menu-option strong { display:block; font-weight:600; }
.model-menu-option > svg { flex:none; color:var(--muted-foreground); }
.composer-batch { flex-shrink:0; height:34px; display:flex; align-items:center; column-gap:4px; background:var(--surface-hover); border-radius:8px; font-size:12px; }
.composer-batch button { border:0; padding:6px 9px; color:var(--foreground); background:transparent; cursor:pointer; }
</style>

<style scoped>
/* 引用区与输入区分别成层，尺寸与参考图保持一致。 */
.composer-mode-rail { align-self:flex-end; height:128px; }
.composer-entry-surface { min-height:120px; }
.composer-tool,.composer-reference-tools,.composer-batch { min-height:28px; height:28px; border-radius:6px; }
.composer-reference-tools > button, .composer-batch > button { border-radius:inherit; }
.composer-toolbar { padding-top:10px; }
.composer-input-tools textarea { min-height:58px; padding:0 4px; }
.composer-generate { flex-basis:120px; height:80px; min-height:80px; border-radius:12px; }
.composer-video-reference { flex-basis:80px; height:80px; }
/* 空输入时操作区居中；输入增高后沿用底部对齐，不随文字向上漂移。 */
.composer-entry-surface:has(.tiptap p:only-child > br:only-child) > .composer-generate,
.composer-entry-surface:has(.tiptap p:only-child > br:only-child) > .composer-video-reference,
.composer-entry-surface:has(.tiptap p:only-child > br:only-child) > :deep(.reference-video-item),
.composer-entry-surface:has(textarea:placeholder-shown) > .composer-generate,
.composer-entry-surface:has(textarea:placeholder-shown) > .composer-video-reference { align-self:center; }
@media(max-width:650px) { .composer-entry-surface { gap:6px; padding:10px 8px; } .composer-generate { flex-basis:80px; } }
:global(.dark .composer-main-panel),:global(.dark .composer-mode-rail) { background:#1d1f20; }
:global(.dark .composer-entry-surface) { background:#262829; }
:global(.dark .composer-tool),:global(.dark .composer-reference-tools),:global(.dark .composer-batch) { background:#303233; }
</style>

<style>
.creation-control-popover.studio-popover {
  padding:8px; background:var(--surface-raised); color:var(--foreground);
  border:1px solid var(--border); border-radius:12px; box-shadow:0 6px 20px #0002;
}
.creation-control-popover .parameter-label {
  display:block; margin:0; padding:4px 10px 6px;
  font-size:12px; line-height:16px; font-weight:400; color:var(--muted-foreground);
}
.creation-control-popover input[type="text"], .creation-control-popover input[placeholder] {
  height:32px; padding:0 10px; border-radius:6px; font-size:13px;
}
.creation-control-popover .duration-control {
  display:flex; align-items:center; gap:10px; padding:2px 10px 5px;
}
.duration-control output { min-width:28px; font-size:13px; font-variant-numeric:tabular-nums; }
.creation-control-popover .duration-control input {
  flex:1; min-width:0; height:26px; padding:0; border:0; box-shadow:none;
  appearance:auto; accent-color:var(--primary); background:transparent; cursor:ew-resize;
}
.duration-control input:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
.composer-video-reference span { font-size:11px; }
.composer-audio-dialog.studio-dialog { border-radius:24px; padding:24px; background:var(--surface); color:var(--foreground); }
.composer-audio-dialog p { color:var(--muted-foreground); line-height:1.7; }
.composer-audio-dialog .el-dialog__footer { padding-top:20px; display:flex; justify-content:flex-end; gap:8px; }
.composer-audio-dialog .audio-cancel, .composer-audio-dialog .audio-confirm { padding:13px 24px; border:0; border-radius:13px; font-weight:600; cursor:pointer; }
.audio-cancel { background:var(--surface-hover); color:var(--foreground); }
.audio-confirm { background:var(--foreground); color:var(--background); }

/* 弹层挂载在创作栏外，与栏内操作共享悬停反馈。 */
@media (hover: hover) {
  :is(.creation-composer-bar, .creation-control-popover, .creation-reference-popover,
      .reference-scope-menu, .reference-sort-menu, .prompt-element-suggestions,
      .prompt-reference-preview, .composer-audio-dialog, .creation-expanded)
    button:enabled:not([aria-disabled="true"]):hover {
    background-color: color-mix(in srgb, var(--foreground) 6%, var(--surface-hover));
    cursor: pointer;
  }

  .creation-composer-bar button.composer-generate:enabled:hover {
    background-color: color-mix(in srgb, var(--primary) 92%, white);
  }

  .composer-audio-dialog button.audio-confirm:enabled:hover {
    background-color: color-mix(in srgb, var(--foreground) 92%, var(--surface));
  }

  .creation-composer-bar button.composer-video-reference:enabled:hover {
    border-color: color-mix(in srgb, var(--foreground) 18%, var(--border));
  }

  .creation-composer-bar :is(textarea:enabled:not([readonly]), [contenteditable="true"], .prompt-element-tag):hover,
  .creation-control-popover input:enabled:hover {
    background-color: color-mix(in srgb, var(--foreground) 4%, transparent);
  }

  .creation-control-popover .duration-control:has(input:enabled:hover) {
    border-color: color-mix(in srgb, var(--foreground) 18%, var(--border));
  }
}

@media (hover: hover) and (prefers-reduced-motion: no-preference) {
  :is(.creation-composer-bar, .creation-control-popover, .creation-reference-popover,
      .reference-scope-menu, .reference-sort-menu, .prompt-element-suggestions,
      .prompt-reference-preview, .composer-audio-dialog, .creation-expanded)
    :where(button, input, textarea, [contenteditable="true"], .duration-control) {
    transition: background-color 140ms ease-out, border-color 140ms ease-out;
  }
}
</style>
