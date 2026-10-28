import { recycleAsset, type RecycledAsset } from '@/api/assets'
import { useBatchRestore } from './useBatchRestore'
export function useAssetBatchRestore(rows: () => RecycledAsset[], allowed: () => boolean, refresh: () => Promise<void>) {
  return useBatchRestore(rows, allowed, refresh,
    (item, key) => recycleAsset(item.targetId, item.revision, true, key),
    '素材', '恢复不会重新提交生成任务；目标目录及引用由服务端校验。')
}
