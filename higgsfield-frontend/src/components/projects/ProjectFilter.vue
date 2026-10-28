<script setup lang="ts">
import { ElDialog, ElInput, ElPagination } from 'element-plus'
import type { Project } from '@/api/projects'
import { useProjectFilter } from '@/composables/useProjectFilter'
import Button from '@/components/ui/Button.vue'
import DialogHeading from '@/components/shared/DialogHeading.vue'

const props = withDefaults(defineProps<{ active?: boolean }>(), { active: true })
const selected = defineModel<Project | null>({ required: true })
const { opened, q, page, rows, total, loading, error, search, load } = useProjectFilter(
  () => props.active, () => { selected.value = null },
)
function choose(project: Project) { selected.value = project; opened.value = false }
</script>
<template>
  <div class="project-filter">
    <Button variant="outline" :disabled="!active" @click="opened = true">{{ selected ? `项目：${selected.name}` : '全部项目' }}</Button>
    <Button v-if="selected" variant="ghost" @click="selected = null">清除项目筛选</Button>
    <ElDialog v-model="opened" title="筛选所属项目" width="min(620px, 94vw)" append-to-body destroy-on-close>
      <template #header="{ titleId, titleClass }"><DialogHeading :title-id="titleId" :title-class="titleClass" title="筛选所属项目" /></template>
      <p class="muted">仅列出当前可访问的项目。选择后仍只查询你发起的生成任务。</p>
      <div class="project-filter-search">
        <ElInput v-model="q" aria-label="搜索筛选项目" placeholder="输入项目名称" clearable @keyup.enter="search" @clear="search" />
        <Button variant="ghost" :disabled="loading" @click="search">搜索</Button>
      </div>
      <p v-if="loading" role="status">正在读取项目…</p>
      <p v-else-if="error" class="project-error" role="alert">{{ error }} <Button variant="ghost" @click="load">重试</Button></p>
      <div v-else class="project-filter-options">
        <Button v-for="project in rows" :key="project.id" variant="outline" @click="choose(project)">{{ project.name }} · #{{ project.id }}</Button>
        <p v-if="!rows.length" class="muted">没有匹配的可访问项目。</p>
      </div>
      <ElPagination v-if="total > 10" v-model:current-page="page" :total="total" :page-size="10" :disabled="loading" layout="prev, pager, next" />
    </ElDialog>
  </div>
</template>
<style scoped>
.project-filter, .project-filter-search { display: flex; gap: 8px; align-items: center; }
.project-filter { flex-wrap: wrap; }
.project-filter-search > button { flex-shrink: 0; }
.project-filter-options { display: grid; gap: 10px; margin: 16px 0; }
.project-filter-options > button { white-space: normal; overflow-wrap: anywhere; height: auto; }
</style>
