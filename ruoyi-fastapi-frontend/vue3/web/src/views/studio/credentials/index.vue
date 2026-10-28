<script setup>
import { computed, ref } from 'vue'
import CredentialActivationDialog from './CredentialActivationDialog.vue'
import CredentialTestDialog from './CredentialTestDialog.vue'
import useSettingsStore from '@/store/modules/settings'
import { useCredentials } from '@/composables/studio/useCredentials'
import { useCredentialState } from '@/composables/studio/useCredentialState'

const settings = useSettingsStore()
const activation = ref()
const testing = ref()
const activationBusy = computed(() => activation.value?.open || activation.value?.pending || testing.value?.open || testing.value?.pending)
const {
  canCreate,
  canRotate,
  rows,
  total,
  page,
  status,
  loading,
  error,
  selected,
  versions,
  versionTotal,
  versionPage,
  versionsLoading,
  open,
  pending,
  preparing,
  formRef,
  form,
  dialogError,
  accounts,
  accountTotal,
  accountPage,
  accountsLoading,
  connection,
  rotating,
  load,
  loadVersions,
  select,
  loadAccounts,
  chooseAccount,
  start,
  close,
  submit,
} = useCredentials()
const {
  open: stateOpen,
  pending: statePending,
  error: stateError,
  formRef: stateFormRef,
  form: stateForm,
  target: stateTarget,
  action: stateAction,
  available: stateAvailable,
  start: startState,
  close: closeState,
  submit: submitState,
} = useCredentialState(async () => {
  await load()
  await loadVersions()
})
const actionLabels = { drain: '排空', disable: '停用', revoke: '本地撤销' }
const stateRules = {
  reason: [{ required: true, whitespace: true, message: '请输入操作原因', trigger: 'blur' }],
}
const states = {
  draft: '草稿',
  active: '启用',
  draining: '排空中',
  disabled: '停用',
  revoked: '撤销',
}
const required = (message) => [{ required: true, message, trigger: 'blur' }]
const rules = {
  name: required('请输入凭据名称'),
  accountId: required('请选择供应商账号'),
  ownerId: [
    {
      required: true,
      pattern: /^[1-9]\d{0,18}$/,
      message: '请输入有效责任人用户编号',
      trigger: 'blur',
    },
  ],
  apiKey: [
    {
      required: true,
      pattern: /^[\x21-\x7e]{8,4096}$/,
      message: '请输入8至4096个无空白的ASCII字符',
      trigger: 'blur',
    },
  ],
  validFrom: required('请选择有效期开始时间'),
  validUntil: [
    {
      validator: (_rule, value, callback) =>
        callback(
          value && new Date(value) <= new Date(form.validFrom)
            ? new Error('结束时间必须晚于开始时间')
            : undefined
        ),
      trigger: 'change',
    },
  ],
}
const dateText = (value) => (value ? new Date(value).toLocaleString() : '不限')
function filter() {
  page.value = 1
  load()
}
</script>

