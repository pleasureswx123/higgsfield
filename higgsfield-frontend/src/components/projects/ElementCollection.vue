<script setup lang="ts">
import { computed } from 'vue'
import { IconPhoto } from '@tabler/icons-vue'
import { ElTable, ElTableColumn, ElCheckbox } from 'element-plus'
import type { ElementRecord } from '@/api/elements'
const props = defineProps<{
  rows: ElementRecord[]
  layout: 'grid' | 'board' | 'table'
  showProject?: boolean
  selectable?: boolean
  selected?: string[]
  selectionDisabled?: boolean
}>()
const emit = defineEmits<{ open: [element: ElementRecord]; select: [id: string, checked: boolean] }>()
const categoryNames = { character: '角色', scene: '场景', prop: '道具', other: '其他' }
const statusNames = {
  none: '未开始',
  working: '制作中',
  review: '待审核',
  approved: '已通过',
  rejected: '已驳回',
}
const columns = computed(() =>
  Object.entries(statusNames).map(([status, title]) => ({
    status,
    title,
    rows: props.rows.filter((row) => row.workStatus === status),
  })),
)
</script>
<template>
  <ElTable
    v-if="layout === 'table'"
    :data="rows"
    row-key="id"
    border
    class="element-table"
    empty-text="暂无匹配的元素"
  >
    <ElTableColumn v-if="selectable" label="选择" width="64">
      <template #default="{ row }"><ElCheckbox :model-value="selected?.includes(row.id) || false" :aria-label="`选择元素 ${row.name}`" :disabled="selectionDisabled" @change="emit('select', row.id, Boolean($event))" /></template>
    </ElTableColumn>
    <ElTableColumn type="index" label="#" width="50" />
    <ElTableColumn label="名称" min-width="180"
      ><template #default="{ row }"
        ><button class="folder-text-button" @click="emit('open', row as ElementRecord)">
          {{ row.name }}
        </button></template
      ></ElTableColumn
    >
    <ElTableColumn
      v-if="showProject"
      prop="projectName"
      label="项目"
      min-width="140"
      show-overflow-tooltip
    />
    <ElTableColumn label="分类" width="100"
      ><template #default="{ row }">{{
        categoryNames[row.category as keyof typeof categoryNames]
      }}</template></ElTableColumn
    >
    <ElTableColumn label="元素别名" min-width="140" show-overflow-tooltip
      ><template #default="{ row }">@{{ row.alias }}</template></ElTableColumn
    >
    <ElTableColumn prop="description" label="描述" min-width="220" show-overflow-tooltip />
    <ElTableColumn label="版本" min-width="130"
      ><template #default="{ row }"
        >{{ row.label || '无标签' }} · #{{ row.revisionNo }}</template
      ></ElTableColumn
    >
    <ElTableColumn label="状态" width="110"
      ><template #default="{ row }">{{
        statusNames[row.workStatus as keyof typeof statusNames]
      }}</template></ElTableColumn
    >
  </ElTable>
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
      <div class="element-card-image"><IconPhoto :size="40" /><span>查看元素</span></div>
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
