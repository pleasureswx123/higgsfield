<script setup>
import ModelSetupEntry from '@/components/ModelSetupEntry.vue'
import { useRoutingChoices } from '@/composables/studio/useRoutingChoices'
import { useRouting } from '@/composables/studio/useRouting'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const choices = useRoutingChoices()
function changeModel(route, value) { route.modelId = value; route.accountId = ''; route.credentials = [] }
function changeAccount(route, value) { route.accountId = value; route.credentials = [] }
const {
  allowed,
  projectId,
  revision,
  routes,
  loading,
  pending,
  error,
  message,
  formRef,
  load,
  save,
} = useRouting()
function addRoute() {
  routes.value.push({ modelId: '', accountId: '', priority: 100, enabled: false, credentials: [] })
}
</script>

<template>
  <div class="app-container routing-console">
    <ModelSetupEntry />
    <header>
      <h2>项目专用配置</h2><p>此处为可选高级配置。全平台模型自动适用于现有和新建项目，无需在此逐项目配置；原有专用配置优先使用。</p>
      <el-button
        text
        @click="settings.toggleTheme()"
        >切换主题</el-button
      >
    </header>
    <p>
      先选择项目，再选择允许使用的模型和供应商密钥。首次接入模型请使用上方接入助手。
    </p>
    <el-form
      inline
      @submit.prevent
    >
      <el-form-item label="选择项目">
        <el-select v-if="choices.canProjects.value" v-model="projectId" filterable :disabled="pending" :loading="choices.loading.value" placeholder="按项目名称选择" style="min-width: 260px">
          <el-option v-for="row in choices.projects.value" :key="row.id" :label="row.name" :value="row.id" />
        </el-select>
        <el-input v-else
          v-model="projectId"
          :disabled="pending"
          placeholder="无项目名称读取权限，请输入项目编号"
      /></el-form-item>
      <el-form-item
        ><el-button
          :disabled="!allowed || pending"
          :loading="loading"
          @click="load"
          >查看使用配置</el-button
        ></el-form-item
      >
    </el-form>
    <el-alert v-for="issue in choices.errors.value" :key="issue" :title="issue" type="warning" :closable="false" />
    <el-button v-if="choices.errors.value.length" :disabled="pending" @click="choices.load">重新读取名称</el-button>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="message"
      :title="message"
      type="success"
      :closable="false"
      show-icon
    />
    <el-form
      v-if="revision && allowed"
      ref="formRef"
      :model="{ routes }"
      :disabled="pending"
      label-position="top"
      @submit.prevent
    >
      <p>
        当前版本：{{
          revision
        }}。保存会替换此项目的整组路由；删除所有条目后保存将清空路由。重新读取会丢弃未保存编辑。
      </p>
      <el-empty
        v-if="!routes.length"
        description="暂无路由"
      />
      <el-card
        v-for="(route, index) in routes"
        :key="index"
        class="route-card"
        shadow="never"
      >
        <div class="route-fields">
          <el-form-item label="模型">
            <el-select v-if="choices.canNames.value" :model-value="route.modelId" filterable placeholder="选择模型" @update:model-value="changeModel(route, $event)">
              <el-option v-for="row in choices.models.value" :key="row.id" :label="row.displayName" :value="row.id" />
              <el-option v-if="route.modelId && !choices.models.value.some(row => row.id === route.modelId)" :value="route.modelId" :label="`原模型（编号 ${route.modelId}，名称不可读）`" />
            </el-select><el-input v-else v-model="route.modelId" placeholder="模型编号（无名称读取权限）" />
          </el-form-item>
          <el-form-item label="供应商账号">
            <el-select v-if="choices.canNames.value" :model-value="route.accountId" filterable placeholder="选择采购账号" @update:model-value="changeAccount(route, $event)">
              <el-option v-for="row in choices.accountsFor(route.modelId)" :key="row.id" :label="`${row.accountCode} · ${row.region}`" :value="row.id" :disabled="row.status !== 'active'" />
              <el-option v-if="route.accountId && !choices.accountsFor(route.modelId).some(row => row.id === route.accountId)" :value="route.accountId" :label="`原账号（编号 ${route.accountId}，名称不可读）`" />
            </el-select><el-input v-else v-model="route.accountId" placeholder="账号编号" />
          </el-form-item>
          <details><summary>模型优先级（高级）</summary><el-form-item label="路由优先级"
            ><el-input-number
              v-model="route.priority"
              :min="0"
              :max="2147483647"
              :precision="0"
          /></el-form-item></details>
          <el-form-item label="允许此项目使用"><el-switch v-model="route.enabled" /></el-form-item>
          <el-button
            text
            type="danger"
            @click="routes.splice(index, 1)"
            >移除此模型</el-button
          >
        </div>
        <div
          v-for="(credential, candidateIndex) in route.credentials"
          :key="candidateIndex"
          class="route-fields"
        >
          <el-form-item label="使用密钥">
            <el-select v-if="choices.canNames.value" v-model="credential.credentialId" filterable placeholder="选择已保存的密钥">
              <el-option v-for="row in choices.credentialsFor(route.accountId)" :key="row.id" :label="row.name" :value="row.id" :disabled="row.status !== 'active'" />
              <el-option v-if="credential.credentialId && !choices.credentialsFor(route.accountId).some(row => row.id === credential.credentialId)" :value="credential.credentialId" :label="`原密钥（编号 ${credential.credentialId}，名称不可读）`" />
            </el-select><el-input v-else v-model="credential.credentialId" placeholder="凭据编号" />
          </el-form-item>
          <details><summary>优先级与并发（高级）</summary><el-form-item label="凭据优先级"
            ><el-input-number
              v-model="credential.priority"
              :min="0"
              :max="2147483647"
              :precision="0"
          /></el-form-item>
          <el-form-item label="并发上限"
            ><el-input-number
              v-model="credential.maxConcurrency"
              :min="1"
              :max="2147483647"
              :precision="0"
          /></el-form-item></details>
          <el-button
            text
            type="danger"
            @click="route.credentials.splice(candidateIndex, 1)"
            >移除此密钥</el-button
          >
        </div>
        <el-button
          :disabled="route.credentials.length >= 100"
          text
          @click="route.credentials.push({ credentialId: '', priority: 100, maxConcurrency: 1 })"
          >添加使用密钥</el-button
        >
      </el-card>
      <el-button
        :disabled="routes.length >= 200"
        @click="addRoute"
        >添加可用模型</el-button
      >
      <el-button
        type="primary"
        :loading="pending"
        @click="save"
        >保存项目专用配置</el-button
      >
    </el-form>
  </div>
</template>

<style scoped>
header,
.route-fields {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
}
header {
  justify-content: space-between;
}
.route-card {
  margin-bottom: 16px;
}
.routing-console {
  color: var(--el-text-color-primary);
}
.el-alert {
  margin-bottom: 16px;
}
summary { cursor: pointer; color: var(--el-text-color-secondary); margin-bottom: 12px; }
.route-fields :deep(.el-select) { min-width: 220px; }
</style>
