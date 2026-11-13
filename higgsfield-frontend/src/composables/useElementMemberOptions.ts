import { onBeforeUnmount, ref } from 'vue'
import { readMembers, type Member } from '@/api/projectWorkspace'

export function useElementMemberOptions() {
  const members = ref<Member[]>([])
  const loading = ref(false)
  const error = ref('')
  let controller: AbortController | undefined
  async function load(projectId: string) {
    controller?.abort()
    const current = controller = new AbortController()
    loading.value = true
    error.value = ''
    members.value = []
    try {
      const result: Member[] = []
      for (let page = 1; ; page++) {
        const response = await readMembers(projectId, page, 'active', current.signal)
        result.push(...response.rows)
        if (result.length >= response.total || !response.rows.length) break
      }
      if (!current.signal.aborted) members.value = result
    } catch (cause) {
      if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '成员加载失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  onBeforeUnmount(() => controller?.abort())
  return { members, loading, error, load }
}
