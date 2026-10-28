import { actOnFolder, type RecycleFolder } from '@/api/folders'
import { useBatchRestore } from './useBatchRestore'
export function useFolderBatchRestore(rows: () => RecycleFolder[], allowed: () => boolean, refresh: () => Promise<void>) {
  return useBatchRestore(rows, allowed, refresh,
    (item, key) => actOnFolder(item.targetId, 'restore', { revision: item.revision }, key),
    '文件夹', '已经移动到父级的内容不会自动移回。')
}
