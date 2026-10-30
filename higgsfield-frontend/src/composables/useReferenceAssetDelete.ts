import { onBeforeUnmount, ref, watch } from 'vue'
import { readAsset } from '@/api/assets'
import type { ReferenceCandidate } from '@/api/references'
import { useAssetActions } from './useAssetActions'

/** 删除前重新读取素材权限和修订，复用回收站及幂等重试流程。 */
export function useReferenceAssetDelete(projectId: string, visible: () => boolean,
  canSelect: (row: ReferenceCandidate) => boolean, changed: () => void) {
  const checking = ref(false), error = ref('')
  const actions = useAssetActions(projectId, changed, visible)
  let controller: AbortController | undefined
  function cancelRead() { controller?.abort(); checking.value = false; error.value = '' }
  async function remove(row: ReferenceCandidate) {
    if (row.kind !== 'asset' || !canSelect(row) || checking.value || actions.actionsLocked.value) return
    cancelRead()
    const reader = new AbortController(); controller = reader; checking.value = true
    try {
      const result = await readAsset(row.id, reader.signal)
      if (reader.signal.aborted || !canSelect(row)) return
      if (!result.data.allowedActions?.includes('asset:remove')) throw new Error('当前素材没有删除权限')
      await actions.lifecycle(result.data, false)
    } catch (cause) {
      if (!reader.signal.aborted) error.value = cause instanceof Error ? cause.message : '无法读取删除权限'
    } finally { if (!reader.signal.aborted) checking.value = false }
  }
  watch(visible, cancelRead)
  onBeforeUnmount(cancelRead)
  return { actions, checking, error, remove }
}
