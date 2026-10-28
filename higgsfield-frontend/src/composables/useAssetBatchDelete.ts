import type { Ref } from 'vue'
import { recycleAsset, type Asset } from '@/api/assets'
import { useBatchAction } from './useBatchAction'
export function useAssetBatchDelete(rows: () => Asset[], allowed: () => boolean, refresh: () => Promise<void>, selection?: Ref<string[]>) {
  return useBatchAction(() => [...new Map(rows().map(item => [item.id, item])).values()], allowed, refresh,
    (item, key) => recycleAsset(item.id, item.revision, false, key),
    item => Boolean(item.allowedActions?.includes('asset:remove')),
    '素材', '删除', '素材将进入回收站，已存在的固定版本引用保留；逐项校验权限，部分失败不撤销已成功的删除。', selection)
}
