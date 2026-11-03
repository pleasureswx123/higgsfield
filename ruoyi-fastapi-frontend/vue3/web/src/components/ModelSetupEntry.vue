<script setup>
import { useRouter } from 'vue-router'
const router = useRouter()
</script>
<template>
  <div class="setup-entry">
    <div><strong>供应商配置一次，多个模型分别管理</strong><p>返回模型列表，选择要配置的模型。已有连接、密钥、价格和测试记录保留。</p></div>
    <el-button type="primary" @click="router.push('/studio/provider-connections')">返回供应商与模型</el-button>
  </div>
</template>
<style scoped>
.setup-entry { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; padding: 18px; margin-bottom: 24px; border: 1px solid var(--el-border-color-light); border-radius: 10px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
p { margin: 8px 0 0; color: var(--el-text-color-secondary); line-height: 1.6; }
</style>
