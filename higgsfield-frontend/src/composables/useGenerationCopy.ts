import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getGenerationInput, type GenerationSnapshot } from '@/api/generations'
import { saveCreationDraft, type DraftBody, type DraftReference, type Scalar } from '@/api/creation'

export function useGenerationCopy(snapshot: () => GenerationSnapshot | undefined) {
  const auth = useAuthStore(),
    router = useRouter()
  const pending = ref(false),
    error = ref(''),
    retryable = ref(false)
  let active = true,
    epoch = 0,
    request: AbortController | undefined
  let attempt:
    | {
        projectId: string
        kind: 'image' | 'video'
        body: DraftBody
        references: DraftReference[]
        key: string
        draftId?: string
      }
    | undefined
  function reset() {
    epoch++
    request?.abort()
    attempt = undefined
    pending.value = false
    retryable.value = false
    error.value = ''
  }
  async function copy() {
    const task = snapshot()
    if (!active || !auth.token || pending.value || !task || task.kind === 'chat') return false
    if (!attempt && !task.allowedActions.includes('generation:copy-input')) return false
    const ticket = epoch
    pending.value = true
    error.value = ''
    try {
      if (!attempt) {
        request = new AbortController()
        const input = (await getGenerationInput(task.id, request.signal)).data
        if (ticket !== epoch) return false
        const parameters: Record<string, Scalar> = {}
        for (const [name, value] of Object.entries(input.parameters)) {
          if (
            typeof value !== 'string' &&
            typeof value !== 'boolean' &&
            !(typeof value === 'number' && Number.isFinite(value))
          )
            throw new Error('原任务包含当前编辑器不支持的参数，未创建草稿，请联系管理员核查')
          parameters[name] = value as Scalar
        }
        // 固定重试内容与幂等键；通信结果未知时不能另建一份草稿。
        attempt = JSON.parse(
          JSON.stringify({
            projectId: task.projectId,
            kind: task.kind,
            key: crypto.randomUUID(),
            body: {
              schemaVersion: 1,
              prompt: input.prompt,
              parameters,
              modelVersionId: input.modelVersionId,
              sourceJobId: task.id,
              folderId: null,
            },
            references: input.references,
          }),
        )
      }
      const intent = attempt!
      if (!intent.draftId) {
        const saved = await saveCreationDraft(
          null,
          intent.projectId,
          intent.kind,
          intent.body,
          intent.key,
          intent.references,
        )
        if (ticket !== epoch) return false
        intent.draftId = saved.data.id
      }
      const failure = await router.push({
        name: 'project-detail',
        params: { id: intent.projectId },
        query: { tab: 'creation', draft: intent.draftId },
      })
      if (ticket !== epoch) return false
      if (failure) throw new Error('草稿已保存，页面未切换；请重试打开，不会重复创建')
      attempt = undefined
      retryable.value = false
      return true
    } catch (cause) {
      if (ticket !== epoch) return false
      const { code, errorCode } = (cause ?? {}) as { code?: number; errorCode?: string }
      retryable.value =
        Boolean(attempt) &&
        (Boolean(attempt?.draftId) ||
          errorCode === 'IDEMPOTENCY_IN_PROGRESS' ||
          code === undefined ||
          code === 0 ||
          (code >= 500 && code !== 601))
      if (!retryable.value) attempt = undefined
      error.value = cause instanceof Error ? cause.message : '复制草稿失败，请重试'
      return false
    } finally {
      if (ticket === epoch) pending.value = false
    }
  }
  watch(
    () => [
      snapshot()?.id,
      auth.token,
      auth.user?.user.userId,
      JSON.stringify(auth.user?.permissions ?? []),
    ],
    reset,
    { flush: 'sync' },
  )
  onDeactivated(() => {
    active = false
    epoch++
    request?.abort()
    pending.value = false
    retryable.value = Boolean(attempt)
  })
  onActivated(() => {
    active = true
  })
  onBeforeUnmount(() => {
    active = false
    reset()
  })
  return { pending, error, retryable, copy }
}
