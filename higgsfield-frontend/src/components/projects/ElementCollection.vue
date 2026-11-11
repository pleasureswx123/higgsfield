<script setup lang="ts">
import ReferenceThumbnail from './ReferenceThumbnail.vue'
import { computed } from 'vue'
import { IconPhoto } from '@tabler/icons-vue'
import { ElCheckbox } from 'element-plus'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { ElementRecord } from '@/api/elements'
const props = defineProps<{
  rows: ElementRecord[]
  layout: 'grid' | 'board' | 'table'
  showProject?: boolean
  selectable?: boolean
  selected?: string[]
  selectionDisabled?: boolean
}>()
const emit = defineEmits<{ open: [element: ElementRecord]; select: [id: string, checked: boolean]; preview: [versionId: string] }>()
const categoryNames = { character: '角色', scene: '场景', prop: '道具', other: '其他' }
const statusNames = {
  none: '未开始',
  working: '制作中',
  review: '待审核',
  approved: '已通过',
  rejected: '待修改',
}
const columns = computed(() =>
  Object.entries(statusNames).map(([status, title]) => ({
    status,
    title,
    rows: props.rows.filter((row) => row.workStatus === status),
  })),
)
const textColumns = computed(() => [
  { key: 'name', title: '名称', width: 180, value: (row: ElementRecord) => row.name },
  ...(props.showProject ? [{ key: 'project', title: '项目', width: 140, value: (row: ElementRecord) => row.projectName || '' }] : []),
  { key: 'category', title: '分类', width: 100, value: (row: ElementRecord) => categoryNames[row.category] },
  { key: 'alias', title: '元素 ID', width: 140, value: (row: ElementRecord) => `@${row.alias}` },
  { key: 'description', title: '描述', width: 220, value: (row: ElementRecord) => row.description || '' },
  { key: 'label', title: '版本', width: 130, value: (row: ElementRecord) => row.label || '—' },
  { key: 'performer', title: '制作人', width: 150, value: (row: ElementRecord) => row.performerName || (row.performerId ? `成员 ${row.performerId}` : '未分配') },
  { key: 'status', title: '状态', width: 110, value: (row: ElementRecord) => statusNames[row.workStatus] },
])
const tableWidth = computed(() => 328 + textColumns.value.reduce((sum, column) => sum + column.width, 0))
</script>
<template>
  <div v-if="layout === 'table'" class="element-table-scroll">
    <TooltipProvider :delay-duration="300">
      <Table class="element-table" :style="{ minWidth: `${tableWidth}px` }" aria-label="元素列表">
        <colgroup>
          <col style="width: 48px" />
          <col style="width: 280px" />
          <col v-for="column in textColumns" :key="column.key" :style="{ width: `${column.width}px` }" />
        </colgroup>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">#</TableHead>
            <TableHead scope="col">图片</TableHead>
            <TableHead v-for="column in textColumns" :key="column.key" scope="col">{{ column.title }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="(row, index) in rows" :key="row.id" :data-state="selected?.includes(row.id) ? 'selected' : undefined">
            <TableCell class="element-index-cell">
              <span class="element-row-index">{{ index + 1 }}</span>
              <Checkbox v-if="selectable" class="element-row-select" :model-value="selected?.includes(row.id) || false" :aria-label="`选择元素 ${row.name}`" :disabled="selectionDisabled" @update:model-value="emit('select', row.id, $event === true)" />
            </TableCell>
            <TableCell class="element-media-cell">
              <div class="element-table-media">
                <template v-if="row.media?.length">
                  <button v-for="media in row.media.slice(0, 3)" :key="media.assetVersionId" type="button" class="element-media-preview" :aria-label="`查看素材详情 ${row.name}`" title="查看素材详情" @click.stop="emit('preview', media.assetVersionId)">
                    <ReferenceThumbnail :version-id="media.assetVersionId" fill passive allow-original :alt="row.name" />
                  </button>
                </template>
                <button v-else-if="row.media === undefined" type="button" class="element-empty-media" :aria-label="`查看元素素材 ${row.name}`" @click="emit('open', row)"><IconPhoto :size="20" />查看元素素材</button>
                <button v-else type="button" class="element-empty-media" :aria-label="`查看元素 ${row.name}`" @click="emit('open', row)"><span v-if="row.allowedActions?.includes('element:edit')">＋</span>{{ row.allowedActions?.includes('element:edit') ? '添加元素图片' : '暂无参考素材' }}</button>
              </div>
            </TableCell>
            <TableCell v-for="column in textColumns" :key="column.key" :class="{ 'cursor-pointer': column.key === 'name' }" @click="column.key === 'name' && emit('open', row)">
              <Tooltip v-if="column.value(row)">
                <TooltipTrigger as-child>
                  <button v-if="column.key === 'name'" type="button" class="folder-text-button element-cell-text" :aria-label="`查看元素 ${row.name}`" title="查看元素详情" @click.stop="emit('open', row)">{{ column.value(row) }}</button>
                  <span v-else class="element-cell-text" tabindex="0">{{ column.value(row) }}</span>
                </TooltipTrigger>
                <TooltipContent class="element-cell-tooltip">{{ column.value(row) }}</TooltipContent>
              </Tooltip>
            </TableCell>
          </TableRow>
          <TableRow v-if="!rows.length"><TableCell :colspan="textColumns.length + 2" class="element-table-empty">暂无匹配的元素</TableCell></TableRow>
        </TableBody>
      </Table>
    </TooltipProvider>
  </div>
  <template v-else-if="layout === 'board'"
    ><p class="muted">按状态分组展示当前页元素，列内数量为当前页数量。</p>
    <div class="element-board">
      <section v-for="column in columns" :key="column.status" class="element-board-column">
        <h3>
          {{ column.title }} <span class="muted">{{ column.rows.length }}</span>
        </h3>
        <div v-for="element in column.rows" :key="element.id" class="element-select-card">
          <ElCheckbox v-if="selectable" :model-value="selected?.includes(element.id) || false" :aria-label="`选择元素 ${element.name}`" :disabled="selectionDisabled" @change="emit('select', element.id, Boolean($event))">选择</ElCheckbox>
          <button class="element-card"
          @click="emit('open', element)"
        >
          <strong>{{ element.name }}</strong
          ><small class="muted">@{{ element.alias }}</small
          ><small v-if="showProject" class="muted">{{ element.projectName }}</small>
          <p class="element-card-description">{{ element.description || '未填写描述' }}</p>
          <span class="element-card-meta"
            >{{ categoryNames[element.category] }} · {{ element.label || '无标签' }}</span
          >
        </button></div>
        <p v-if="!column.rows.length" class="muted">当前页无此状态元素</p>
      </section>
    </div></template
  >
  <div v-else class="element-grid">
    <div v-for="element in rows" :key="element.id" class="element-select-card">
          <ElCheckbox v-if="selectable" :model-value="selected?.includes(element.id) || false" :aria-label="`选择元素 ${element.name}`" :disabled="selectionDisabled" @change="emit('select', element.id, Boolean($event))">选择</ElCheckbox>
          <button class="element-card"
      @click="emit('open', element)"
    >
      <div class="element-card-image"><ReferenceThumbnail v-if="element.media?.length" :version-id="element.media[0]!.assetVersionId" fill passive allow-original :alt="element.name" /><template v-else><IconPhoto :size="40" /><span>查看元素</span></template></div>
      <strong>{{ element.name }}</strong
      ><small class="muted">@{{ element.alias }}</small
      ><small v-if="showProject" class="muted">{{ element.projectName }}</small>
      <div class="element-card-meta">
        <span>{{ categoryNames[element.category] }}</span
        ><span>{{ statusNames[element.workStatus] }}</span>
      </div>
    </button></div>
    <p v-if="!rows.length" class="muted">暂无匹配的元素。</p>
  </div>
</template>


<style scoped>
.element-select-card { min-width: 0; }
.element-select-card > .element-card { width: 100%; }
</style>
