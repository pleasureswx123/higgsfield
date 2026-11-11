<script setup lang="ts">
import { computed, watch } from 'vue'
import { ElInput, ElSelect, ElOption } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useProduction } from '@/composables/useProduction'
import { formatProjectDate } from '@/utils/projects'
import type { ProductionKind, ProductionState } from '@/api/production'
const props = defineProps<{
  kind: ProductionKind
  id: string
  projectId: string
  versionId: string
  disabled?: boolean
  dirty?: boolean
}>()
const emit = defineEmits<{
  changed: [state: ProductionState]
  busy: [busy: boolean]
  version: [id: string]
}>()
const {
  state,
  loading,
  pending,
  error,
  assignmentError,
  assignmentLoading,
  reason,
  clearDraft,
  members,
  performer,
  intent,
  oldVersion,
  blocked,
  load,
  run,
} = useProduction(
  () => props,
  () => !!props.disabled || !!props.dirty,
  (value) => emit('changed', value),
)
watch(
  () => pending.value || !!intent.value,
  (value) => emit('busy', value),
)
const labels: Record<string, string> = {
  reopen: '重新制作',
  start: '开始制作',
  submit: '提交审核',
  withdraw: '撤回提交',
  request_changes: '退回修改',
  approve: '审核通过',
  assign: '分配制作人',
  revise: '保存新版本',
}
const statuses: Record<string, string> = {
  none: '未开始',
  working: '制作中',
  review: '待审核',
  rejected: '待修改',
  approved: '已通过',
}
const feedback = computed(() => {
  if (oldVersion.value || !['rejected', 'working'].includes(state.value?.workStatus || '')) return
  // 已通过的上一轮意见不再作为当前待处理意见。
  for (const item of state.value?.history || []) {
    if (item.action === 'approve') return
    if (item.action === 'request_changes' && item.reason) return item
  }
})
</script>
<template>
  <section class="production-panel" aria-label="制作与审核">
    <header>
      <strong>制作与审核</strong
      ><Button variant="ghost" :disabled="loading || pending || !!intent" @click="load"
        >刷新</Button
      >
    </header>
    <p v-if="loading" role="status">正在读取制作信息…</p>
    <template v-if="state">
      <p>
        <span class="muted">{{ oldVersion ? '最新版本状态：' : '当前状态：' }}</span
        >{{
          state.workStatus === 'approved' && !state.reviewVerified
            ? '历史通过（版本未验证）'
            : statuses[state.workStatus]
        }}
      </p>
      <p><span class="muted">制作人：</span>{{ state.performerName || '未分配' }}</p>
      <aside v-if="feedback" class="production-feedback" aria-label="修改意见">
        <strong>修改意见</strong>
        <p>{{ feedback.reason }}</p>
      </aside>
      <Button
        v-if="state.approvedVersionId && state.approvedVersionId !== versionId"
        variant="ghost"
        :disabled="pending || !!intent"
        @click="emit('version', state.approvedVersionId)"
        >查看最近通过版本</Button
      >
      <p v-if="oldVersion" class="muted">
        正在查看旧版本，不能对当前新版本执行制作或审核操作。请打开最新版本后操作。
      </p>
      <Button
        v-if="oldVersion"
        variant="outline"
        :disabled="pending || !!intent"
        @click="emit('version', state.versionId)"
        >查看最新版本</Button
      >
      <p v-if="dirty" class="muted">有未保存的修改，请先保存，再执行制作或审核操作。</p>
      <div v-if="state.canAssign" class="production-assignment">
        <ElSelect
          v-model="performer"
          aria-label="分配制作人"
          placeholder="未分配"
          :disabled="blocked || !!intent || assignmentLoading || !!assignmentError"
          :loading="assignmentLoading"
        >
          <ElOption
            v-if="performer && !members.some((member) => member.userId === performer)"
            :value="performer"
            :label="state.performerName || '原制作人（当前不可分配）'"
            disabled
          />
          <ElOption
            v-for="member in members"
            :key="member.userId"
            :value="member.userId"
            :label="member.displayName"
          />
        </ElSelect>
        <Button
          variant="outline"
          :disabled="
            blocked ||
            !!intent ||
            assignmentLoading ||
            !!assignmentError ||
            !performer ||
            performer === state.performerId
          "
          @click="run(undefined, true)"
          >分配</Button
        >
      </div>
      <p v-if="assignmentError" class="project-error" role="alert">
        制作人列表暂不可用：{{ assignmentError }}。可点击上方刷新重试，审核操作不受影响。
      </p>
      <label v-if="state.allowedActions.includes('request_changes')" class="production-reason"
        >修改意见（退回时必填）
        <ElInput
          v-model="reason"
          type="textarea"
          :rows="3"
          maxlength="2000"
          placeholder="请说明需要修改的内容"
          :disabled="blocked || !!intent"
        />
      </label>
      <div v-if="reason" class="production-draft-note">
        <span class="muted">意见草稿已在当前会话保留，关闭后重新打开此版本可继续填写。</span>
        <Button variant="ghost" :disabled="pending || !!intent" @click="clearDraft"
          >清除意见草稿</Button
        >
      </div>
      <div class="production-actions">
        <Button
          v-for="action in state.allowedActions"
          :key="action"
          :variant="
            action === 'submit' || action === 'approve' || action === 'start'
              ? 'default'
              : 'outline'
          "
          :disabled="blocked || !!intent"
          @click="run(action)"
          >{{ labels[action] }}</Button
        >
      </div>
      <p v-if="pending" role="status">正在保存制作操作…</p>
      <p v-if="intent && !pending" role="status">
        结果尚未确认，请重试原请求。<Button :disabled="blocked" @click="run()">重试确认</Button>
      </p>
      <details class="production-history">
        <summary>流转记录（{{ state.history.length }}）</summary>
        <p v-if="state.history.length === 100" class="muted">此处显示最近 100 条记录。</p>
        <p v-if="!state.history.length" class="muted">暂无流转记录</p>
        <article v-for="item in state.history" :key="item.id">
          <strong>{{ labels[item.action] || item.action }}</strong> ·
          {{ item.actorName || '未知用户' }}
          <small
            >{{ formatProjectDate(item.createTime) }} ·
            {{
              item.versionId === versionId
                ? '当前查看版本'
                : item.versionId
                  ? '其他版本'
                  : '历史记录，未绑定版本'
            }}</small
          >
          <p v-if="item.reason">{{ item.reason }}</p>
          <Button
            v-if="item.versionId"
            variant="ghost"
            :disabled="pending || !!intent"
            @click="emit('version', item.versionId)"
            >查看此版本</Button
          >
        </article>
      </details>
    </template>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
  </section>
</template>
<style scoped>
.production-panel {
  display: grid;
  gap: 10px;
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.production-panel header,
.production-assignment {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}
.production-panel p {
  margin: 0;
  overflow-wrap: anywhere;
}
.production-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.production-reason {
  display: grid;
  gap: 8px;
}
.production-feedback {
  display: grid;
  gap: 6px;
  padding: 10px;
  border-radius: 8px;
  background: var(--muted);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.production-history summary {
  cursor: pointer;
  padding: 8px 0;
}
.production-history article {
  border-top: 1px solid var(--border);
  padding: 10px 0;
}
.production-history small {
  display: block;
  color: var(--muted-foreground);
  margin: 5px 0;
}
.production-assignment .el-select {
  min-width: 0;
  flex: 1;
}
</style>
