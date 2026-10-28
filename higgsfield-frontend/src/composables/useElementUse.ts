import { onActivated, onDeactivated, onBeforeUnmount, ref, watch } from 'vue'
import { searchReferences } from '@/api/references'
import type { ElementRecord } from '@/api/elements'
import type { DraftReference, ModelCapability } from '@/api/creation'
import type { PromptDocument } from '@/utils/promptDocument'
import { prepareElementUse } from '@/utils/elementUse'
import { useAuthStore } from '@/stores/auth'
interface DraftState { prompt: PromptDocument; references: DraftReference[]; model: ModelCapability | null; kind: string }
export function useElementUse(projectId: string, state: () => DraftState, locked: () => boolean, apply: (value: ReturnType<typeof prepareElementUse>) => void) {
  const auth = useAuthStore(), pending = ref(false), error = ref('')
  let epoch = 0, active = true, reader: AbortController | undefined
  function cancel() { epoch++; reader?.abort(); pending.value = false; error.value = '' }
  async function useElements(values: ElementRecord[]) {
    if (!active || !auth.token || pending.value || locked() || !values.length) return false
    const items = [...new Map(values.map(item => [item.id, { ...item }])).values()]
    const fingerprint = JSON.stringify(state()), ticket = epoch, controller = new AbortController()
    reader = controller; pending.value = true; error.value = ''
    try {
      const candidates = []
      for (const item of items) {
        if (item.projectId !== projectId) throw new Error('不能跨项目直接引用元素，请先受控复制到当前项目')
        const result = await searchReferences({ projectId, kind: 'element', elementId: item.id, q: '', pageNum: 1, pageSize: 1 }, controller.signal)
        if (ticket !== epoch || controller.signal.aborted) return false
        const candidate = result.rows.find(value => value.id === item.id && value.kind === 'element' && value.projectId === projectId)
        if (!candidate) throw new Error(`${item.name}没有可引用图片或当前无引用权限，请补图或刷新权限后重试`)
        if (candidate.elementRevisionId !== item.currentRevisionId) throw new Error(`${item.name}已更新，请刷新元素列表后重新选择`)
        candidates.push(candidate)
      }
      if (!active || ticket !== epoch || locked()) return false
      if (fingerprint !== JSON.stringify(state())) throw new Error('读取期间创作内容已变化，请重新使用所选元素')
      const current = state()
      apply(prepareElementUse(current.prompt, current.references, candidates, current.model))
      return true
    } catch (cause) {
      if (ticket === epoch && !controller.signal.aborted) error.value = cause instanceof Error ? cause.message : '元素引用失败'
      return false
    } finally { if (ticket === epoch) pending.value = false }
  }
  watch(() => [auth.token, JSON.stringify(auth.user?.permissions || [])], cancel, { flush: 'sync' })
  onDeactivated(() => { active = false; cancel() })
  onActivated(() => { active = true })
  onBeforeUnmount(() => { active = false; cancel() })
  return { pending, error, useElements }
}
