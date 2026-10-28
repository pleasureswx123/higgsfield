<script setup lang="ts">
import GenerationCollection from '@/components/projects/GenerationCollection.vue'
</script>
<template>
  <section class="projects-page">
    <div class="project-page-heading">
      <div>
        <h1>我的生成</h1>
        <p class="muted">查看你发起且当前仍有项目访问权限的生成记录。</p>
      </div>
    </div>
    <GenerationCollection />
  </section>
</template>
