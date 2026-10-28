import { recycleElement, type RecycledElement } from '@/api/elements'
import { useBatchRestore } from './useBatchRestore'
export function useElementBatchRestore(rows: () => RecycledElement[], allowed: () => boolean, refresh: () => Promise<void>) {
  return useBatchRestore(rows, allowed, refresh,
    (item, key) => recycleElement(item.targetId, item.revision, true, key),
    '元素', '恢复保留原有版本，不自动重新提交草稿或生成任务。')
}
