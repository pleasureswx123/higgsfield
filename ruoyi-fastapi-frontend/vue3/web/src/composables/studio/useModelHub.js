import { ref, computed, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import useUserStore from '@/store/modules/user'
import * as api from '@/api/studio/modelSetup'
import { setupRows } from '@/utils/modelSetup'
import { modelHubState, toggleModelRoutes } from '@/utils/modelHub'

export function useModelHub() {
  const user = useUserStore()
  const connections = ref([]), selected = ref(''), models = ref([]), loading = ref(false), error = ref('')
  const search = ref(''), kind = ref('')
  const can = permission => user.permissions.includes('*:*:*') || user.permissions.includes(permission)
  const connection = computed(() => connections.value.find(row => row.id === selected.value))
  const visible = computed(() => models.value.filter(row => (!kind.value || row.kind === kind.value)
    && `${row.displayName} ${row.code}`.toLowerCase().includes(search.value.trim().toLowerCase())))
  const changing = ref(''), changeError = ref('')
  let changeAttempt
  let identity = 0
  async function toggle(row) {
    if (changing.value || !can('provider:route')) return
    const ticket = identity, token = user.token
    const current = () => active && identity === ticket && user.token === token
    changing.value = row.id; changeError.value = ''
    try {
      if (changeAttempt && changeAttempt.modelId !== row.id) throw new Error('上一项操作结果尚未确认，请先重试原模型')
      if (!changeAttempt) {
        const config = (await api.getPlatformRouting()).data
        if (!current()) return
        const enabled = !row.enabled
        changeAttempt = { modelId: row.id, payload: toggleModelRoutes(config, row.id, enabled), key: crypto.randomUUID() }
      }
      await api.savePlatformRouting(changeAttempt.payload, changeAttempt.key)
      if (!current()) return
      changeAttempt = undefined
      await load()
    } catch (cause) {
      if (!current()) return
      if (cause?.code === 601 || cause?.response?.status === 422) changeAttempt = undefined
      changeError.value = cause?.message || '操作未完成，请重试确认原请求'
    }
    finally { if (current()) changing.value = '' }
  }
  let active = true, epoch = 0
  async function load() {
    const ticket = ++epoch, token = user.token
    models.value = []; error.value = ''
    if (!active || !token) return
    loading.value = true
    const current = () => active && epoch === ticket && user.token === token
    const read = async action => { const value = await action(); if (!current()) throw new Error('读取已失效'); return value }
    const rows = (loader, params) => setupRows(query => read(() => loader(query)), params)
    try {
      if (!can('provider:read') || !can('model:read')) throw new Error('需要供应商和模型查看权限')
      connections.value = await rows(api.listProviderConnections)
      if (!connections.value.some(row => row.id === selected.value)) selected.value = connections.value.length === 1 ? connections.value[0].id : ''
      if (!selected.value) return
      let routes = null
      if (can('provider:route')) {
        try { routes = (await read(() => api.getPlatformRouting())).data.routes }
        catch (cause) { if (!current()) throw cause; error.value = '全平台开放状态未能读取；模型配置仍保留。' }
      }
      const parents = await rows(api.listModels, { connectionId: selected.value })
      const result = []
      for (const parent of parents) {
        const versions = await rows(query => api.listModelVersions(parent.id, query))
        result.push({ ...parent, versions, state: modelHubState(parent, versions, routes), canToggle: !!routes?.some(row => row.modelId === parent.id) && versions.some(row => row.status === 'published'), enabled: !!routes?.some(row => row.modelId === parent.id && row.enabled) })
      }
      if (current()) models.value = result
    } catch (cause) { if (current()) error.value = cause?.message || '读取失败，请重试' }
    finally { if (current()) loading.value = false }
  }
  const clear = () => { epoch++; identity++; changing.value = ''; changeAttempt = undefined; changeError.value = ''; models.value = []; connections.value = []; selected.value = ''; error.value = ''; loading.value = false }
  onMounted(load)
  onActivated(() => { if (!active) { active = true; load() } })
  onDeactivated(() => { active = false; clear() })
  onBeforeUnmount(() => { active = false; clear() })
  watch(() => [user.token, JSON.stringify(user.permissions)], () => { clear(); if (active) load() }, { flush: 'sync' })
  return { changing, changeError, toggle, connections, selected, connection, models, visible, loading, error, search, kind, can, load }
}
