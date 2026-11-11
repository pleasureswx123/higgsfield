<script setup lang="ts">
import { ref, watch } from 'vue'
import { useTimeoutFn } from '@vueuse/core'
import { ElCheckbox, ElDatePicker, ElInput, ElSelect, ElOption, ElTooltip } from 'element-plus'
import { IconFilter, IconLayoutGrid, IconLayoutColumns, IconDots, IconRefresh, IconCheckbox } from '@tabler/icons-vue'
import Button from '@/components/ui/Button.vue'
import StudioPopover from '@/components/ui/StudioPopover.vue'
import { Slider } from '@/components/ui/slider'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { type AssetFileType } from '@/utils/assetFormats'

export interface AssetFilterValues {
  search: string
  fileType: '' | AssetFileType
  activity: '' | 'generated' | 'uploaded' | 'liked' | 'downloaded'
  dates: string[] | null
  includeDescendants: boolean
}
const props = defineProps<{ filters: AssetFilterValues; conditions: string[]; folder: boolean; compact?: boolean; loading: boolean; itemCount: number }>()
const emit = defineEmits<{ apply: [value: AssetFilterValues]; refresh: []; selectAll: [] }>()
const layout = defineModel<'square' | 'masonry'>('layout', { required: true })
const cardSize = defineModel<number>('cardSize', { required: true })
const splitByDate = defineModel<boolean>('splitByDate', { required: true })
const filterOpen = ref(false), viewOpen = ref(false)
const emptyFilters = (): AssetFilterValues => ({ search: '', fileType: '', activity: '', dates: null, includeDescendants: true })
const draft = ref<AssetFilterValues>(emptyFilters())
const { start: scheduleSearch, stop: cancelSearch, isPending: searchPending } = useTimeoutFn(() => apply(), 350, { immediate: false })
watch(() => JSON.stringify(props.filters), () => {
  const value = props.filters
  cancelSearch()
  draft.value = { ...value, dates: value.dates ? [...value.dates] : null }
})
function resetFilters() {
  draft.value = emptyFilters()
  apply()
}
function openFilter(open: boolean) {
  if (!open && searchPending.value) apply()
  filterOpen.value = open
  if (open) {
    viewOpen.value = false
    draft.value = { ...props.filters, dates: props.filters.dates ? [...props.filters.dates] : null }
  }
}
function apply() {
  cancelSearch()
  emit('apply', { ...draft.value, search: draft.value.search.trim(), dates: draft.value.dates ? [...draft.value.dates] : null })
}
</script>

<template>
  <StudioPopover :visible="filterOpen" placement="bottom-end" :width="352" popper-class="library-control-panel" @update:visible="openFilter">
    <template #reference><span class="library-filter-anchor"><ElTooltip :disabled="filterOpen || !conditions.length" :show-after="250" placement="bottom-end" popper-class="library-filter-summary">
      <template #content><strong>当前筛选</strong><ul><li v-for="condition in conditions" :key="condition">{{ condition }}</li></ul></template>
      <Button variant="outline" aria-label="筛选素材" :class="{ 'library-filter-active': conditions.length > 0 }"><IconFilter :size="16" />筛选<span v-if="conditions.length" class="asset-filter-count">{{ conditions.length }}</span></Button>
    </ElTooltip></span></template>
    <form class="library-filter-form" @submit.prevent="apply">
      <label class="library-field"><span>素材名称</span><ElInput v-model="draft.search" aria-label="素材名称" placeholder="输入名称关键词" clearable maxlength="200" @input="scheduleSearch()" @clear="apply" /></label>
      <div class="library-field-row">
        <div class="library-field"><span>素材类型</span><ElSelect v-model="draft.fileType" @change="apply" aria-label="素材类型" placeholder="全部类型" :teleported="false"><ElOption label="全部类型" value="" /><ElOption label="图片" value="image" /><ElOption label="视频" value="video" /></ElSelect></div>
        <div class="library-field"><span>素材来源</span><ElSelect v-model="draft.activity" @change="apply" aria-label="素材来源" placeholder="全部" :teleported="false"><ElOption label="全部" value="" /><ElOption label="AI 生成" value="generated" /><ElOption label="手动上传" value="uploaded" /></ElSelect></div>
      </div>
      <div class="library-field"><span>创建日期</span><ElDatePicker v-model="draft.dates" @change="apply" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" aria-label="素材创建日期" :teleported="false" /></div>
      <ElCheckbox v-if="folder" v-model="draft.includeDescendants" @change="apply">包含子文件夹素材</ElCheckbox>
      <footer><Button type="button" variant="ghost" class="library-neutral-button" @click="resetFilters">重置筛选</Button><span class="library-filter-feedback" role="status">{{ loading ? '正在筛选…' : searchPending ? '等待输入完成…' : '条件自动生效' }}</span></footer>
    </form>
  </StudioPopover>
  <StudioPopover v-model:visible="viewOpen" placement="bottom-end" :width="304" popper-class="library-control-panel" @update:visible="open => { if (open) filterOpen = false }">
    <template #reference><Button variant="outline" aria-label="素材视图"><IconLayoutGrid :size="16" />视图</Button></template>
    <div class="library-view-form">
      <div class="library-field"><span>排列方式</span><div class="library-layout-options" role="group" aria-label="素材布局">
        <button type="button" :aria-pressed="layout === 'square'" @click="layout = 'square'"><IconLayoutGrid :size="20" />{{ compact ? '等高画廊' : '方形网格' }}</button>
        <button type="button" :aria-pressed="layout === 'masonry'" @click="layout = 'masonry'"><IconLayoutColumns :size="20" />瀑布流</button>
      </div></div>
      <div class="library-field"><span>缩略图大小</span><div class="library-size-control"><span>小</span><Slider :model-value="[cardSize]" :min="1" :max="8" :step="1" aria-label="缩略图大小" @update:model-value="value => { if (value?.[0]) cardSize = value[0] }" /><span>大</span></div></div>
      <ElCheckbox v-model="splitByDate">按日期分组</ElCheckbox>
      <slot name="preference" />
    </div>
  </StudioPopover>
  <DropdownMenu :modal="false" @update:open="open => { if (open) { filterOpen = false; viewOpen = false } }">
    <DropdownMenuTrigger as-child><Button variant="outline" aria-label="素材更多操作"><IconDots :size="16" /></Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="library-more-menu">
      <DropdownMenuItem :disabled="loading" @select="emit('refresh')"><IconRefresh :size="16" />刷新素材</DropdownMenuItem>
      <DropdownMenuItem :disabled="loading || !itemCount" @select="emit('selectAll')"><IconCheckbox :size="16" />选择当前页<span class="library-menu-count">{{ itemCount }} 项</span></DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
