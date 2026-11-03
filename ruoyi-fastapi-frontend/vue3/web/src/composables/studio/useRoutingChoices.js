import { computed, ref, onMounted, onActivated, onDeactivated, onBeforeUnmount, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import { listModels } from '@/api/studio/models'
import { listProviderAccounts } from '@/api/studio/providers'
import { listCredentials } from '@/api/studio/credentials'
import { listGovernedProjects } from '@/api/studio/governance'
import { setupRows } from '@/utils/modelSetup'
import { hasPermission } from '@/utils/studioWorkbench'

export function useRoutingChoices() {
  const user = useUserStore(), projects = ref([]), models = ref([]), accounts = ref([]), credentials = ref([])
  const loading = ref(false), errors = ref([])
  const canProjects = computed(() => hasPermission(user.permissions, 'project:govern'))
  const canNames = computed(() => ['model:read', 'provider:read', 'credential:read'].every(value => hasPermission(user.permissions, value)))
  let epoch = 0, active = true
  function clear() { epoch++; projects.value = []; models.value = []; accounts.value = []; credentials.value = []; errors.value = []; loading.value = false }
  async function load() {
    clear()
    if (!active || !user.token) return
    const ticket = epoch, token = user.token
    const current = () => active && ticket === epoch && user.token === token
    loading.value = true
    const tasks = []
    function add(loader, target, label) {
      tasks.push((async () => {
        try {
          const values = await setupRows(async query => {
            if (!current()) throw new Error('读取已失效')
            return await loader(query)
          })
          if (current()) target.value = values
        } catch (error) { if (current()) errors.value.push(`${label}：${error?.message || '读取失败'}`) }
      })())
    }
    if (canProjects.value) add(listGovernedProjects, projects, '项目名称')
    if (canNames.value) { add(listModels, models, '模型名称'); add(listProviderAccounts, accounts, '采购账号'); add(listCredentials, credentials, '密钥名称') }
    await Promise.allSettled(tasks)
    if (current()) loading.value = false
  }
  const accountsFor = modelId => accounts.value.filter(row => row.connectionId === models.value.find(model => model.id === modelId)?.connectionId)
  const credentialsFor = accountId => credentials.value.filter(row => row.accountId === accountId)
  onMounted(load)
  onActivated(() => { if (!active) { active = true; load() } })
  onDeactivated(() => { active = false; clear() })
  onBeforeUnmount(() => { active = false; clear() })
  watch(() => [user.token, JSON.stringify(user.permissions)], () => { clear(); if (active) load() }, { flush: 'sync' })
  return { projects, models, accountsFor, credentialsFor, canProjects, canNames, loading, errors, load }
}
