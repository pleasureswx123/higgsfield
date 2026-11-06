<script setup lang="ts">
defineProps<{ count?: number; error?: string }>()
</script>

<template>
  <span v-if="error || count" class="generation-activity-count" :title="error" role="status">
    {{ error ? (count === undefined ? '状态暂不可用' : `${count} · 更新延迟`) : `进行中 ${count}` }}
  </span>
</template>

<style scoped>
.generation-activity-count { margin-left:auto; max-width:92px; font-size:11px; color:var(--muted-foreground); text-align:right; white-space:normal; }
</style>
