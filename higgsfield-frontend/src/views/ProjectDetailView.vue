<script setup lang="ts">
import { IconArrowLeft, IconFolder } from '@tabler/icons-vue'
import { useProjectDetail } from '@/composables/useProjects'
import { formatProjectDate, projectStatusLabels } from '@/utils/projects'
import Button from '@/components/ui/Button.vue'
import ProjectWorkspace from '@/components/projects/ProjectWorkspace.vue'
const { project, loading, error, load, acceptProject } = useProjectDetail()
</script>
<template>
  <section class="project-detail-page project-studio-page">
    <RouterLink to="/projects" class="project-back"
      ><IconArrowLeft :size="18" />我的项目</RouterLink
    >
    <p v-if="loading" class="project-loading" role="status">正在加载项目…</p>
    <div v-else-if="error" class="project-error" role="alert">
      <p>{{ error }}</p>
      <Button variant="outline" @click="load">重新加载</Button>
    </div>
    <template v-else-if="project"
      ><header class="project-detail-header">
        <div class="project-detail-symbol"><IconFolder :size="38" /></div>
        <div>
          <span class="eyebrow">项目空间</span>
          <h1>{{ project.name }}</h1>
          <p>创建于 {{ formatProjectDate(project.createTime) }}</p>
        </div>
        <span class="project-status">{{ projectStatusLabels[project.status] }}</span>
      </header>
      <ProjectWorkspace :key="project.id" :project-id="project.id" :project="project" @changed="acceptProject"
    /></template>
  </section>
</template>
