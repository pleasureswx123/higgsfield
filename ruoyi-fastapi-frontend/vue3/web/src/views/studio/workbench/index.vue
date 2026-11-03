<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import useSettingsStore from '@/store/modules/settings'
import { useWorkbench } from '@/composables/studio/useWorkbench'
const router = useRouter(), settings = useSettingsStore()
const { user, role, entries, next, facts, models, issues, loading, updated, paths, load } = useWorkbench()
const financeOnly = computed(() => role.value === 'finance')
const display = value => value === null ? '—' : value
const go = path => router.push(path)
</script>
<template>
  <main class="app-container workbench" :class="{ 'is-dark': settings.isDark }">
    <header class="workbench-heading">
      <div><span class="eyebrow">AI 制作平台 · {{ financeOnly ? '费用管理' : role === 'combined' ? '综合管理' : role === 'platform' ? '平台管理' : '管理端' }}</span><h1>{{ financeOnly ? '费用工作台' : role === 'combined' ? '综合管理工作台' : role === 'platform' ? '平台工作台' : '工作台' }}</h1><p>{{ user.name }}，{{ financeOnly ? '从这里查看 Token 消耗和费用明细。' : role === 'combined' ? '从这里管理模型、费用与团队。' : entries.some(row => row.key === 'users' || row.key === 'departments') ? '从这里管理模型、团队和日常运行。' : '从这里完成模型接入和日常检查。' }}</p></div>
      <div class="actions"><el-button :loading="loading" @click="load">刷新状态</el-button></div>
    </header>
    <section v-if="entries.length" class="entry-section"><h2>{{ financeOnly ? '费用查询' : '日常管理' }}</h2><div class="entry-grid">
      <article v-for="entry in entries" :key="entry.key"><h3>{{ entry.title }}</h3><p>{{ entry.description }}</p><el-button @click="go(entry.path)">{{ entry.action }}</el-button></article>
    </div></section>
    <section class="start-card">
      <span class="eyebrow">{{ loading ? '正在读取工作台'  : '建议下一步' }}</span>
      <h2>{{ loading ? (financeOnly ? '正在准备费用入口…' : '正在核对已有配置…') : next.heading }}</h2>
      <p>{{ loading ? '只读取状态，不创建配置、不调用供应商生成。' : next.detail }}</p>
      <el-button v-if="next.path && !loading" type="primary" size="large" @click="go(next.path)">{{ next.action }}</el-button>
    </section>
    <section v-if="entries.some(row => row.key === 'setup')" class="journey" aria-label="管理员上手顺序">
      <div><span>01</span><h3>接入模型</h3><p>连接供应商，确认价格，测试并启用。</p><el-button link type="primary" @click="go('/studio/provider-connections')">开始 / 继续接入 →</el-button></div>
      <div><span>02</span><h3>全平台自动可用</h3><p>启用后覆盖现有和新建项目，无需逐项目配置；项目权限保持不变。</p></div>
      <div><span>03</span><h3>验证生成结果</h3><p>让项目成员在制作端生成 1 张图片，检查保存结果和实际费用。</p><el-button v-if="paths.has('/studio/calls')" link type="primary" @click="go('/studio/calls')">查看运行结果 →</el-button></div>
    </section>
    <section v-if="!financeOnly" class="fact-grid" aria-label="真实配置状态">
      <div v-if="paths.has('/studio/provider-connections')"><span>已登记供应商连接</span><strong>{{ display(facts.connections) }}</strong></div>
      <div v-if="paths.has('/studio/models')"><span>已发布模型能力版本</span><strong>{{ display(facts.published) }}</strong></div>
      <div v-if="paths.has('/studio/routing')"><span>已启用全平台模型</span><strong>{{ display(facts.platformModels) }}</strong></div>
      <div v-if="paths.has('/studio/incidents')"><span>异常记录</span><strong>{{ display(facts.incidents) }}</strong><el-button link type="primary" @click="go('/studio/incidents')">进入核查</el-button></div>
    </section>
    <p v-if="!financeOnly" class="fact-note">{{ updated ? `状态读取时间：${updated}（上海时间）。` : '' }}“—”表示尚未读取或没有查看权限。配置状态不代表真实调用已通过，异常记录也不等于待处理数量。</p>
    <el-alert v-for="issue in issues" :key="issue" :title="issue" type="warning" :closable="false" show-icon class="read-error" />
    <section v-if="!financeOnly && models.length" class="model-summary"><h2>已有模型</h2>
      <div v-for="(model, index) in models" :key="index" class="model-row"><div><strong>{{ model.name }}</strong><span>{{ model.kind === 'image' ? '图片模型' : '视频模型' }}</span></div>
        <div><el-tag v-if="model.published" type="success">{{ model.published }} 个已发布版本</el-tag><el-tag v-if="model.drafts" type="warning">{{ model.drafts }} 个待完成版本</el-tag><span v-if="!model.published && !model.drafts">暂无可用能力版本</span></div>
        <el-button v-if="paths.has('/studio/provider-connections')" link type="primary" @click="go('/studio/provider-connections')">{{ model.drafts ? '继续接入' : '查看接入配置' }}</el-button>
      </div>
    </section>

  </main>
