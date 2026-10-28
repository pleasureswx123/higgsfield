<script setup>
import { watch } from 'vue'
import { useJoinRequests } from '@/composables/studio/useJoinRequests'
const props = defineProps({ projectId: { type: String, required: true }, roles: { type: Array, default: () => [] }, canManage: Boolean })
const emit = defineEmits(['changed', 'locked'])
const { rows, total, page, status, loading, error, target, form, formRef, saving, uncertain, locked, actionError, load, start, close, submit, filter, changePage } = useJoinRequests(() => props.projectId, () => props.roles, () => props.canManage, () => emit('changed'))
watch(locked, value => emit('locked', value), { immediate: true })
const labels = { pending: '待审批', approved: '已批准', rejected: '已拒绝', cancelled: '已取消' }
const rules = {
  decision: [{ required: true, message: '请选择审批结果' }],
  roleId: [{ validator: (_rule, value, done) => done(form.decision === 'approved' && !value ? new Error('批准时请选择角色') : undefined), trigger: 'change' }],
}
</script>
<template>
  <section class="join-requests">
    <h3>加入申请</h3>
    <el-select v-model="status" :disabled="locked" aria-label="申请状态" @change="filter">
      <el-option label="全部状态" value="" />
      <el-option v-for="(label, value) in labels" :key="value" :label="label" :value="value" />
    </el-select>
    <el-button link :disabled="locked || loading" @click="load">刷新申请</el-button>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <el-table v-else v-loading="loading" :data="rows" empty-text="暂无申请">
      <el-table-column prop="userId" label="申请人编号" />
      <el-table-column prop="reason" label="申请说明" show-overflow-tooltip />
      <el-table-column label="状态"><template #default="{ row }">{{ labels[row.status] }}</template></el-table-column>
      <el-table-column prop="createTime" label="申请时间" />
      <el-table-column label="操作"><template #default="{ row }"><el-button v-if="canManage && row.status === 'pending'" link :disabled="locked" @click="start(row)">审批</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-if="total > 20" :current-page="page" :page-size="20" :total="total" :disabled="locked" layout="prev,pager,next" @current-change="changePage" />
    <el-dialog :model-value="!!target" title="审批加入申请" width="min(520px, 94vw)" append-to-body :before-close="close" :close-on-click-modal="!locked" :show-close="!locked">
      <p>申请人 {{ target?.userId }}：{{ target?.reason || '未填写说明' }}</p>
      <el-alert v-if="actionError" type="error" :title="actionError" :closable="false" />
      <el-alert v-if="uncertain" type="warning" title="结果尚未确认，请重试原审批请求；不要重新选择审批结果。" :closable="false" />
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="locked">
        <el-form-item label="审批结果" prop="decision"><el-radio-group v-model="form.decision"><el-radio value="approved">批准</el-radio><el-radio value="rejected">拒绝</el-radio></el-radio-group></el-form-item>
        <el-form-item v-if="form.decision === 'approved'" label="授予角色" prop="roleId"><el-select v-model="form.roleId"><el-option v-for="role in roles.filter(item => item.canGrant)" :key="role.id" :label="role.name" :value="role.id" /></el-select></el-form-item>
        <el-form-item label="审批说明"><el-input v-model="form.reason" type="textarea" maxlength="5000" show-word-limit /></el-form-item>
      </el-form>
      <template #footer><el-button :disabled="locked" @click="close">取消</el-button><el-button type="primary" :loading="saving" :disabled="!canManage" @click="submit">{{ uncertain ? '重试确认' : '提交审批' }}</el-button></template>
    </el-dialog>
  </section>
</template>
<style scoped>
.join-requests { margin-top: 24px; border-top: 1px solid var(--el-border-color); padding-top: 12px; }
.join-requests > .el-select { width: 160px; margin-right: 12px; }
</style>
