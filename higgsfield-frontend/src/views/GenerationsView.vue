<script setup lang="ts">
import GenerationCollection from '@/components/projects/GenerationCollection.vue'
</script>
<template>
  <section class="projects-page">
    <div class="project-page-heading">
      <div>
        <h1>我的生成记录</h1>
        <p class="muted">跨项目查看你本人发起的 AI 生成任务与结果，仅展示当前有权访问的记录。</p>
      </div>
    </div>
    <GenerationCollection />
  </section>
</template>
