<script setup>
import { ref, watch, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import useSettingsStore from '@/store/modules/settings'
import { useModelHub } from '@/composables/studio/useModelHub'
import ModelTestHistory from './ModelTestHistory.vue'
import ModelProfileEditor from '../models/ModelProfileEditor.vue'
import ModelVersionEditor from '../models/ModelVersionEditor.vue'
import ModelVersionActions from '../models/ModelVersionActions.vue'
const testHistory = ref()
const props = defineProps({ startAdd: { type: Boolean, default: false } })
const emit = defineEmits(['configure', 'supplier'])
const router = useRouter(), settings = useSettingsStore(), editor = ref(), versionEditor = ref(), detail = ref()
const { changing, changeError, toggle, connections, selected, connection, models, visible, loading, error, search, kind, can, load } = useModelHub()
const nextModel = computed(() => models.value.find(row => row.state.supported && !row.canToggle && row.state.tone !== 'success'))
const configured = computed(() => models.value.some(row => row.state.tone === 'success'))
let openedAdd = false
watch(() => [loading.value, selected.value, editor.value], () => {
  if (props.startAdd && !openedAdd && !loading.value && selected.value && editor.value && can('model:write')) { openedAdd = true; editor.value.start(selected.value) }
})
function configure(row) {
  if (row.state.supported) emit('configure', { connection: selected.value, model: row.id })
  else detail.value = row
}
let confirming = false
async function changeAvailability(row) {
  if (changing.value || confirming) return
  confirming = true
  try {
  if (row.enabled) {
    try { await ElMessageBox.confirm(`停用 ${row.displayName} 后，不再接受新生成任务。已受理任务继续执行，配置、素材和费用保留。`, '停用模型', { confirmButtonText: '确认停用', cancelButtonText: '取消', type: 'warning' }) } catch { return }
  }
  await toggle(row)
  } finally { confirming = false }
}
async function saved() { detail.value = undefined; await load() }
</script>
<template>
  <main class="app-container model-hub">
    <header><div><h2>供应商与模型</h2><p>供应商配置一次，旗下模型分别管理。启用后，现有和新建项目自动可用。</p></div>
      <div class="actions"><el-button :loading="loading" @click="load">刷新状态</el-button><el-button text @click="settings.toggleTheme()">切换主题</el-button></div>
    </header>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" show-icon />
    <el-alert v-if="changeError" :title="changeError" type="error" :closable="false" show-icon />
    <section class="supplier" v-loading="loading">
      <div><span class="muted">供应商配置</span><h3>{{ connection?.name || '先连接你的供应商' }}</h3>
        <p v-if="connection">{{ connection.status === 'active' ? '连接已启用' : connection.status === 'disabled' ? '连接已停用' : '连接待启用' }} · 地址、账号和密钥供旗下模型复用。</p>
        <p v-else>保存供应商地址和密钥后，再添加旗下的图片或视频模型。</p>
      </div>
      <div class="actions">
        <el-select v-if="connections.length > 1" v-model="selected" placeholder="选择供应商" @change="load"><el-option v-for="row in connections" :key="row.id" :label="row.name" :value="row.id" /></el-select>
        <el-button v-if="can('provider:write')" :type="connection ? 'default' : 'primary'" @click="emit('supplier')">{{ connection ? '供应商设置' : '配置供应商' }}</el-button>

      </div>
    </section>
    <section class="next-step"><strong>{{ !connection ? '下一步：配置供应商' : !models.length ? '下一步：添加第一个模型' : nextModel ? `下一步：完成 ${nextModel.displayName} 的配置` : configured ? '配置已完成，可以在制作端使用' : models.some(row => row.canToggle) ? '模型已停用，可在下方重新启用' : '下一步：确认新模型的接口文档' }}</strong>
      <p>已有配置自动复用，查看和刷新不会收费。模型启用后，项目成员可在制作端直接使用。</p>
      <el-button v-if="nextModel && can('model:write')" type="primary" @click="configure(nextModel)">继续配置 {{ nextModel.displayName }}</el-button>
    </section>
    <section>
      <header><div><h3>模型列表 <small>{{ models.length }}</small></h3><p>图片、视频模型可以共用同一个供应商，每个模型独立配置和启停。</p></div>
        <el-button v-if="can('model:write')" type="primary" :disabled="!selected || loading" @click="editor.start(selected)">新增模型</el-button></header>
      <div class="filters"><el-input v-model="search" clearable placeholder="搜索模型名称或标识" /><el-select v-model="kind" clearable placeholder="全部类型"><el-option label="图片" value="image" /><el-option label="视频" value="video" /></el-select></div>
      <el-table :data="visible" v-loading="loading" empty-text="暂无模型，点击新增模型开始接入">
        <el-table-column label="模型" min-width="180"><template #default="{ row }"><strong>{{ row.displayName }}</strong><div class="muted">{{ row.code }}</div></template></el-table-column>
        <el-table-column label="类型" width="85"><template #default="{ row }">{{ row.kind === 'image' ? '图片' : '视频' }}</template></el-table-column>
        <el-table-column label="状态" min-width="170"><template #default="{ row }"><el-tag :type="row.state.tone">{{ row.state.label }}</el-tag></template></el-table-column>
        <el-table-column label="下一步" min-width="260"><template #default="{ row }">{{ row.state.next }}</template></el-table-column>
        <el-table-column label="操作" width="300"><template #default="{ row }"><el-button link type="primary" @click="configure(row)">{{ row.state.supported ? '配置模型' : '查看接入详情' }}</el-button><el-button v-if="can('credential:read')" link type="primary" @click="testHistory.show(row, selected)">测试记录</el-button><el-button v-if="can('provider:route') && row.canToggle" link :type="row.enabled ? 'danger' : 'primary'" :loading="changing === row.id" :disabled="!!changing" @click="changeAvailability(row)">{{ row.enabled ? '停用' : '启用' }}</el-button><el-button v-if="row.state.supported" link @click="detail = row">更多操作</el-button></template></el-table-column>
      </el-table>
    </section>
    <ModelTestHistory ref="testHistory" />
    <ModelProfileEditor ref="editor" :supplier-name="connection?.name || ''" @saved="saved" />
    <ModelVersionEditor ref="versionEditor" @saved="saved" />
    <el-dialog :model-value="!!detail" :title="detail?.displayName" width="min(760px, 95vw)" @close="detail = undefined">
      <template v-if="detail">
        <el-alert v-if="!detail.state.supported" title="该模型尚未接入简化配置流程" type="info" :closable="false" show-icon
          description="模型已归属于当前供应商。请先确认供应商接口、参数、结果格式和计费文档；不会沿用 mm-imagen2 的价格或发起测试。已有高级配置保留。" />
        <p v-if="!detail.state.supported">下一步：根据供应商文档完成接口适配。已有适配的模型可在高级能力与价格配置中继续维护。</p>
        <p v-else>已有能力版本和测试记录保留。停用仅针对选定版本；不会自动重新测试或修改其他模型。</p>
        <el-collapse><el-collapse-item title="维护详情（通常无需修改）">
        <el-button v-if="can('model:write')" @click="versionEditor.start(detail)">新增能力版本</el-button>
        <el-button v-if="can('billing:price:read')" @click="router.push('/studio/prices')">价格配置</el-button>
        <div v-for="version in detail.versions" :key="version.id" class="version"><strong>第 {{ version.versionNo }} 版 · {{ version.gatewayAlias }}</strong><p>{{ ({ draft: '待验证', verified: '已验证', published: '已发布', disabled: '已停用' })[version.status] || version.status }} · {{ version.region }}</p><el-button v-if="version.status === 'draft' && can('model:write')" @click="versionEditor.start(detail, version)">编辑能力</el-button><ModelVersionActions :version="version" @saved="saved" /></div>
        </el-collapse-item></el-collapse>
      </template>
    </el-dialog>
  </main>
</template>
<style scoped>
.model-hub { max-width: 1200px; margin: auto; color: var(--el-text-color-primary); }
header, .supplier, .actions, .filters { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
header { margin-bottom: 20px; } h2, h3 { margin: 0 0 8px; } p, .muted { color: var(--el-text-color-secondary); line-height: 1.7; } p { margin: 6px 0; }
.supplier, .next-step { padding: 24px; margin-bottom: 24px; border: 1px solid var(--el-border-color-light); border-radius: 12px; background: var(--el-bg-color); }
.next-step { background: var(--el-fill-color-light); } .filters { justify-content: flex-start; margin-bottom: 16px; } .filters .el-input { max-width: 320px; } .el-select { width: 180px; } .version { border-top: 1px solid var(--el-border-color-light); margin-top: 20px; padding-top: 16px; }
small { color: var(--el-text-color-secondary); } @media(max-width:700px) { .supplier { padding: 16px; } .filters .el-input { max-width: 100%; } }
</style>
