import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { readElement, type ElementRecord } from '@/api/elements'
import { readBrief } from '@/api/projectWorkspace'
import { useAuthStore } from '@/stores/auth'

/** 进入创作前复核目标，列表缓存不作为生成和修改权限的依据。 */
export function useElementGenerationEntry() {
  const auth = useAuthStore(),
    router = useRouter(),
    pending = ref(false),
    error = ref('')
  let active = true,
    epoch = 0,
    reader: AbortController | undefined
  function clear() {
    epoch++
    reader?.abort()
    pending.value = false
    error.value = ''
  }
  async function start(value: ElementRecord) {
    if (!active || !auth.token || pending.value) return
    const source = { ...value },
      ticket = epoch,
      controller = (reader = new AbortController())
    pending.value = true
    error.value = ''
    try {
      const [{ data: detail }, { data: brief }] = await Promise.all([
        readElement(source.id, controller.signal),
        readBrief(source.projectId, controller.signal),
      ])
      if (ticket !== epoch || !active || controller.signal.aborted || !auth.token) return
      if (
        detail.element.projectId !== source.projectId ||
        !detail.element.allowedActions?.includes('element:edit')
      )
        throw new Error('目标元素已不可编辑，请刷新列表。')
      if (
        !brief.allowedActions.includes('generation:create') ||
        !brief.allowedActions.includes('asset:create')
      )
        throw new Error('生成并加入元素需要项目生成和素材创建权限。')
      await router.push({
        name: 'project-detail',
        params: { id: source.projectId },
        query: { tab: 'creation', targetElement: source.id, returnTo: 'elements' },
      })
    } catch (cause) {
      if (ticket === epoch && !controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '无法进入元素图片创作'
    } finally {
      if (ticket === epoch) pending.value = false
    }
  }
  watch(() => [auth.token, JSON.stringify(auth.user?.permissions || [])], clear, { flush: 'sync' })
  onDeactivated(() => {
    active = false
    clear()
  })
  onActivated(() => {
    active = true
  })
  onBeforeUnmount(() => {
    active = false
    clear()
  })
  return { pending, error, start }
}
