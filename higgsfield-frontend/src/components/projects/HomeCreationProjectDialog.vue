<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElDialog, ElInput, ElPagination } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import type { Project } from '@/api/projects'
defineProps<{
  projects: Project[]
  total: number
  loading: boolean
  saving: boolean
  error: string
}>()
const q = defineModel<string>('q', { required: true })
const page = defineModel<number>('page', { required: true })
const emit = defineEmits<{ close: []; search: []; load: []; choose: [project: Project] }>()
</script>
<template>
  <ElDialog
    :model-value="true"
    title="选择创作项目"
    width="min(620px, 94vw)"
    append-to-body
    :show-close="!saving"
    :close-on-click-modal="false"
    :before-close="
      () => {
        if (!saving) emit('close')
      }
    "
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="选择创作项目" />
    </template>
    <p class="muted">选择项目后配置模型、参考素材和参数，核对预计费用，再确认生成。</p>
    <div class="element-toolbar">
      <ElInput
        v-model="q"
        placeholder="搜索活跃项目"
        aria-label="搜索创作项目"
        :disabled="saving"
        @keyup.enter="emit('search')"
      />
      <Button variant="ghost" :disabled="saving || loading" @click="emit('search')">搜索</Button>
    </div>
    <p v-if="loading" role="status">正在加载项目…</p>
    <div v-else class="home-creation-projects">
      <Button
        v-for="project in projects"
        :key="project.id"
        variant="outline"
        :disabled="saving"
        @click="emit('choose', project)"
        >{{ project.name }}</Button
      >
      <p v-if="!projects.length" class="muted">没有可选择的项目，请先创建项目或加入项目。</p>
    </div>
    <ElPagination
      v-if="total > 10"
      v-model:current-page="page"
      :total="total"
      :page-size="10"
      :disabled="saving || loading"
      layout="prev, pager, next"
      @current-change="emit('load')"
    />
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <template #footer
      ><Button variant="ghost" :disabled="saving" @click="emit('close')"
        >返回修改描述</Button
      ></template
    >
  </ElDialog>
</template>
<style scoped>
.home-creation-projects {
  display: grid;
  gap: 10px;
  margin: 16px 0;
}
</style>
