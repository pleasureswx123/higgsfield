import type { Ref } from 'vue'
import { recycleElement, type ElementRecord } from '@/api/elements'
import { useBatchAction } from './useBatchAction'
export function useElementBatchDelete(rows: () => ElementRecord[], allowed: () => boolean, refresh: () => Promise<void>, selection?: Ref<string[]>) {
  return useBatchAction(rows, allowed, refresh,
    (item, key) => recycleElement(item.id, item.revision, false, key),
    item => !item.allowedActions || item.allowedActions.includes('element:remove'),
    '元素', '删除', '元素将进入回收站，每项由服务端重新校验权限与修订；部分失败不撤销已成功的删除。', selection)
}
