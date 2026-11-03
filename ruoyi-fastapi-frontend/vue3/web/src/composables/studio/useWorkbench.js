import { computed, reactive, ref, onMounted, onActivated, onDeactivated, onBeforeUnmount, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import usePermissionStore from '@/store/modules/permission'
import * as api from '@/api/studio/workbench'
import { setupRows } from '@/utils/modelSetup'
import { authorizedPaths, hasPermission, workbenchEntries, workbenchNext, workbenchRole } from '@/utils/studioWorkbench'

export function useWorkbench() {
  const user = useUserStore(), permission = usePermissionStore()
  const loading = ref(false), issues = ref([]), updated = ref(''), models = ref([])
  const facts = reactive({ connections: null, published: null, drafts: null, platformModels: null, incidents: null })
  const can = value => hasPermission(user.permissions, value)
  const paths = computed(() => new Set(authorizedPaths(permission.routes)))
  const authorizedEntries = computed(() => workbenchEntries.filter(row => can(row.permission) && paths.value.has(row.path)))
  const role = computed(() => workbenchRole(user.roles, authorizedEntries.value))
  const entries = computed(() => authorizedEntries.value.filter(row => role.value === 'finance' ? row.key === 'billing' : role.value === 'platform' ? row.key !== 'billing' : true))
  const next = computed(() => workbenchNext(facts, entries.value))
  let active = true, epoch = 0
  function clear() {
    epoch++; models.value = []; issues.value = []; updated.value = ''; loading.value = false
    for (const key of Object.keys(facts)) facts[key] = null
  }
  async function load() {
    clear()
    if (!active || !user.token) return
    const ticket = epoch, token = user.token
    const current = () => active && ticket === epoch && token === user.token
    const read = async action => {
      if (!current()) throw new Error('读取已失效')
      const result = await action()
      if (!current()) throw new Error('读取已失效')
      return result
    }
    const all = (loader, query) => setupRows(params => read(() => loader(params)), query)
    loading.value = true
    const tasks = []
    const task = (label, action) => tasks.push((async () => {
      try { await action() } catch (error) { if (current()) issues.value.push(`${label}：${error?.message || '读取失败'}`) }
    })())
    if (role.value !== 'finance' && can('provider:read')) task('供应商状态', async () => {
      const result = await read(() => api.listProviderConnections({ pageNum: 1, pageSize: 1 }))
      facts.connections = Number(result.total)
    })
    if (role.value !== 'finance' && can('model:read')) task('模型状态', async () => {
      const parents = await all(api.listModels)
      const records = []
      for (const parent of parents) {
        const versions = await all(query => api.listModelVersions(parent.id, query))
        records.push({ name: parent.displayName, kind: parent.kind,
          published: versions.filter(row => row.status === 'published').length,
          drafts: versions.filter(row => ['draft', 'verified'].includes(row.status)).length })
      }
      models.value = records
      facts.published = records.reduce((sum, row) => sum + row.published, 0)
      facts.drafts = records.reduce((sum, row) => sum + row.drafts, 0)
    })
    if (role.value !== 'finance' && can('provider:route')) task('全平台模型', async () => {
      const result = await read(() => api.getPlatformRouting())
      facts.platformModels = new Set(result.data.routes.filter(row => row.enabled && row.credentials.length).map(row => row.modelId)).size
    })
    if (role.value !== 'finance' && can('operations:read')) task('异常记录', async () => {
      const result = await read(() => api.listIncidents({ pageNum: 1, pageSize: 1 }))
      facts.incidents = Number(result.total)
    })
    await Promise.allSettled(tasks)
    if (current()) { loading.value = false; updated.value = new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }) }
  }
  watch(() => [user.token, JSON.stringify(user.permissions), JSON.stringify(user.roles)], () => { clear(); if (active) load() }, { flush: 'sync' })
  onMounted(load)
  onActivated(() => { if (!active) { active = true; load() } })
  onDeactivated(() => { active = false; clear() })
  onBeforeUnmount(() => { active = false; clear() })
  return { user, role, entries, next, facts, models, issues, loading, updated, paths, load }
}
