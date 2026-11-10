import { ref, watch, onBeforeUnmount } from 'vue'
import { readMemberCandidates, type Candidate } from '@/api/projectWorkspace'

export function useMemberCandidates(projectId: string) {
  const keyword = ref(''), items = ref<Candidate[]>([]), loading = ref(false), error = ref('')
  const hasNext = ref(false)
  let page = 0, sequence = 0, timer: ReturnType<typeof setTimeout> | undefined
  async function load(more = false) {
    if (more && (loading.value || !hasNext.value)) return
    clearTimeout(timer)
    const stamp = ++sequence, nextPage = more ? page + 1 : 1
    loading.value = true; error.value = ''
    if (!more) { items.value = []; hasNext.value = false }
    try {
      const result = await readMemberCandidates(projectId, keyword.value.trim(), nextPage)
      if (stamp !== sequence) return
      items.value = more ? [...items.value, ...result.rows] : result.rows
      hasNext.value = result.hasNext; page = nextPage
    } catch (cause) {
      if (stamp === sequence) error.value = cause instanceof Error ? cause.message : '人员加载失败，请重试'
    } finally { if (stamp === sequence) loading.value = false }
  }
  function reset() {
    sequence++; keyword.value = ''; clearTimeout(timer); items.value = []; page = 0
    void load()
  }
  watch(keyword, () => {
    clearTimeout(timer); sequence++; items.value = []; hasNext.value = false; loading.value = true
    timer = setTimeout(() => void load(), 250)
  }, { flush: 'sync' })
  onBeforeUnmount(() => { sequence++; clearTimeout(timer) })
  return { keyword, items, loading, error, hasNext, load, reset }
}
