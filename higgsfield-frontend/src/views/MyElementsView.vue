<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElInput, ElSelect, ElOption, ElPagination, ElCheckbox, ElInputNumber } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import ElementViewCollection from '@/components/projects/ElementViewCollection.vue'
import ElementViewPreference from '@/components/projects/ElementViewPreference.vue'
import type { ElementViewSettings } from '@/api/viewPreferences'
import { useMyElements } from '@/composables/useMyElements'
import { useContentSelection } from '@/composables/useContentSelection'
import { useElementGenerationEntry } from '@/composables/useElementGenerationEntry'
import type { ElementRecord } from '@/api/elements'
import '@/styles/elements.css'
const {
  mineFilter,
  hasFilters,
  filteredResult,
  clearFilters,
  rows,
  total,
  page,
  search,
  category,
  workStatus,
  statusGroup,
  loading,
  error,
  refresh,
  filter,
} = useMyElements()
const generationEntry = useElementGenerationEntry()
const selection = useContentSelection(
  () => rows.value,
  () => loading.value || generationEntry.pending.value,
)
const chosen = computed(() => rows.value.find((item) => selection.selected.value.includes(item.id)))
function generateImage() {
  if (selection.selected.value.length === 1 && chosen.value)
    void generationEntry.start(chosen.value)
}
const layout = ref<'grid' | 'board' | 'table'>('grid')
const cardSize = ref(4),
  splitByDate = ref(false)
const settings = computed<ElementViewSettings>(() => ({
  mineFilter: mineFilter.value,
  layout: layout.value,
  cardSize: cardSize.value,
  splitByDate: splitByDate.value,
  category: category.value || null,
  workStatus: workStatus.value || null,
  statusGroup: statusGroup.value || null,
}))
const statuses = {
  none: '未开始',
  working: '制作中',
  review: '待审核',
  approved: '已通过',
  rejected: '已退回',
}
function restoreView(value: ElementViewSettings) {
  mineFilter.value = 'created'
  layout.value = value.layout
  cardSize.value = value.cardSize
  splitByDate.value = value.splitByDate
  category.value = value.category || ''
  workStatus.value = value.workStatus || ''
  statusGroup.value = value.statusGroup || ''
  filter()
}
const categories = { character: '角色', scene: '场景', prop: '道具', other: '其他' }
const router = useRouter()
function open(element: ElementRecord) {
  void router.push({
    name: 'project-detail',
    params: { id: element.projectId },
    query: { tab: 'elements', element: element.id },
  })
}
</script>
<template>
  <section class="projects-page element-workspace">
    <div class="project-page-heading">
      <div>
        <h1>我创建的元素</h1>
        <p class="muted">跨项目查看你本人创建的角色、场景、道具等可复用元素，仅展示当前有权访问的内容。</p>
      </div>
      <Button variant="ghost" :disabled="loading" @click="refresh">刷新</Button>
    </div>
    <div class="element-toolbar" :inert="generationEntry.pending.value">
      <ElInput
        v-model="search"
        placeholder="搜索名称或别名"
        clearable
        maxlength="200"
        @keyup.enter="filter"
        @clear="filter"
      />
      <ElSelect v-model="category" placeholder="全部分类" aria-label="元素分类" @change="filter"
        ><ElOption label="全部分类" value="" /><ElOption
          v-for="(label, value) in categories"
          :key="value"
          :label="label"
          :value="value"
      /></ElSelect>
      <ElSelect
        v-model="statusGroup"
        placeholder="全部状态组"
        aria-label="元素状态组"
        @change="filter"
      >
        <ElOption label="全部状态组" value="" /><ElOption
          label="Active（已通过）"
          value="active"
        /><ElOption label="Drafts（草稿）" value="drafts" />
      </ElSelect>
      <ElSelect
        v-model="workStatus"
        placeholder="全部工作状态"
        aria-label="元素工作状态"
        @change="filter"
      >
        <ElOption label="全部工作状态" value="" /><ElOption
          v-for="(label, value) in statuses"
          :key="value"
          :label="label"
          :value="value"
        />
      </ElSelect>
      <Button variant="ghost" @click="filter">搜索</Button>
      <Button
        v-if="hasFilters"
        variant="ghost"
        :disabled="generationEntry.pending.value"
        @click="clearFilters"
        >清除筛选</Button
      >
      <ElSelect v-model="layout" aria-label="元素布局"
        ><ElOption label="网格" value="grid" /><ElOption label="看板" value="board" /><ElOption
          label="表格"
          value="table"
      /></ElSelect>
      <ElCheckbox v-model="splitByDate">按日期分组</ElCheckbox>
      <label
        >卡片尺寸
        <ElInputNumber
          v-model="cardSize"
          :min="1"
          :max="8"
          :precision="0"
          :disabled="layout === 'table'"
          aria-label="元素卡片尺寸"
      /></label>
    </div>
    <ElementViewPreference :settings="settings" @restore="restoreView" />
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载元素…</p>
    <div class="element-toolbar">
      <Button
        :disabled="
          loading ||
          generationEntry.pending.value ||
          selection.selected.value.length !== 1 ||
          (chosen?.allowedActions !== undefined && !chosen.allowedActions.includes('element:edit'))
        "
        @click="generateImage"
        >{{ generationEntry.pending.value ? '正在核验目标…' : '为所选元素生成图片' }}</Button
      >
      <span class="muted">选择一个目标元素，进入其项目创作区；此操作不发起生成。</span>
    </div>
    <p v-if="generationEntry.error.value" class="project-error" role="alert">
      {{ generationEntry.error.value }}
    </p>
    <div v-if="!loading && !error && !rows.length" class="muted" role="status">
      <p>
        {{
          filteredResult
            ? '没有符合当前筛选的元素，可清除筛选后重试。'
            : '当前没有可查看的创建元素。可进入有权限的项目创建元素。'
        }}
      </p>
    </div>
    <ElementViewCollection
      v-if="!loading && rows.length"
      selectable
      :selected="selection.selected.value"
      :selection-disabled="generationEntry.pending.value"
      @select="selection.toggle"
      :rows="rows"
      :layout="layout"
      :card-size="cardSize"
      :split-by-date="splitByDate"
      show-project
      @open="!generationEntry.pending.value && open($event)"
    />
    <ElPagination
      v-if="total > 30"
      v-model:current-page="page"
      :disabled="generationEntry.pending.value"
      :page-size="30"
      :total="total"
      layout="prev, pager, next"
    />
  </section>
</template>
