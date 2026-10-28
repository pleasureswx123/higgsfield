<script setup lang="ts">
import { IconFolder, IconArrowUpRight } from '@tabler/icons-vue'
import type { Project } from '@/api/projects'
import { projectRoleLabels, projectStatusLabels, formatProjectDate } from '@/utils/projects'
defineProps<{ project: Project }>()
</script>
<template>
  <RouterLink :to="`/projects/${project.id}`" class="project-card"
    ><div class="project-card-cover">
      <IconFolder :size="42" stroke="1.2" /><span>{{ projectStatusLabels[project.status] }}</span
      ><IconArrowUpRight class="project-card-arrow" :size="19" />
    </div>
    <div class="project-card-title">
      <strong :title="project.name">{{ project.name }}</strong
      ><small>{{ projectRoleLabels[project.currentUserRole] || project.currentUserRole }}</small>
    </div>
    <time :datetime="project.createTime">{{
      formatProjectDate(project.createTime)
    }}</time></RouterLink
  >
</template>
