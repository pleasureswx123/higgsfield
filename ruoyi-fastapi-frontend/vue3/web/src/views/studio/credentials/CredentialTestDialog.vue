<script setup>
import { useCredentialTest } from '@/composables/studio/useCredentialTest'
const { allowed, open, pending, error, target, receipt, formRef, form, models, centers,
  start, close, load, submit } = useCredentialTest()
defineExpose({ start, open, pending })
const rules = {
  modelVersionId: [{ required: true, message: '请选择图片模型版本', trigger: 'change' }],
  costCenterId: [{ required: true, message: '请选择费用归属', trigger: 'change' }],
  acknowledgePotentialCharge: [{ validator: (_rule, value, callback) => callback(value === true ? undefined : new Error('请确认测试可能产生费用')), trigger: 'change' }],
}
</script>

<template>
  <el-dialog :model-value="open" title="申请凭据测试" width="min(640px, calc(100vw - 24px))" append-to-body
    :close-on-click-modal="false" :close-on-press-escape="!pending" :show-close="!pending" @close="close">
    <p>测试凭据版本 {{ target?.versionNo }}。当前使用单张图片探针，提交后由工作器执行。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" role="alert" />
    <el-alert v-if="receipt" type="success" :closable="false"
      :title="`测试 ${receipt.id} 已受理，等待执行。请在测试历史中刷新诊断；尚未通过或启用。`" />
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="pending || !!receipt || !allowed">
      <el-form-item label="同连接、同区域的图片模型版本" prop="modelVersionId">
        <el-alert v-if="models.error" :title="models.error" type="error" :closable="false" />
        <el-select v-model="form.modelVersionId" :loading="models.loading" placeholder="选择模型版本" style="width:100%">
          <el-option v-for="row in models.rows" :key="row.id" :value="row.id" :label="`${row.name} · V${row.versionNo} · ${row.gatewayAlias}`" />
        </el-select>
        <el-pagination v-model:current-page="models.page" :page-size="20" :total="models.total" layout="total, prev, next"
          :disabled="pending || !!receipt" @current-change="load(models)" />
        <el-button link :disabled="pending || !!receipt" @click="load(models)">刷新模型</el-button>
      </el-form-item>
      <el-form-item label="测试费用归属成本中心" prop="costCenterId">
        <el-alert v-if="centers.error" :title="centers.error" type="error" :closable="false" />
        <el-select v-model="form.costCenterId" :loading="centers.loading" placeholder="选择成本中心" style="width:100%">
          <el-option v-for="row in centers.rows" :key="row.id" :value="row.id" :label="row.name" :disabled="!row.active" />
        </el-select>
        <el-pagination v-model:current-page="centers.page" :page-size="20" :total="centers.total" layout="total, prev, next"
          :disabled="pending || !!receipt" @current-change="load(centers)" />
        <el-button link :disabled="pending || !!receipt" @click="load(centers)">刷新成本中心</el-button>
      </el-form-item>
      <el-form-item prop="acknowledgePotentialCharge">
        <el-checkbox v-model="form.acknowledgePotentialCharge">我确认测试可能产生供应商费用，失败或超时不代表免费。</el-checkbox>
      </el-form-item>
    </el-form>
    <el-alert title="候选模型不代表已验证。若模型要求参考媒体或不支持单张探针，执行时会返回不支持；测试不会自动启用凭据。" type="info" :closable="false" />
    <template #footer>
      <el-button :disabled="pending" @click="close">{{ receipt ? '完成' : '取消' }}</el-button>
      <el-button v-if="!receipt" type="primary" :disabled="!allowed || models.loading || centers.loading" :loading="pending" @click="submit">确认并申请测试</el-button>
    </template>
  </el-dialog>
</template>
