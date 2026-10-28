import { onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { saveFavorite, type FavoriteTarget } from '@/api/favorites'
import { useAuthStore } from '@/stores/auth'

export function useFavoriteAction(target: () => FavoriteTarget) {
  const pending = ref(false),
    saved = ref(false),
    error = ref('')
  const auth = useAuthStore()
  let controller: AbortController | undefined,
    key = ''
  function reset() {
    controller?.abort()
    pending.value = false
    saved.value = false
    error.value = ''
    key = ''
  }
  async function save() {
    if (pending.value || saved.value) return
    const current = new AbortController()
    controller = current
    key ||= crypto.randomUUID()
    pending.value = true
    error.value = ''
    try {
      await saveFavorite(target(), key, current.signal)
      if (!current.signal.aborted) saved.value = true
    } catch (cause) {
      if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '收藏失败'
    } finally {
      if (!current.signal.aborted) pending.value = false
    }
  }
  watch(() => [JSON.stringify(target()), auth.token], reset, { flush: 'sync' })
  onDeactivated(reset)
  onBeforeUnmount(reset)
  return { pending, saved, error, save }
}
