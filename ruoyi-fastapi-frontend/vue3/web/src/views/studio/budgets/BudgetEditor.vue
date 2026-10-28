<script setup>
import { useBudgetEditor } from '@/composables/studio/useBudgetEditor'
const emit = defineEmits(['saved'])
const { canWrite, open, pending, error, editing, formRef, form, start, close, submit } =
  useBudgetEditor(() => emit('saved'))
defineExpose({ start })
const rules = {
  subjectId: [
    {
      required: true,
      validator: (_rule, value, callback) =>
        callback(
          /^[1-9]\d{0,18}$/.test(value) && BigInt(value) <= 9223372036854775807n
            ? undefined
            : new Error('请输入有效的主体ID')
        ),
      trigger: 'blur',
    },
  ],
  currency: [
    { required: true, pattern: /^[A-Z]{3}$/, message: '请输入三位大写币种代码', trigger: 'blur' },
  ],
  businessTimezone: [
    {
      required: true,
      validator: (_rule, value, callback) => {
        try {
          if (!value.trim()) throw new Error()
          new Intl.DateTimeFormat('zh-CN', { timeZone: value.trim() })
          callback()
        } catch {
          callback(new Error('请输入有效的IANA时区，例如 Asia/Shanghai'))
        }
      },
      trigger: 'blur',
    },
  ],
}
</script>
<template>
  <el-dialog
    :model-value="open"
    :title="editing ? (editing.active ? '停用预算' : '启用预算') : '创建预算'"
    width="min(560px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    @close="close"
    destroy-on-close
  >
    <template v-if="editing">
      <p>
        将{{ editing.active ? '停用' : '启用' }}预算 {{ editing.id }}（{{
          editing.currency
        }}）。停用不会释放已有任务预占，也不会删除历史周期或账本。
      </p>
    </template>
    <el-form
      v-else
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      :disabled="pending"
    >
      <el-form-item label="主体类型"
        ><el-radio-group v-model="form.subjectType"
          ><el-radio value="project">项目</el-radio
          ><el-radio value="user">用户</el-radio></el-radio-group
        ></el-form-item
      >
      <el-form-item
        label="主体ID"
        prop="subjectId"
        ><el-input v-model="form.subjectId"
      /></el-form-item>
      <el-form-item label="计价口径"
        ><el-radio-group v-model="form.purpose"
          ><el-radio value="platform">平台</el-radio
          ><el-radio value="procurement">采购</el-radio></el-radio-group
        ></el-form-item
      >
      <el-form-item
        label="币种"
        prop="currency"
        ><el-input
          v-model="form.currency"
          maxlength="3"
      /></el-form-item>
      <el-form-item label="周期类型"
        ><el-radio-group v-model="form.cycleKind"
          ><el-radio value="monthly">月度</el-radio
          ><el-radio value="total">总额</el-radio></el-radio-group
        ></el-form-item
      >
      <el-form-item
        label="业务时区"
        prop="businessTimezone"
        ><el-input v-model="form.businessTimezone"
      /></el-form-item>
      <p>创建预算定义后还需初始化周期与额度，才能用于任务预算检查。</p>
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
        :disabled="!canWrite"
        :loading="pending"
        @click="submit"
        >{{ editing ? '确认变更' : '创建预算' }}</el-button
      ></template
    >
  </el-dialog>
</template>
