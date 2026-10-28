<script setup lang="ts">
import UsageSummaryPanel from '@/components/projects/UsageSummaryPanel.vue'
</script>
<template>
  <section class="projects-page">
    <div class="project-page-heading">
      <div>
        <h1>我的用量</h1>
        <p class="muted">查看本人生成任务的平台费用和已知用量。</p>
      </div>
    </div>
    <UsageSummaryPanel />
  </section>
</template>
