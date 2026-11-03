<script setup>
import { ref, nextTick } from 'vue'
import { useModelTestHistory } from '@/composables/studio/useModelTestHistory'
import TestEvidence from '../setup/TestEvidence.vue'
const { open, loading, error, records, model, show, close } = useModelTestHistory()
const selected = ref(), evidence = ref()
async function view(row) { selected.value = row; await nextTick(); evidence.value?.show() }
function start(row, connection) { selected.value = undefined; show(row, connection) }
function dismiss() { selected.value = undefined; close() }
const states = { pending: '进行中', passed: '测试通过', failed: '测试失败' }
const time = value => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
defineExpose({ show: start })
</script>
<template>
  <el-drawer :model-value="open" :title="`${model?.displayName || ''} · 测试记录`" size="min(900px, 95vw)" append-to-body @close="dismiss">
    <p>查看已有测试不会调用供应商，也不会产生新费用。时间为北京时间。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table :data="records" v-loading="loading" empty-text="此模型暂无测试记录，请在配置模型中发起测试。">
      <el-table-column label="测试时间" min-width="190"><template #default="{ row }">{{ time(row.createTime) }}</template></el-table-column>
      <el-table-column label="状态" width="110"><template #default="{ row }">{{ states[row.state] }}</template></el-table-column>
      <el-table-column prop="id" label="测试编号" width="100" />
      <el-table-column label="操作" width="110"><template #default="{ row }"><el-button link type="primary" @click="view(row)">查看详情</el-button></template></el-table-column>
    </el-table>
    <TestEvidence v-if="selected && open" ref="evidence" :test-id="selected.id" :kind="model.kind" hide-entry />
    <template #footer><el-button @click="dismiss">关闭</el-button></template>
  </el-drawer>
</template>
