<script setup>
import { useRouting } from '@/composables/studio/useRouting'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
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
    <header>
      <h2>项目模型路由</h2>
      <el-button
        text
        @click="settings.toggleTheme()"
        >切换主题</el-button
      >
    </header>
    <p>
      按项目配置模型、供应商账号和候选凭据。启用需要同区域已发布能力及有效凭据版本，保存时由服务端校验。
    </p>
    <el-form
      inline
      @submit.prevent
    >
      <el-form-item label="项目ID"
        ><el-input
          v-model="projectId"
          :disabled="pending"
          placeholder="输入治理范围内的项目ID"
      /></el-form-item>
      <el-form-item
        ><el-button
          :disabled="!allowed || pending"
          :loading="loading"
          @click="load"
          >读取路由</el-button
        ></el-form-item
      >
    </el-form>
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
          <el-form-item label="模型ID"><el-input v-model="route.modelId" /></el-form-item>
          <el-form-item label="账号ID"><el-input v-model="route.accountId" /></el-form-item>
          <el-form-item label="路由优先级"
            ><el-input-number
              v-model="route.priority"
              :min="0"
              :max="2147483647"
              :precision="0"
          /></el-form-item>
          <el-form-item label="启用"><el-switch v-model="route.enabled" /></el-form-item>
          <el-button
            text
            type="danger"
            @click="routes.splice(index, 1)"
            >移除路由</el-button
          >
        </div>
        <div
          v-for="(credential, candidateIndex) in route.credentials"
          :key="candidateIndex"
          class="route-fields"
        >
          <el-form-item label="候选凭据ID"
            ><el-input v-model="credential.credentialId"
          /></el-form-item>
          <el-form-item label="凭据优先级"
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
          /></el-form-item>
          <el-button
            text
            type="danger"
            @click="route.credentials.splice(candidateIndex, 1)"
            >移除凭据</el-button
          >
        </div>
        <el-button
          :disabled="route.credentials.length >= 100"
          text
          @click="route.credentials.push({ credentialId: '', priority: 100, maxConcurrency: 1 })"
          >添加候选凭据</el-button
        >
      </el-card>
      <el-button
        :disabled="routes.length >= 200"
        @click="addRoute"
        >添加路由</el-button
      >
      <el-button
        type="primary"
        :loading="pending"
        @click="save"
        >保存整组路由</el-button
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
</style>
