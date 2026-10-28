<script setup>
import { useCredentialActivation } from '@/composables/studio/useCredentialActivation'
const emit = defineEmits(['activated'])
const { allowed, canActivate, eligible, open, pending, loading, error, target, result, formRef, form,
  history, start, close, inspect, submit, loadHistory, chooseTest } = useCredentialActivation(() => emit('activated'))
defineExpose({ start, open, pending })
const rules = { reason: [{ required: true, whitespace: true, message: '请输入启用原因', trigger: 'blur' }] }
const states = { pending: '待执行', passed: '通过', failed: '失败' }
const costStates = { not_started: '尚未发送', unpriced: '未定价', unknown: '未知', pending: '待定',
  calculated: '已计算（未对账确认）', confirmed: '已确认', disputed: '有争议' }
</script>

<template>
  <el-dialog :model-value="open" title="凭据测试记录" width="min(620px, calc(100vw - 24px))" append-to-body
    :close-on-click-modal="false" :close-on-press-escape="!pending" :show-close="!pending" @close="close">
    <p>凭据版本 {{ target?.versionNo }}。测试成功后仍需明确启用；不会修改旧版本或在途任务的凭据。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" role="alert" />
    <el-alert v-if="history.error" :title="history.error" type="error" :closable="false" role="alert" />
    <el-button :disabled="pending" :loading="history.loading" @click="loadHistory">刷新测试历史</el-button>
    <el-table :data="history.rows" v-loading="history.loading" empty-text="当前凭据版本尚无测试记录">
      <el-table-column prop="id" label="测试编号" min-width="100" />
      <el-table-column label="状态" width="90"><template #default="{ row }">{{ states[row.state] || '未知' }}</template></el-table-column>
      <el-table-column label="申请时间" min-width="160"><template #default="{ row }">{{ new Date(row.createTime).toLocaleString() }}</template></el-table-column>
      <el-table-column label="操作" width="90"><template #default="{ row }">
        <el-button link type="primary" :disabled="pending" @click="chooseTest(row)">查看诊断</el-button>
      </template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="history.page" :page-size="10" :total="history.total"
      :disabled="pending" layout="total, prev, pager, next" @current-change="loadHistory" />
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="pending || !allowed">
      <el-form-item label="测试记录编号">
        <el-input v-model="form.testId" placeholder="输入本凭据版本的测试记录编号" maxlength="19" />
        <el-button :loading="loading" @click="inspect">读取 / 刷新测试</el-button>
      </el-form-item>
      <el-descriptions v-if="result" :column="1" border>
        <el-descriptions-item label="状态">{{ states[result.state] || '未知' }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ result.finishedAt ? new Date(result.finishedAt).toLocaleString() : '尚未完成' }}</el-descriptions-item>
        <el-descriptions-item label="模型验证">{{ result.result?.modelVerified ? '通过' : '尚未通过' }}</el-descriptions-item>
        <el-descriptions-item label="诊断代码">{{ result.result?.issue || '等待执行' }}</el-descriptions-item>
        <el-descriptions-item label="测试采购费用">
          <template v-if="result.costVisibility === 'visible' && result.cost">
            {{ costStates[result.cost.state] || '未知' }}
            <span v-if="result.cost.effectiveAmount !== null"> · {{ result.cost.currency }} {{ result.cost.effectiveAmount }}</span>
            <span v-else> · 金额未知</span>
          </template>
          <span v-else>无费用查看权限</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-form-item v-if="canActivate && target?.state === 'draft'" label="启用原因" prop="reason">
        <el-input v-model="form.reason" type="textarea" maxlength="4000" show-word-limit />
      </el-form-item>
    </el-form>
    <el-alert title="服务端会再次核对当前配置和证据。测试通过不代表费用已结算。" type="info" :closable="false" />
    <template #footer>
      <el-button :disabled="pending" @click="close">取消</el-button>
      <el-button v-if="canActivate && target?.state === 'draft'" type="primary" :disabled="!eligible || loading" :loading="pending" @click="submit">启用此版本</el-button>
    </template>
  </el-dialog>
</template>
