<script setup>
import { usePriceVersionEditor } from '@/composables/studio/usePriceVersionEditor'
import { emptyPriceItem } from '@/utils/priceVersion'
const emit = defineEmits(['saved'])
const { canWrite, open, pending, error, model, editing, formRef, form, start, close, submit } =
  usePriceVersionEditor(() => emit('saved'))
defineExpose({ start })
</script>
<template>
  <el-dialog
    :model-value="open"
    :title="editing ? '编辑价格草稿' : '新建价格草稿'"
    width="min(1100px, 96vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    destroy-on-close
    @close="close"
  >
    <p>
      {{ model?.name }} ·
      {{
        model?.currency
      }}。保存草稿不会发布价格。允许先保存未完整配置的草稿，发布前须解决服务端校验问题。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :disabled="pending"
      label-position="top"
    >
      <el-form-item label="计算小数位（四舍五入）"
        ><el-input-number
          v-model="form.calculationScale"
          :min="0"
          :max="10"
          :precision="0"
      /></el-form-item>
      <el-form-item label="来源证据ID（逗号或空格分隔）"
        ><el-input
          v-model="form.sourceIds"
          type="textarea"
      /></el-form-item>
      <el-card
        v-for="(item, index) in form.items"
        :key="index"
        shadow="never"
        class="price-item"
      >
        <div class="fields">
          <el-form-item label="计价分项编码"
            ><el-input
              v-model="item.itemCode"
              placeholder="例如 image_count"
          /></el-form-item>
          <el-form-item label="单位"
            ><el-select v-model="item.unit"
              ><el-option
                label="Token"
                value="token" /><el-option
                label="张"
                value="image" /><el-option
                label="秒"
                value="second" /><el-option
                label="字符"
                value="character" /></el-select
          ></el-form-item>
          <el-form-item label="公式"
            ><el-select v-model="item.formulaTemplate"
              ><el-option
                label="线性"
                value="linear" /><el-option
                label="阶梯"
                value="tiered" /></el-select
          ></el-form-item>
          <el-form-item label="单价基数"><el-input v-model="item.unitQuantity" /></el-form-item>
          <el-form-item label="单价"
            ><el-input
              v-model="item.unitPrice"
              placeholder="最多10位小数"
          /></el-form-item>
          <el-form-item label="阶梯起点"><el-input v-model="item.quantityFrom" /></el-form-item>
          <el-form-item label="阶梯上限（留空无上限）"
            ><el-input v-model="item.quantityTo"
          /></el-form-item>
        </div>
        <el-form-item label="免费依据（零价必填）"
          ><el-input
            v-model="item.freeReason"
            type="textarea"
            maxlength="4000"
        /></el-form-item>
        <el-button
          text
          type="danger"
          @click="form.items.splice(index, 1)"
          >移除此分项</el-button
        >
      </el-card>
      <el-button
        :disabled="form.items.length >= 1000"
        @click="form.items.push(emptyPriceItem())"
        >添加计价分项</el-button
      >
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
        :disabled="!canWrite"
        @click="submit"
        >保存草稿</el-button
      ></template
    >
  </el-dialog>
</template>
<style scoped>
.price-item {
  margin-bottom: 16px;
}
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.el-alert {
  margin-top: 16px;
}
</style>
