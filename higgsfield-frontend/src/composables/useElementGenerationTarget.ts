import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { readElement, type ElementRecord } from '@/api/elements'
import { readBrief } from '@/api/projectWorkspace'
import { useAuthStore } from '@/stores/auth'

/** 路由只携带目标标识；刷新、恢复与权限变化都重新读取授权信息。 */
export function useElementGenerationTarget(projectId: string) {
  const route = useRoute(),
    auth = useAuthStore()
  const target = ref<ElementRecord>(),
    loading = ref(false),
    error = ref('')
  const requested = computed(
    () => route.params.id === projectId && route.query.targetElement !== undefined,
  )
  const returnTo = computed(() =>
    route.query.returnTo === 'elements' ? '/elements' : `/projects/${projectId}?tab=elements`,
  )
  let active = true,
    reader: AbortController | undefined
  async function load() {
    reader?.abort()
    target.value = undefined
    loading.value = false
    error.value = ''
    if (!active || !auth.token || !requested.value) return
    const id = route.query.targetElement
    if (typeof id !== 'string' || !/^[1-9]\d*$/.test(id)) {
      error.value = '目标元素标识无效，请返回重新选择。'
      return
    }
    const controller = (reader = new AbortController())
    loading.value = true
    try {
      const [{ data: detail }, { data: brief }] = await Promise.all([
        readElement(id, controller.signal),
        readBrief(projectId, controller.signal),
      ])
      if (controller.signal.aborted) return
      if (
        detail.element.projectId !== projectId ||
        !detail.element.allowedActions?.includes('element:edit')
      )
        throw new Error('目标元素已不可编辑或不属于当前项目。')
      if (
        !brief.allowedActions.includes('generation:create') ||
        !brief.allowedActions.includes('asset:create')
      )
        throw new Error('当前项目未授予生成和素材创建权限。')
      target.value = detail.element
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '目标元素核验失败'
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }
  watch(
    () => [
      route.params.id,
      route.query.targetElement,
      auth.token,
      JSON.stringify(auth.user?.permissions || []),
    ],
    () => void load(),
    { immediate: true, flush: 'sync' },
  )
  onDeactivated(() => {
    active = false
    reader?.abort()
    target.value = undefined
    loading.value = false
    error.value = ''
  })
  onActivated(() => {
    if (!active) {
      active = true
      void load()
    }
  })
  onBeforeUnmount(() => {
    active = false
    reader?.abort()
  })
  return { target, requested, returnTo, loading, error, reload: load }
}
