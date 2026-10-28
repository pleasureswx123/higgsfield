<script setup lang="ts">
import { useRoute } from 'vue-router'
import { IconLayoutGrid } from '@tabler/icons-vue'
const route = useRoute()
</script>
<template>
  <section class="workspace-page">
    <h1>{{ route.meta.title }}</h1>
    <p class="muted">{{ route.meta.description }}</p>
    <div class="project-placeholder">
      <IconLayoutGrid :size="34" />
      <h2>工作空间已就绪</h2>
      <p>此模块将在下一阶段接入，当前暂无可操作的业务功能。</p>
      <RouterLink to="/home" class="text-button">返回首页</RouterLink>
    </div>
  </section>
</template>