</template>
<style scoped>
.workbench { --start-bg: #edf4fc; --start-border: #c9d9ed; --start-title: #1d3048; --start-text: #465c75; max-width: 1240px; margin: 0 auto; color: var(--el-text-color-primary); }
.workbench-heading, .actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.workbench-heading { margin: 10px 0 26px; } h1 { font-size: 28px; margin: 8px 0; } h2 { font-size: 20px; } h3 { font-size: 17px; }
p { color: var(--el-text-color-secondary); line-height: 1.8; }
.eyebrow { color: var(--el-text-color-secondary); font-size: 13px; }
.workbench.is-dark { --start-bg: #192532; --start-border: #34485f; --start-title: #edf3fc; --start-text: #bacbdd; }
.start-card { color: var(--start-title); border: 1px solid var(--start-border); background: var(--start-bg); padding: 28px; border-radius: 12px; }
.start-card p, .start-card .eyebrow { color: var(--start-text); }
.start-card h2 { color: var(--start-title); font-size: 24px; margin: 12px 0; } .start-card p { max-width: 780px; margin-bottom: 24px; }
.journey { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 24px; margin: 26px 0; }
.journey > div, .entry-grid article { background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); padding: 22px; border-radius: 10px; }
.journey > div > span { color: var(--el-color-primary); font-size: 22px; font-weight: 700; }
.fact-grid { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 24px; }
.fact-grid > div { flex: 1 1 180px; display: flex; flex-direction: column; align-items: flex-start; gap: 12px; padding: 20px; border: 1px solid var(--el-border-color-light); border-radius: 10px; background: var(--el-bg-color); }
.fact-grid span { color: var(--el-text-color-secondary); font-size: 13px; } .fact-grid strong { font-size: 30px; }
.fact-note { font-size: 12px; } .entry-section { margin: 24px 0 30px; } .entry-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 18px; }
.entry-grid h3 { margin-top: 0; } .entry-grid p { min-height: 52px; } .model-summary { margin-top: 28px; }
.model-row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; padding: 20px 0; border-bottom: 1px solid var(--el-border-color-light); }
.model-row span, .model-row .el-tag { margin-left: 12px; } .model-row > div > span:not(.el-tag) { color: var(--el-text-color-secondary); font-size: 13px; }
.read-error { margin: 10px 0; } .help { margin: 28px 0; border: 1px solid var(--el-border-color-light); border-radius: 10px; padding: 18px; } summary { cursor: pointer; }
@media (max-width: 760px) { .journey, .entry-grid { grid-template-columns: 1fr; } .start-card { padding: 20px; } }
</style>
