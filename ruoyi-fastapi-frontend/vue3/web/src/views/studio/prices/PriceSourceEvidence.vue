<script setup>
import { usePriceSource } from '@/composables/studio/usePriceSource'
const props = defineProps({ sourceIds: { type: Array, required: true } })
const { allowed, selectedId, source, loading, downloading, error, select, clear, download } = usePriceSource(
  () => props.sourceIds
)
const types = {
  vendor_document: '供应商文档',
  official_screenshot: '官方截图',
  manual_confirmation: '人工确认',
}
</script>
<template>
  <section aria-label="价格来源证据">
    <h4>来源证据</h4>
    <p v-if="!sourceIds.length">尚未绑定来源证据</p>
    <el-button
      v-for="id in sourceIds"
      :key="id"
      text
      :disabled="!allowed"
      :type="selectedId === id ? 'primary' : 'default'"
      @click="select(id)"
      >来源 {{ id }}</el-button
    >
    <div v-loading="loading">
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
      />
      <el-card
        v-if="source"
        shadow="never"
      >
        <header>
          <strong>{{ types[source.sourceType] || source.sourceType }} · {{ source.id }}</strong
          ><el-button
            text
            @click="clear"
            >收起</el-button
          >
        </header>
        <p>获取时间：{{ source.observedAt }}</p>
        <p>出处地址：{{ source.sourceUrl || '未提供' }}</p>
        <pre>{{ source.excerpt }}</pre>
        <div v-if="source.attachment">
          <p>附件：{{ source.attachment.fileName }} · {{ source.attachment.byteSize }} 字节</p>
          <p>SHA-256：{{ source.attachment.sha256 }}</p>
          <el-button text type="primary" :disabled="!allowed" :loading="downloading" @click="download">下载证据附件</el-button>
        </div>
        <p>此处展示已登记的不可变证据原文，不表示平台已自动核实出处或当前价格。</p>
      </el-card>
    </div>
  </section>
</template>
<style scoped>
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: inherit;
  background: var(--el-fill-color-light);
  padding: 12px;
}
p {
  overflow-wrap: anywhere;
}
</style>