<template>
  <div class="app-container credential-page">
    <div class="heading">
      <h2>供应商凭据</h2>
      <el-button @click="settings.toggleTheme()">{{
        settings.isDark ? '切换亮色' : '切换暗色'
      }}</el-button>
    </div>
    <el-alert
      type="info"
      :closable="false"
      title="登记和轮换均创建草稿，不会自动启用。启用需要当前配置的成功测试记录。密钥保存后仅显示末尾四位。"
      show-icon
    />
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
      role="alert"
    />
    <div class="toolbar">
      <el-select
        v-model="status"
        clearable
        placeholder="全部状态"
        aria-label="凭据状态"
        @change="filter"
        ><el-option
          v-for="(label, value) in states"
          :key="value"
          :label="label"
          :value="value"
      /></el-select>
      <el-button
        :loading="loading"
        @click="load"
        >刷新</el-button
      >
      <el-button
        v-if="canCreate"
        type="primary"
        :disabled="pending || stateOpen || statePending || activationBusy"
        @click="start()"
        >登记凭据</el-button
      >
    </div>
    <el-table
      v-loading="loading"
      :data="rows"
      highlight-current-row
      @row-click="select"
    >
      <el-table-column
        prop="name"
        label="凭据名称"
        min-width="180"
      />
      <el-table-column
        prop="accountId"
        label="账号编号"
        width="110"
      />
      <el-table-column
        prop="ownerId"
        label="责任人编号"
        width="110"
      />
      <el-table-column
        label="状态"
        width="100"
        ><template #default="{ row }"
          ><el-tag>{{ states[row.status] }}</el-tag></template
        ></el-table-column
      >
      <el-table-column
        label="最新版本末位"
        min-width="130"
        ><template #default="{ row }">{{
          row.versionsSummary[0]?.maskedSuffix || '无版本'
        }}</template></el-table-column
      >
      <el-table-column
        label="操作"
        width="180"
        ><template #default="{ row }">
          <el-button
            link
            type="primary"
            @click.stop="select(row)"
            >查看版本</el-button
          >
          <el-button
            v-if="canRotate"
            link
            type="primary"
            :disabled="
              pending || stateOpen || statePending || activationBusy || ['disabled', 'revoked'].includes(row.status)
            "
            @click.stop="start(row)"
            >轮换</el-button
          >
        </template></el-table-column
      >
    </el-table>
    <el-pagination
      v-model:current-page="page"
      :page-size="20"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="load"
    />
    <section
      v-if="selected"
      class="versions"
    >
      <h3>{{ selected.name }} · 历史版本</h3>
      <el-table
        v-loading="versionsLoading"
        :data="versions"
      >
        <el-table-column
          prop="versionNo"
          label="版本"
          width="80"
        />
        <el-table-column
          prop="maskedSuffix"
          label="密钥末位"
          width="130"
        />
        <el-table-column
          prop="inFlightCount"
          label="在途任务"
          width="100"
        />
        <el-table-column
          label="版本操作"
          min-width="220"
        >
          <template #default="{ row }">
            <el-button v-if="['draft', 'active'].includes(row.state)" v-hasPermi="['credential:test']" link type="primary"
              :disabled="pending || open || stateOpen || statePending || activationBusy"
              @click="testing.start(row)">申请测试</el-button>
            <el-button v-hasPermi="['credential:read']" link type="primary"
              :disabled="pending || open || stateOpen || statePending || activationBusy"
              @click="activation.start(row)">测试记录</el-button>
            <template
              v-for="(label, kind) in actionLabels"
              :key="kind"
            >
              <el-button
                v-if="stateAvailable(row, kind)"
                link
                :type="kind === 'revoke' ? 'danger' : 'primary'"
                :disabled="
                  pending ||
                  open ||
                  statePending ||
                  activationBusy ||
                  (kind === 'disable' && row.inFlightCount !== '0')
                "
                @click="startState(row, kind)"
                >{{ label }}</el-button
              >
            </template>
          </template>
        </el-table-column>
        <el-table-column
          prop="connectionVersionId"
          label="连接配置版本编号"
          min-width="150"
        />
        <el-table-column
          label="状态"
          width="100"
          ><template #default="{ row }">{{ states[row.state] }}</template></el-table-column
        >
        <el-table-column
          label="生效时间"
          min-width="170"
          ><template #default="{ row }">{{ dateText(row.validFrom) }}</template></el-table-column
        >
        <el-table-column
          label="到期时间"
          min-width="170"
          ><template #default="{ row }">{{ dateText(row.validUntil) }}</template></el-table-column
        >
      </el-table>
      <el-pagination
        v-model:current-page="versionPage"
        :page-size="20"
        :total="versionTotal"
        layout="total, prev, pager, next"
        @current-change="loadVersions"
      />
    </section>
    <el-dialog
      :model-value="stateOpen"
      :title="`${actionLabels[stateAction]}凭据版本 ${stateTarget?.versionNo ?? ''}`"
      width="560px"
      destroy-on-close
      :close-on-click-modal="false"
      :close-on-press-escape="!statePending"
      :show-close="!statePending"
      @close="closeState"
    >
      <el-alert
        type="warning"
        :closable="false"
        :title="
          stateAction === 'revoke'
            ? '本地撤销不能恢复，不代表供应商已撤销密钥或停止消费；原任务绑定和历史证据保留。'
            : stateAction === 'drain'
              ? '排空后不再接收新任务，已有任务仍需确认终态。'
              : '停用要求没有在途任务；提交时服务器会重新检查。'
        "
      />
      <el-alert
        v-if="stateError"
        type="error"
        :closable="false"
        :title="stateError"
        role="alert"
      />
      <el-form
        ref="stateFormRef"
        :model="stateForm"
        :rules="stateRules"
        label-position="top"
        :disabled="statePending"
      >
        <el-form-item
          label="操作原因"
          prop="reason"
        >
          <el-input
            v-model="stateForm.reason"
            type="textarea"
            :rows="4"
            maxlength="4000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button
          :disabled="statePending"
          @click="closeState"
          >取消</el-button
        >
        <el-button
          :type="stateAction === 'revoke' ? 'danger' : 'primary'"
          :loading="statePending"
          @click="submitState"
          >确认{{ actionLabels[stateAction] }}</el-button
        >
      </template>
    </el-dialog>
    <el-dialog
      :model-value="open"
      :title="rotating ? `轮换：${rotating.name}` : '登记供应商凭据'"
      width="720px"
      destroy-on-close
      :close-on-click-modal="false"
      :close-on-press-escape="!pending"
      :show-close="!pending"
      @close="close"
    >
      <el-alert
        v-if="dialogError"
        type="error"
        :closable="false"
        :title="dialogError"
        role="alert"
      />
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        :disabled="pending"
      >
        <template v-if="!rotating">
          <el-form-item
            label="凭据名称"
            prop="name"
            ><el-input
              v-model="form.name"
              maxlength="200"
          /></el-form-item>
          <el-form-item
            label="责任人用户编号"
            prop="ownerId"
            ><el-input
              v-model="form.ownerId"
              maxlength="19"
          /></el-form-item>
          <el-form-item
            label="供应商账号（点击选择）"
            prop="accountId"
          >
            <el-table
              v-loading="accountsLoading"
              :data="accounts"
              highlight-current-row
              @row-click="chooseAccount"
            >
              <el-table-column
                label="选择"
                width="65"
                ><template #default="{ row }">{{
                  row.id === form.accountId ? '已选' : ''
                }}</template></el-table-column
              >
              <el-table-column
                prop="accountCode"
                label="账号"
              /><el-table-column
                prop="region"
                label="区域"
              /><el-table-column
                prop="upstreamProject"
                label="上游项目"
              />
              <el-table-column label="状态"
                ><template #default="{ row }">{{
                  row.status === 'active' ? '正常' : '停用'
                }}</template></el-table-column
              >
            </el-table>
            <el-pagination
              v-model:current-page="accountPage"
              :page-size="20"
              :total="accountTotal"
              layout="prev, pager, next"
              @current-change="loadAccounts"
            />
          </el-form-item>
        </template>
        <p v-if="preparing">正在读取连接配置…</p>
        <el-alert
          v-if="connection"
          :type="connection.status === 'disabled' ? 'error' : 'info'"
          :closable="false"
          :title="`${connection.name} · ${connection.environment === 'test' ? '测试环境' : '正式环境'} · 配置版本 ${connection.currentVersion?.versionNo ?? '缺失'}（编号 ${connection.currentVersion?.id ?? '无'}）`"
        />
        <el-form-item
          label="供应商 API 密钥"
          prop="apiKey"
          ><el-input
            v-model="form.apiKey"
            type="password"
            autocomplete="new-password"
            maxlength="4096"
            placeholder="不保存在浏览器缓存；提交结束后清空"
        /></el-form-item>
        <el-form-item
          label="开始时间（本地时区）"
          prop="validFrom"
          ><el-date-picker
            v-model="form.validFrom"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ssZ"
        /></el-form-item>
        <el-form-item
          label="结束时间（可选，本地时区）"
          prop="validUntil"
          ><el-date-picker
            v-model="form.validUntil"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ssZ"
            clearable
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button
          :disabled="pending"
          @click="close"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="pending"
          :disabled="preparing || !connection?.currentVersion || connection.status === 'disabled'"
          @click="submit"
          >保存草稿</el-button
        ></template
      >
    </el-dialog>
    <CredentialActivationDialog ref="activation" @activated="load(); loadVersions()" />
    <CredentialTestDialog ref="testing" />
  </div>
</template>

<style scoped>
.credential-page {
  color: var(--el-text-color-primary);
}
.heading,
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.heading {
  justify-content: space-between;
}
.heading h2 {
  margin: 0;
}
.toolbar {
  margin-top: 16px;
  flex-wrap: wrap;
}
.toolbar .el-select {
  width: 180px;
}
.el-alert {
  margin-bottom: 16px;
}
.el-pagination {
  margin-top: 16px;
}
.versions {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color);
}
:deep(.el-dialog) {
  max-width: calc(100vw - 24px);
}
</style>
