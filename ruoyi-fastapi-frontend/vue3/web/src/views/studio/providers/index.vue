<script setup>
import useSettingsStore from '@/store/modules/settings'
import { useProviders } from '@/composables/studio/useProviders'

const settings = useSettingsStore()
const {
  canWrite,
  rows,
  total,
  page,
  environment,
  loading,
  error,
  selected,
  accounts,
  accountTotal,
  accountPage,
  accountsLoading,
  open,
  accountOpen,
  pending,
  preparing,
  dialogError,
  editing,
  formRef,
  accountFormRef,
  form,
  accountForm,
  load,
  loadAccounts,
  select,
  start,
  close,
  startAccount,
  submit,
  submitAccount,
} = useProviders()
const states = { draft: '草稿（未验证）', active: '已启用', disabled: '已停用' }
const required = (message) => [{ required: true, whitespace: true, message, trigger: 'blur' }]
const rules = {
  name: required('请输入连接名称'),
  environment: required('请选择环境'),
  baseUrl: required('请输入供应商固定地址'),
  adapterVersion: [
    {
      required: true,
      pattern: /^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/,
      message: '请输入适配器版本标识，仅支持字母、数字、点、下划线和短横线',
      trigger: 'blur',
    },
  ],
  allowedHosts: required('请填写允许访问的完整域名，每行一个，不使用通配符'),
  connectTimeoutSeconds: [
    {
      required: true,
      type: 'number',
      min: 1,
      max: 120,
      message: '连接超时为1至120秒',
      trigger: 'change',
    },
  ],
  readTimeoutSeconds: [
    {
      required: true,
      type: 'number',
      min: 1,
      max: 3600,
      message: '读取超时为1至3600秒',
      trigger: 'change',
    },
  ],
  operationTimeoutSeconds: [
    {
      validator: (_rule, value, callback) =>
        callback(
          Number.isInteger(value) &&
            value >= Math.max(form.connectTimeoutSeconds, form.readTimeoutSeconds) &&
            value <= 3600
            ? undefined
            : new Error('操作超时不得短于连接或读取超时，且不超过3600秒')
        ),
      trigger: 'change',
    },
  ],
  taskTimeoutSeconds: [
    {
      validator: (_rule, value, callback) =>
        callback(
          Number.isInteger(value) && value >= form.operationTimeoutSeconds && value <= 604800
            ? undefined
            : new Error('任务超时不得短于操作超时，且不超过604800秒')
        ),
      trigger: 'change',
    },
  ],
}
const exact = (name) => [
  {
    required: true,
    validator: (_rule, value, callback) =>
      callback(
        value && value === value.trim() && !/[\x00-\x1f]/.test(value)
          ? undefined
          : new Error(`${name}不能为空或包含首尾空白、控制字符`)
      ),
    trigger: 'blur',
  },
]
const accountRules = {
  accountCode: exact('账号编码'),
  upstreamProject: exact('上游项目标识'),
  region: [
    {
      required: true,
      pattern: /^[a-z][a-z0-9_-]*$/,
      message: '区域以小写字母开头，仅支持小写字母、数字、下划线和短横线',
      trigger: 'blur',
    },
  ],
}
function filter() {
  page.value = 1
  load()
}
</script>

