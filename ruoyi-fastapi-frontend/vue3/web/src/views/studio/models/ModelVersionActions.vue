<script setup>
import { useModelVersionActions } from '@/composables/studio/useModelVersionActions'
const props = defineProps({ version: { type: Object, required: true } })
const emit = defineEmits(['saved'])
const { actions, open, pending, error, action, selected, formRef, form, start, close, submit } =
  useModelVersionActions(
    () => props.version,
    () => emit('saved')
  )
const labels = { verify: '登记验证证据', publish: '发布版本', disable: '停用版本' }
const rules = {
  reason: [
    {
      required: true,
      whitespace: true,
      max: 2000,
      message: '请填写操作原因，最多2000字',
      trigger: 'blur',
    },
  ],
  verificationRef: [
    {
      required: true,
      whitespace: true,
      max: 2000,
      message: '请填写已审阅联调证据的位置，最多2000字',
      trigger: 'blur',
    },
  ],
}
</script>
<template>
  <div class="version-actions">
    <el-button
      v-for="value in actions"
      :key="value"
      :disabled="pending"
      @click="start(value)"
      >{{ labels[value] }}</el-button
    >
    <el-dialog
      :model-value="open"
      :title="labels[action]"
      width="min(600px, 95vw)"
      :show-close="!pending"
      :close-on-click-modal="!pending"
      :close-on-press-escape="!pending"
      @close="close"
      destroy-on-close
    >
      <p v-if="selected">
        版本 {{ selected.versionNo }} · {{ selected.gatewayAlias }} · 修订 {{ selected.revision }}
      </p>
      <p v-if="action === 'verify'">
        仅登记已经实际完成并审阅的联调证据。本操作不会调用供应商执行验证。
      </p>
      <p v-else-if="action === 'publish'">
        发布当前已验证能力版本；后续可用性仍由路由、价格和项目权限共同决定。
      </p>
      <p v-else>停用后当前版本不再作为新生成任务的可用版本；历史任务保留原版本记录。</p>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        :disabled="pending"
      >
        <el-form-item
          v-if="action === 'verify'"
          label="联调证据位置"
          prop="verificationRef"
          ><el-input
            v-model="form.verificationRef"
            :maxlength="2000"
        /></el-form-item>
        <el-form-item
          label="操作原因"
          prop="reason"
          ><el-input
            v-model="form.reason"
            type="textarea"
            :maxlength="2000"
            show-word-limit
        /></el-form-item>
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
          @click="submit"
          >确认{{ labels[action] }}</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>
<style scoped>
.version-actions {
  margin: 16px 0;
}
p {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
