<script setup>
import { useExchangeRateEditor } from '@/composables/studio/useExchangeRateEditor'
const emit = defineEmits(['saved'])
const { canCreate, canPublish, open, pending, target, error, formRef, form, start, close, submit } =
  useExchangeRateEditor(() => emit('saved'))
defineExpose({ start, canCreate, canPublish })
</script>
<template>
  <el-dialog
    :model-value="open"
    :title="target ? '发布汇率版本' : '登记汇率草稿'"
    width="min(640px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    destroy-on-close
    @close="close"
  >
    <p v-if="target">
      版本 {{ target.id }} · 修订 {{ target.revision }}：1 {{ target.baseCurrency }} =
      {{ target.rate }} {{ target.quoteCurrency }}。生效区间 {{ target.validFrom }} 至
      {{ target.validUntil || '无结束时间' }}。发布后不可修改。
    </p>
    <p v-else>登记有来源依据的汇率，不自动抓取市场报价。1单位基准币兑换所填数量的报价币。</p>
    <el-form
      ref="formRef"
      :model="form"
      :disabled="pending"
      label-position="top"
    >
      <el-form-item
        v-if="target"
        label="发布原因"
        prop="reason"
        :rules="[{ required: true, whitespace: true, message: '请填写发布原因' }]"
        ><el-input
          v-model="form.reason"
          type="textarea"
          maxlength="4000"
      /></el-form-item>
      <template v-else>
        <el-form-item label="基准币"
          ><el-input
            v-model="form.baseCurrency"
            maxlength="3"
            placeholder="例如 USD"
        /></el-form-item>
        <el-form-item label="报价币"
          ><el-input
            v-model="form.quoteCurrency"
            maxlength="3"
            placeholder="例如 CNY"
        /></el-form-item>
        <el-form-item label="汇率"
          ><el-input
            v-model="form.rate"
            placeholder="最多12位小数"
        /></el-form-item>
        <el-form-item label="来源证据ID"><el-input v-model="form.sourceId" /></el-form-item>
        <el-form-item label="生效起点（上海时间）"
          ><el-date-picker
            v-model="form.validFrom"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
        /></el-form-item>
        <el-form-item label="生效终点（可选，上海时间）"
          ><el-date-picker
            v-model="form.validUntil"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
        /></el-form-item>
      </template>
    </el-form>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    />
    <template #footer
      ><el-button
        :disabled="pending"
        @click="close"
        >取消</el-button
      ><el-button
        type="primary"
        :loading="pending"
        :disabled="target ? !canPublish : !canCreate"
        @click="submit"
        >{{ target ? '发布汇率' : '登记草稿' }}</el-button
      ></template
    >
  </el-dialog>
</template>
