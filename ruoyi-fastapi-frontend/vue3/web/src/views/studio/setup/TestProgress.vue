<script setup>
defineProps({ message: { type: String, default: '正在等待供应商结果…' } })
</script>
<template>
  <div class="test-progress" role="status" aria-live="polite">
    <span class="test-spinner" aria-hidden="true"></span>
    <div><strong>{{ message }}</strong><p>结果会自动更新，无需重复提交。可以关闭详情，稍后回来查看。</p></div>
  </div>
</template>
<style scoped>
.test-progress { display: flex; align-items: center; gap: 12px; padding: 16px; margin: 12px 0; border-radius: 8px; background: var(--el-color-primary-light-9); color: var(--el-text-color-primary); }
p { margin: 6px 0 0; color: var(--el-text-color-secondary); line-height: 1.6; }
.test-spinner { flex-shrink: 0; width: 20px; height: 20px; border: 2px solid var(--el-border-color); border-top-color: var(--el-color-primary); border-radius: 50%; animation: test-spin 1s linear infinite; }
@keyframes test-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .test-spinner { animation: none; } }
</style>
