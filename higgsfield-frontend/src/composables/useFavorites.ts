import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { cancelFavorite, listFavorites, type Favorite, type FavoriteKind } from '@/api/favorites'
import { useAuthStore } from '@/stores/auth'

export function useFavorites() {
  const rows = ref<Favorite[]>([]),
    total = ref(0),
    page = ref(1),
    kind = ref<FavoriteKind | ''>('')
  const loading = ref(false),
    error = ref(''),
    pending = ref('')
  const auth = useAuthStore(),
    keys = new Map<string, string>()
  let active = false,
    reader: AbortController | undefined,
    writer: AbortController | undefined
  async function refresh() {
    reader?.abort()
    const current = new AbortController()
    reader = current
    rows.value = []
    total.value = 0
    loading.value = true
    error.value = ''
    try {
      const result = await listFavorites(page.value, kind.value, current.signal)
      if (!current.signal.aborted) {
        rows.value = result.rows
        total.value = result.total
        if (page.value > 1 && !result.rows.length)
          page.value = Math.max(1, Math.ceil(result.total / 30))
      }
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '收藏加载失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  async function remove(id: string) {
    if (pending.value) return
    const current = new AbortController()
    writer = current
    const key = keys.get(id) || crypto.randomUUID()
    keys.set(id, key)
    pending.value = id
    error.value = ''
    try {
      await cancelFavorite(id, key, current.signal)
      if (!current.signal.aborted) {
        keys.delete(id)
        await refresh()
      }
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '取消收藏失败'
    } finally {
      if (!current.signal.aborted) pending.value = ''
    }
  }
  function clear() {
    reader?.abort()
    writer?.abort()
    rows.value = []
    total.value = 0
    error.value = ''
    loading.value = false
    pending.value = ''
  }
  watch(page, () => {
    if (active) void refresh()
  })
  watch(kind, () => {
    if (page.value !== 1) page.value = 1
    else if (active) void refresh()
  })
  watch(
    () => auth.token,
    () => {
      clear()
      keys.clear()
      if (active && auth.token) void refresh()
    },
    { flush: 'sync' },
  )
  onActivated(() => {
    active = true
    void refresh()
  })
  onDeactivated(() => {
    active = false
    clear()
  })
  onBeforeUnmount(clear)
  return { rows, total, page, kind, loading, error, pending, refresh, remove }
}
