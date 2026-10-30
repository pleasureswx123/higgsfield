import { ref, watch, onBeforeUnmount } from 'vue'
import {
  listComments,
  listCommentThreads,
  type CommentThread,
  type MediaComment,
  type CommentTarget,
} from '@/api/comments'
import { useAuthStore } from '@/stores/auth'
/** 侧栏展示当前固定版本的讨论；请求串行并在切换目标时作废。 */
export function useCommentOverview(target: () => CommentTarget, visible: () => boolean) {
  const rows = ref<MediaComment[]>([]),
    threads = ref<CommentThread[]>([]),
    loading = ref(false),
    error = ref('')
  const auth = useAuthStore()
  let reader: AbortController | undefined
  async function reload() {
    reader?.abort()
    const controller = new AbortController()
    reader = controller
    if (!visible() || !auth.token) return
    loading.value = true
    error.value = ''
    try {
      const allThreads: CommentThread[] = [],
        allRows: MediaComment[] = []
      for (let page = 1, total = 1; allThreads.length < total; page++) {
        const result = await listCommentThreads(target(), page, controller.signal)
        total = result.total
        allThreads.push(...result.rows)
        if (!result.rows.length) break
      }
      for (const thread of allThreads) {
        let count = 0
        for (let page = 1, total = 1; count < total; page++) {
          const result = await listComments(thread.id, page, controller.signal)
          total = result.total
          count += result.rows.length
          allRows.push(...result.rows)
          if (!result.rows.length) break
        }
      }
      if (!controller.signal.aborted) {
        threads.value = allThreads
        rows.value = allRows.sort((a, b) => Date.parse(a.createTime) - Date.parse(b.createTime))
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '读取评论失败'
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }
  watch(
    () => [JSON.stringify(target()), visible(), auth.token],
    () => {
      reader?.abort()
      rows.value = []
      threads.value = []
      void reload()
    },
    { immediate: true },
  )
  onBeforeUnmount(() => reader?.abort())
  return { rows, threads, loading, error, reload }
}
