import { ref, type Ref } from 'vue'
import { setAssetStatus, type Asset, type AssetWorkStatus } from '@/api/assets'
import { useBatchAction } from './useBatchAction'

export function useAssetBatchStatus(rows: () => Asset[], allowed: () => boolean, refresh: () => Promise<void>, selection: Ref<string[]>) {
  const target = ref<AssetWorkStatus>('none')
  // 请求意图包含目标状态；网络异常重试继续原修订和幂等键。
  const batch = useBatchAction(() => rows().map(item => ({ ...item, targetStatus: target.value })), allowed, refresh,
    (item, key) => setAssetStatus(item, item.targetStatus, key),
    item => Boolean(item.allowedActions?.includes('content:review')),
    '素材', '更新状态', '', selection, { confirm: false, preserveSelection: true })
  async function change(status: AssetWorkStatus) {
    if (batch.pending.value) return
    target.value = status
    await batch.execute()
  }
  return { ...batch, change }
}
