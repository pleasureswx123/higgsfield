<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useModelSetup } from '@/composables/studio/useModelSetup'
import useSettingsStore from '@/store/modules/settings'
const emit = defineEmits(['saved', 'advanced', 'busy'])
const router = useRouter()
const settings = useSettingsStore(), formRef = ref()
const state = useModelSetup({ supplierOnly: true })
const { form, selection, connections, accounts, credentials, connectionSaved, pending, uncertain, error, loaded, missing, next, retry, changeConnection, changeAccount } = state
form.upstreamProject = 'op'
watch(() => pending.value || uncertain.value, value => emit('busy', value), { immediate: true })
async function save() { if (await formRef.value?.validate().catch(() => false)) await next() }
const rules = { name: [{ required: true, whitespace: true, message: '请填写供应商名称' }],
  baseUrl: [{ required: true, message: '请填写供应商 API 地址' }], apiKey: [{ required: true, message: '请粘贴供应商提供的 API Key' }] }
</script>
<template>
  <main class="app-container supplier-setup">
    <header><div><h2>配置供应商</h2><p>只需保存一次，旗下所有模型共用连接与密钥。此步骤不会调用供应商或收费。</p></div><el-button text @click="settings.toggleTheme()">切换主题</el-button></header>
    <el-alert v-if="missing.length" :title="`缺少权限：${missing.join('、')}`" type="warning" :closable="false" />
    <el-result v-if="connectionSaved" icon="success" title="供应商已保存" sub-title="下一步添加模型。地址和密钥已经保存，无需再次填写。"><template #extra><el-button type="primary" @click="emit('saved')">下一步：添加模型</el-button></template></el-result>
    <el-form v-else ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="pending || uncertain || !loaded || missing.length > 0" @submit.prevent>
      <el-form-item v-if="connections.length" label="供应商"><el-select v-model="selection.connection" @change="changeConnection"><el-option v-for="row in connections" :key="row.id" :value="row.id" :label="row.name" /><el-option value="" label="新增供应商连接" /></el-select></el-form-item>
      <template v-if="!selection.connection">
        <el-form-item label="供应商名称" prop="name"><el-input v-model="form.name" placeholder="例如 VideoPlus MM" maxlength="200" /></el-form-item>
        <el-form-item label="API 地址" prop="baseUrl"><el-input v-model="form.baseUrl" placeholder="http://llm-gw.videoplus.cc/" /></el-form-item>
      </template>
      <p v-else>供应商已保存，直接复用即可。只有地址或密钥发生变化时才需要修改。</p>
      <el-form-item v-if="accounts.length > 1" label="采购账号"><el-select v-model="selection.account" @change="changeAccount"><el-option v-for="row in accounts" :key="row.id" :value="row.id" :label="row.accountCode" /></el-select></el-form-item>
      <el-form-item v-if="credentials.length" label="共享 API 密钥"><el-select v-model="selection.credential"><el-option v-for="row in credentials" :key="row.id" :value="row.id" :label="`${row.name}（已保存）`" /><el-option value="" label="登记新的密钥" /></el-select></el-form-item>
      <el-form-item v-if="!selection.credential" label="API Key" prop="apiKey"><el-input v-model="form.apiKey" type="password" show-password autocomplete="new-password" placeholder="只粘贴密钥，不带 Bearer 前缀" /></el-form-item>
      <p>已预填当前供应商的业务标识、区域和超时，通常不需要修改。密钥保存后不回显。</p>
      <el-collapse v-if="!selection.account"><el-collapse-item title="可选：采购账号与业务标识">
        <el-form-item label="采购账号名称"><el-input v-model="form.accountCode" /></el-form-item>
        <el-form-item label="业务标识"><el-input v-model="form.upstreamProject" /></el-form-item>
        <el-form-item label="区域"><el-input v-model="form.region" /></el-form-item>
        <el-form-item label="环境"><el-radio-group v-model="form.environment"><el-radio value="test">测试</el-radio><el-radio value="production">正式</el-radio></el-radio-group></el-form-item>
      </el-collapse-item></el-collapse>
      <el-button type="primary" :loading="pending" @click="save">保存供应商与密钥</el-button>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-button v-if="error || uncertain" :loading="pending" @click="retry">确认原保存结果，不重复创建</el-button>
    <el-collapse><el-collapse-item title="维护详情（仅在地址或密钥变化时使用）">
      <p>新模型默认共用现有连接和密钥，无需重复配置。修改连接参数或轮换密钥前，请确认供应商的新配置。</p>
      <el-button :disabled="pending || uncertain" @click="emit('advanced')">修改连接参数</el-button>
      <el-button :disabled="pending || uncertain" @click="router.push('/studio/provider-credentials')">查看密钥与轮换记录</el-button>
    </el-collapse-item></el-collapse>
  </main>
</template>
<style scoped>
.supplier-setup { max-width: 760px; margin: auto; color: var(--el-text-color-primary); } header { display: flex; justify-content: space-between; align-items: center; } p { color: var(--el-text-color-secondary); line-height: 1.8; } .el-select { width: 100%; } .el-form { padding: 24px; border: 1px solid var(--el-border-color-light); border-radius: 12px; background: var(--el-bg-color); } .el-collapse, .el-alert { margin: 20px 0; }
</style>
