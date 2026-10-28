<script setup>
import { computed } from 'vue'
import { useProjectGovernance, governanceActions } from '@/composables/studio/useProjectGovernance'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const {
  allowed,
  filters,
  rows,
  page,
  total,
  loading,
  error,
  target,
  action,
  reason,
  pending,
  actionError,
  formRef,
  load,
  search,
  start,
  close,
  submit,
} = useProjectGovernance()
const labels = { pause: '暂停', resume: '恢复进行', archive: '归档', restore: '还原为进行中' }
const statuses = { active: '进行中', paused: '暂停', archived: '归档', pending_delete: '待删除' }
const form = computed(() => ({ reason: reason.value }))
</script>
<template>
  <div class="app-container">
    <header>
      <h2>项目治理</h2>
      <el-button
        text
        @click="settings.toggleTheme()"
        >切换主题</el-button
      >
    </header>
    <p>此处管理授权范围内的项目状态。暂停或归档不会取消已经提交给供应商的任务。</p>
    <el-form
      inline
      @submit.prevent
    >
      <el-form-item label="项目名称"
        ><el-input
          v-model="filters.q"
          maxlength="200"
          clearable
      /></el-form-item>
      <el-form-item label="状态"
        ><el-select
          v-model="filters.status"
          clearable
          style="width: 160px"
          ><el-option
            v-for="(label, value) in statuses"
            :key="value"
            :label="label"
            :value="value" /></el-select
      ></el-form-item>
      <el-form-item
        ><el-button
          :disabled="!allowed"
          :loading="loading"
          @click="search"
          >查询</el-button
        ></el-form-item
      >
    </el-form>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    />
    <el-table
      v-loading="loading"
      :data="rows"
      empty-text="暂无可治理项目"
    >
      <el-table-column
        prop="id"
        label="项目ID"
      /><el-table-column
        prop="name"
        label="项目名称"
      /><el-table-column label="状态"
        ><template #default="{ row }">{{ statuses[row.status] }}</template></el-table-column
      >
      <el-table-column
        prop="revision"
        label="修订"
      /><el-table-column
        prop="updateTime"
        label="更新时间"
      />
      <el-table-column
        label="操作"
        min-width="200"
        ><template #default="{ row }"
          ><el-button
            v-for="operation in governanceActions[row.status] || []"
            :key="operation"
            text
            :disabled="pending || !allowed"
            @click="start(row, operation)"
            >{{ labels[operation] }}</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-pagination
      v-if="total"
      v-model:current-page="page"
      :page-size="20"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="load"
    />
    <el-dialog
      :model-value="!!target"
      :title="labels[action] || '项目治理'"
      width="min(600px, 95vw)"
      :show-close="!pending"
      :close-on-click-modal="!pending"
      :close-on-press-escape="!pending"
      destroy-on-close
      @close="close"
    >
      <p>{{ target?.name }} · 项目 {{ target?.id }} · 修订 {{ target?.revision }}</p>
      <el-form
        ref="formRef"
        :model="form"
        :disabled="pending"
        label-position="top"
        ><el-form-item
          label="操作原因"
          prop="reason"
          :rules="[{ required: true, whitespace: true, message: '请填写治理原因' }]"
          ><el-input
            v-model="reason"
            type="textarea"
            maxlength="4000" /></el-form-item
      ></el-form>
      <el-alert
        v-if="actionError"
        :title="actionError"
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
          :disabled="!allowed"
          @click="submit"
          >确认{{ labels[action] }}</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>
<style scoped>
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.el-pagination {
  margin-top: 16px;
}
</style>
