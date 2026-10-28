<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ref } from 'vue'
import { IconFolderPlus, IconChevronRight } from '@tabler/icons-vue'
import { useProjects } from '@/composables/useProjects'
import ProjectCard from './ProjectCard.vue'
import CreateProjectDialog from './CreateProjectDialog.vue'
import Button from '@/components/ui/Button.vue'
const { rows, loading, error, canCreate, load } = useProjects(true)
const open = ref(false),
  router = useRouter()
function created(id: string) {
  void router.push(`/projects/${id}`)
}
</script>
<template>
  <section class="projects-section">
    <div class="section-heading">
      <h2>我的项目</h2>
      <RouterLink to="/projects">查看全部<IconChevronRight :size="16" /></RouterLink>
    </div>
    <p v-if="error" class="project-error" role="alert">
      {{ error }} <Button variant="ghost" @click="load">重试</Button>
    </p>
    <p v-else-if="loading" class="muted" role="status">正在加载项目…</p>
    <div v-else class="project-grid">
      <button v-if="canCreate" class="new-project-card" @click="open = true">
        <span><IconFolderPlus :size="32" /></span><strong>新建项目</strong></button
      ><ProjectCard v-for="project in rows" :key="project.id" :project="project" />
    </div>
    <p v-if="!loading && !error && !rows.length" class="project-empty-note">
      你还没有参与的项目。{{
        canCreate ? '新建一个项目，开始组织你的创作。' : '请联系项目负责人添加成员权限。'
      }}
    </p>
    <CreateProjectDialog v-model="open" @created="created" />
  </section>
</template>
