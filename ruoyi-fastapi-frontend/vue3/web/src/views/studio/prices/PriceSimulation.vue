<script setup>
import { usePriceSimulation } from '@/composables/studio/usePriceSimulation'
import { simulationFields } from '@/utils/priceSimulation'
const props = defineProps({ versionId: { type: String, required: true } })
const { allowed, form, formRef, result, error, pending, submit } = usePriceSimulation(
  () => props.versionId
)
</script>
<template>
  <section>
    <h4>离线价格试算</h4>
    <p>
      试算不会调用供应商或写入账本。规格维度必须与价格簿精确规格完全一致；用量留空表示未知，填写0表示已知为零。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      label-position="top"
      @submit.prevent
    >
      <el-form-item
        label="完整规格维度（JSON对象）"
        prop="dimensions"
        :rules="[{ required: true, message: '请输入完整规格维度' }]"
        ><el-input
          v-model="form.dimensions"
          type="textarea"
          :rows="4"
      /></el-form-item>
      <div class="usage-fields">
        <el-form-item
          v-for="[name, label] in simulationFields"
          :key="name"
          :label="label"
          ><el-input
            v-model="form[name]"
            placeholder="未知则留空"
        /></el-form-item>
      </div>
      <el-form-item label="汇率版本ID（可选，不填则不换算）"
        ><el-input v-model="form.exchangeRateVersionId"
      /></el-form-item>
      <el-button
        :disabled="!allowed"
        :loading="pending"
        @click="submit"
        >试算</el-button
      >
    </el-form>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    />
    <template v-if="result">
      <el-alert
        v-for="(warning, index) in result.warnings"
        :key="index"
        :title="warning"
        type="warning"
        :closable="false"
      />
      <p>
        版本 {{ result.priceVersionId }} · 精确规格 {{ result.matchedVariantId }} · 合计
        {{ result.total }} {{ result.currency }}
      </p>
      <el-table :data="result.lines"
        ><el-table-column
          prop="itemCode"
          label="分项" /><el-table-column
          prop="quantity"
          label="用量" /><el-table-column
          prop="unitQuantity"
          label="基数" /><el-table-column
          prop="unitPrice"
          label="单价" /><el-table-column
          prop="amount"
          label="金额"
      /></el-table>
      <details v-if="result.conversion">
        <summary>汇率换算详情</summary>
        <pre>{{ JSON.stringify(result.conversion, null, 2) }}</pre>
      </details>
    </template>
  </section>
</template>
<style scoped>
.usage-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.el-alert {
  margin-top: 12px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--el-fill-color-light);
  padding: 12px;
}
</style>