<template>
  <div class="app-container provider-page">
    <div class="heading">
      <h2>供应商连接与账号</h2>
      <el-button @click="settings.toggleTheme()">{{
        settings.isDark ? '切换亮色' : '切换暗色'
      }}</el-button>
    </div>
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="此处登记连接和账号，不会访问供应商或产生调用费用。配置变更会创建历史版本并退回草稿；凭据测试与启用请在供应商凭据页面操作。"
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
        v-model="environment"
        clearable
        placeholder="全部环境"
        aria-label="连接环境"
        @change="filter"
        ><el-option
          label="测试环境"
          value="test" /><el-option
          label="正式环境"
          value="production"
      /></el-select>
      <el-button
        :loading="loading"
        @click="load"
        >刷新</el-button
      ><el-button
        v-if="canWrite"
        type="primary"
        :disabled="pending"
        @click="start()"
        >登记连接</el-button
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
        label="连接名称"
        min-width="160"
      />
      <el-table-column
        label="环境"
        width="100"
        ><template #default="{ row }">{{
          row.environment === 'test' ? '测试' : '正式'
        }}</template></el-table-column
      >
      <el-table-column
        label="状态"
        width="155"
        ><template #default="{ row }"
          ><el-tag>{{ states[row.status] }}</el-tag></template
        ></el-table-column
      >
      <el-table-column
        label="固定地址"
        min-width="240"
        show-overflow-tooltip
        ><template #default="{ row }">{{
          row.currentVersion?.baseUrl || '缺失'
        }}</template></el-table-column
      >
      <el-table-column
        label="配置版本"
        width="100"
        ><template #default="{ row }">{{
          row.currentVersion?.versionNo || '无'
        }}</template></el-table-column
      >
      <el-table-column
        label="操作"
        width="180"
        ><template #default="{ row }"
          ><el-button
            link
            type="primary"
            @click.stop="select(row)"
            >查看账号</el-button
          ><el-button
            v-if="canWrite"
            link
            type="primary"
            :disabled="pending"
            @click.stop="start(row)"
            >编辑</el-button
          ></template
        ></el-table-column
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
      class="details"
    >
      <div class="heading">
        <h3>{{ selected.name }} · 配置与账号</h3>
        <el-button
          v-if="canWrite"
          :disabled="pending || selected.status === 'disabled'"
          @click="startAccount"
          >登记账号</el-button
        >
      </div>
      <el-descriptions
        v-if="selected.currentVersion"
        :column="2"
        border
      >
        <el-descriptions-item label="适配器版本">{{
          selected.currentVersion.adapterVersion
        }}</el-descriptions-item>
        <el-descriptions-item label="连接配置编号">{{
          selected.currentVersion.id
        }}</el-descriptions-item>
        <el-descriptions-item label="允许域名">{{
          selected.currentVersion.config.allowedHosts.join('、')
        }}</el-descriptions-item>
        <el-descriptions-item label="超时（秒）"
          >连接 {{ selected.currentVersion.config.connectTimeoutSeconds }} / 读取
          {{ selected.currentVersion.config.readTimeoutSeconds }} / 操作
          {{ selected.currentVersion.config.operationTimeoutSeconds }} / 任务
          {{ selected.currentVersion.config.taskTimeoutSeconds }}</el-descriptions-item
        >
      </el-descriptions>
      <el-table
        v-loading="accountsLoading"
        :data="accounts"
      >
        <el-table-column
          prop="id"
          label="账号编号"
          width="110"
        /><el-table-column
          prop="accountCode"
          label="供应商账号编码"
          min-width="180"
        /><el-table-column
          prop="region"
          label="区域"
          width="120"
        /><el-table-column
          prop="upstreamProject"
          label="供应商上游项目"
          min-width="180"
        /><el-table-column
          label="状态"
          width="100"
          ><template #default="{ row }">{{
            row.status === 'active' ? '正常' : '停用'
          }}</template></el-table-column
        >
      </el-table>
      <el-pagination
        v-model:current-page="accountPage"
        :page-size="20"
        :total="accountTotal"
        layout="total, prev, pager, next"
        @current-change="loadAccounts"
      />
      <p class="hint">
        账号登记后，可在“供应商凭据”页面为该账号登记密钥。上游项目标识必须来自供应商，不使用本平台业务项目名称代替。
      </p>
    </section>
    <el-dialog
      :model-value="open"
      :title="editing ? '编辑连接配置' : '登记供应商连接'"
      width="740px"
      destroy-on-close
      :show-close="!pending"
      :close-on-click-modal="false"
      :close-on-press-escape="!pending"
      @close="close"
    >
      <el-alert
        v-if="dialogError"
        :title="dialogError"
        type="error"
        :closable="false"
        role="alert"
      />
      <el-form
        ref="formRef"
        v-loading="preparing"
        :model="form"
        :rules="rules"
        label-position="top"
        :disabled="pending || preparing"
      >
        <el-form-item
          label="连接名称"
          prop="name"
          ><el-input
            v-model="form.name"
            maxlength="200"
        /></el-form-item>
        <el-form-item
          label="环境（创建后不可修改）"
          prop="environment"
          ><el-radio-group
            v-model="form.environment"
            :disabled="!!editing"
            ><el-radio value="test">测试</el-radio
            ><el-radio value="production">正式</el-radio></el-radio-group
          ></el-form-item
        >
        <el-form-item
          label="固定地址（不得包含用户名、密码、查询参数或片段）"
          prop="baseUrl"
          ><el-input
            v-model="form.baseUrl"
            maxlength="2000"
            placeholder="https://供应商域名/接口前缀"
        /></el-form-item>
        <el-form-item
          label="适配器版本（按已配置的适配器标识登记）"
          prop="adapterVersion"
          ><el-input
            v-model="form.adapterVersion"
            maxlength="100"
        /></el-form-item>
        <el-form-item
          label="允许域名（每行一个完整ASCII域名，不含协议或端口）"
          prop="allowedHosts"
          ><el-input
            v-model="form.allowedHosts"
            type="textarea"
            :rows="3"
            placeholder="固定地址的主机必须在此列表中"
        /></el-form-item>
        <div class="timeouts">
          <el-form-item
            label="连接超时（秒）"
            prop="connectTimeoutSeconds"
            ><el-input-number
              v-model="form.connectTimeoutSeconds"
              :min="1"
              :max="120"
              :precision="0"
          /></el-form-item>
          <el-form-item
            label="读取超时（秒）"
            prop="readTimeoutSeconds"
            ><el-input-number
              v-model="form.readTimeoutSeconds"
              :min="1"
              :max="3600"
              :precision="0"
          /></el-form-item>
          <el-form-item
            label="操作超时（秒）"
            prop="operationTimeoutSeconds"
            ><el-input-number
              v-model="form.operationTimeoutSeconds"
              :min="1"
              :max="3600"
              :precision="0"
          /></el-form-item>
          <el-form-item
            label="任务超时（秒）"
            prop="taskTimeoutSeconds"
            ><el-input-number
              v-model="form.taskTimeoutSeconds"
              :min="1"
              :max="604800"
              :precision="0"
          /></el-form-item>
        </div>
        <p class="hint">
          业务标识固定为 op。这里不填写 API 密钥或自定义鉴权请求头。HTTP
          地址可登记，但不代表已满足正式调用的传输安全要求。
        </p>
      </el-form>
      <template #footer
        ><el-button
          :disabled="pending"
          @click="close"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="pending"
          :disabled="preparing"
          @click="submit"
          >保存配置</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      :model-value="accountOpen"
      :title="`${selected?.name || ''} · 登记供应商账号`"
      width="580px"
      destroy-on-close
      :show-close="!pending"
      :close-on-click-modal="false"
      :close-on-press-escape="!pending"
      @close="close"
    >
      <el-alert
        v-if="dialogError"
        :title="dialogError"
        type="error"
        :closable="false"
        role="alert"
      />
      <el-form
        ref="accountFormRef"
        :model="accountForm"
        :rules="accountRules"
        label-position="top"
        :disabled="pending"
      >
        <el-form-item
          label="供应商账号编码"
          prop="accountCode"
          ><el-input
            v-model="accountForm.accountCode"
            maxlength="100"
        /></el-form-item>
        <el-form-item
          label="区域标识"
          prop="region"
          ><el-input
            v-model="accountForm.region"
            maxlength="32"
        /></el-form-item>
        <el-form-item
          label="供应商侧项目标识"
          prop="upstreamProject"
          ><el-input
            v-model="accountForm.upstreamProject"
            maxlength="100"
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
          @click="submitAccount"
          >登记账号</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>

<style scoped>
.provider-page {
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
.heading h2,
.heading h3 {
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
.details {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color);
}
.hint {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.timeouts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
@media (max-width: 600px) {
  .timeouts {
    grid-template-columns: 1fr;
  }
}
</style>
