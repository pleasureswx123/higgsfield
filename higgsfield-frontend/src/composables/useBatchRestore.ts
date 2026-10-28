import { useBatchAction } from './useBatchAction'
export interface RecoverableItem { id: string; targetId: string; revision: string; name: string; canRestore: boolean }
export function useBatchRestore<T extends RecoverableItem>(rows: () => T[], allowed: () => boolean, refresh: () => Promise<void>, restoreItem: (item: T, key: string) => Promise<unknown>, label: string, warning: string) {
  const state = useBatchAction(rows, allowed, refresh, restoreItem, item => item.canRestore, label, '恢复', warning)
  return { ...state, restore: state.execute }
}
