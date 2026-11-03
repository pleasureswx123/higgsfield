import { ref, watch, onBeforeUnmount, onDeactivated } from 'vue'
import useUserStore from '@/store/modules/user'
import * as api from '@/api/studio/modelSetup'
import { setupRows } from '@/utils/modelSetup'

/** 只读聚合模型各能力版本、各密钥版本的测试记录。 */
export function useModelTestHistory() {
  const user = useUserStore()
  const open = ref(false), loading = ref(false), error = ref(''), records = ref([]), model = ref()
  let epoch = 0
  function close() { epoch++; open.value = false; records.value = []; loading.value = false; error.value = '' }
  async function show(row, connectionId) {
    close(); open.value = true; model.value = row; loading.value = true
    const ticket = epoch
    const rows = (fn, params) => setupRows(async query => {
      const result = await fn(query)
      if (ticket !== epoch) throw new Error('读取已失效')
      return result
    }, params)
    try {
      const ids = new Set(row.versions.map(version => version.id))
      const result = []
      for (const account of await rows(api.listProviderAccounts, { connectionId })) {
        for (const credential of await rows(api.listCredentials, { accountId: account.id })) {
          for (const version of await rows(query => api.listCredentialVersions(credential.id, query))) {
            const tests = await rows(query => api.listCredentialTests(version.id, query))
            result.push(...tests.filter(test => ids.has(test.modelVersionId)))
          }
        }
      }
      if (ticket === epoch) records.value = result.sort((a, b) => Date.parse(b.createTime) - Date.parse(a.createTime))
    } catch (cause) { if (ticket === epoch) error.value = cause?.message || '测试记录读取失败，请重试' }
    finally { if (ticket === epoch) loading.value = false }
  }
  watch(() => [user.token, JSON.stringify(user.permissions)], close, { flush: 'sync' })
  onBeforeUnmount(close)
  onDeactivated(close)
  return { open, loading, error, records, model, show, close }
}
