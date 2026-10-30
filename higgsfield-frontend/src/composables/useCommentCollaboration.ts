import { ref, watch, onBeforeUnmount } from 'vue'
import {
  setCommentReaction,
  updateCommentThread,
  type MediaComment,
  type CommentThread,
} from '@/api/comments'
import { readMembers, type Member } from '@/api/projectWorkspace'
import { useAuthStore } from '@/stores/auth'
export function useCommentCollaboration(
  projectId: () => string | undefined,
  target: () => string,
  refresh: () => Promise<unknown>,
  reload: () => Promise<unknown>,
) {
  const auth = useAuthStore(),
    pending = ref(false),
    error = ref(''),
    members = ref<Member[]>([])
  let epoch = 0,
    reader: AbortController | undefined,
    writer: AbortController | undefined
  const intents = new Map<string, string>()
  watch(
    () => [projectId(), target(), auth.token, JSON.stringify(auth.user?.permissions)],
    async (_, __, cleanup) => {
      epoch++
      reader?.abort()
      writer?.abort()
      pending.value = false
      error.value = ''
      members.value = []
      intents.clear()
      const controller = new AbortController()
      reader = controller
      cleanup(() => controller.abort())
      if (!projectId() || !auth.token) return
      try {
        let page = 1,
          total = 1
        const result: Member[] = []
        while (result.length < total) {
          const response = await readMembers(projectId()!, page++, 'active', controller.signal)
          total = response.total
          result.push(...response.rows)
          if (!response.rows.length) break
        }
        if (!controller.signal.aborted) members.value = result
      } catch {
        /* 无成员阅读权限时不推断或暴露成员。 */
      }
    },
    { immediate: true },
  )
  async function run(
    identity: string,
    action: (key: string, signal: AbortSignal) => Promise<unknown>,
    done: () => Promise<unknown>,
  ) {
    if (pending.value) return
    const stamp = epoch,
      key = intents.get(identity) || crypto.randomUUID()
    intents.set(identity, key)
    const controller = new AbortController()
    writer = controller
    pending.value = true
    error.value = ''
    try {
      await action(key, controller.signal)
      if (stamp !== epoch) return
      intents.delete(identity)
      await done()
    } catch (cause) {
      if (stamp === epoch)
        error.value = cause instanceof Error ? cause.message : '操作失败，可重试原操作'
    } finally {
      if (stamp === epoch) pending.value = false
    }
  }
  const react = (row: MediaComment, emoji: string) => {
    const active = !(row.reactions || []).some(
      (item) => item.emoji === emoji && item.userId === String(auth.user?.user.userId),
    )
    return run(
      `reaction:${row.id}:${emoji}:${active}`,
      (key, signal) => setCommentReaction(row.id, { emoji, active }, key, signal),
      refresh,
    )
  }
  const update = (thread: CommentThread, action: 'resolve' | 'reopen' | 'delete') =>
    run(
      `thread:${thread.id}:${thread.revision}:${action}`,
      (key, signal) =>
        updateCommentThread(thread.id, { revision: thread.revision, action }, key, signal),
      reload,
    )
  onBeforeUnmount(() => {
    epoch++
    reader?.abort()
    writer?.abort()
  })
  return { pending, error, members, react, update }
}
