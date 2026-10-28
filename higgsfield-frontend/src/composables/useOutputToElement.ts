import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { readElement, saveElement, type ElementDetail, type ElementFields } from '@/api/elements'
import { getOutput } from '@/api/generations'
import { outputToAsset, type Asset } from '@/api/assets'
import { readBrief } from '@/api/projectWorkspace'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

export interface ElementGenerationDestination {
  id: string
  projectId: string
  name: string
}

/** 两步写入分别保留幂等意图；素材已创建而元素保存失败时仅重试绑定。 */
export function useOutputToElement(
  outputId: string,
  jobId: string,
  value: ElementGenerationDestination,
) {
  const destination = { ...value },
    auth = useAuthStore(),
    active = ref(true)
  const detail = ref<ElementDetail>(),
    asset = ref<Asset>(),
    result = ref<ElementDetail>()
  const loading = ref(false),
    saving = ref(false),
    uncertain = ref(false),
    ready = ref(false),
    error = ref('')
  const locked = computed(() => saving.value || uncertain.value)
  let epoch = 0,
    alive = true,
    reader: AbortController | undefined
  let assetIntent:
    { data: { projectId: string; folderId: null; name: string }; key: string } | undefined
  let saveIntent: { revision: string; data: ElementFields; key: string } | undefined
  const current = (ticket: number) => alive && ticket === epoch && !!auth.token
  const definitive = (cause: unknown) =>
    cause instanceof ApiError &&
    ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') ||
      (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
  async function inspect() {
    reader?.abort()
    ready.value = false
    detail.value = undefined
    if (!active.value || !auth.token || !alive) return false
    const controller = (reader = new AbortController())
    loading.value = true
    try {
      const [elementResponse, outputResponse, briefResponse] = await Promise.all([
        readElement(destination.id, controller.signal),
        getOutput(outputId, controller.signal),
        readBrief(destination.projectId, controller.signal),
      ])
      if (controller.signal.aborted) return false
      const element = elementResponse.data,
        output = outputResponse.data,
        actions = briefResponse.data.allowedActions
      if (
        element.element.projectId !== destination.projectId ||
        !element.element.allowedActions?.includes('element:edit')
      )
        throw new Error('目标元素已不可编辑或不属于当前项目')
      if (!actions.includes('asset:create')) throw new Error('当前项目没有素材创建权限')
      if (
        output.jobId !== jobId ||
        output.kind !== 'image' ||
        output.archiveState !== 'archived' ||
        output.file?.state !== 'ready' ||
        !output.allowedActions.includes('output:to-asset')
      )
        throw new Error('作品尚未归档就绪或没有转素材权限')
      detail.value = JSON.parse(JSON.stringify(element))
      ready.value = true
      return true
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '无法核验作品与目标元素'
      return false
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }
  async function submit() {
    if (!active.value || !auth.token || saving.value || loading.value || result.value) return
    const ticket = epoch
    saving.value = true
    error.value = ''
    try {
      if (!(await inspect()) || !current(ticket) || !active.value) return
      if (!asset.value) {
        assetIntent ||= {
          data: {
            projectId: destination.projectId,
            folderId: null,
            name: `${detail.value!.element.name} · 生成图片`.slice(0, 200),
          },
          key: crypto.randomUUID(),
        }
        uncertain.value = true
        try {
          const response = await outputToAsset(
            outputId,
            assetIntent.data,
            assetIntent.key,
            new AbortController().signal,
          )
          if (!current(ticket)) return
          asset.value = response.data
          assetIntent = undefined
          uncertain.value = false
        } catch (cause) {
          if (!current(ticket)) return
          if (definitive(cause)) {
            assetIntent = undefined
            uncertain.value = false
          }
          throw cause
        }
      }
      if (!current(ticket) || !active.value || !ready.value) return
      if (!saveIntent) {
        // 素材创建期间目标可能被他人修改；再读一次后冻结整份保存快照。
        if (!(await inspect()) || !current(ticket) || !active.value) return
        const source = detail.value!,
          version = asset.value!.currentVersionId
        if (asset.value!.mediaType !== 'image') throw new Error('转入素材不是图片，未修改元素')
        if (source.currentRevision.media.some((item) => item.assetVersionId === version)) {
          result.value = source
          return
        }
        const media = [...source.currentRevision.media]
          .sort((a, b) => a.ordinal - b.ordinal)
          .map((item, ordinal) => ({ ...item, ordinal }))
        media.push({
          assetVersionId: version,
          ordinal: media.length,
          isPrimary: media.length === 0,
        })
        const element = source.element,
          revision = source.currentRevision
        saveIntent = {
          revision: element.revision,
          key: crypto.randomUUID(),
          data: {
            name: element.name,
            alias: element.alias,
            category: element.category,
            workStatus: element.workStatus,
            performerId: element.performerId,
            description: revision.description,
            label: revision.label,
            propertyValues: revision.propertyValues.map((item) => ({ ...item })),
            media,
          },
        }
      }
      uncertain.value = true
      try {
        const response = await saveElement(
          destination.id,
          saveIntent.revision,
          saveIntent.data,
          saveIntent.key,
        )
        if (!current(ticket)) return
        result.value = response.data
        saveIntent = undefined
        uncertain.value = false
      } catch (cause) {
        if (!current(ticket)) return
        if (definitive(cause)) {
          saveIntent = undefined
          uncertain.value = false
        }
        throw cause
      }
    } catch (cause) {
      if (current(ticket))
        error.value =
          (cause instanceof Error ? cause.message : '加入元素失败') +
          (uncertain.value
            ? '；结果未知，请重试原请求。'
            : asset.value
              ? '；素材已创建，重试将重新读取目标并仅追加该素材。'
              : '；未完成加入，请检查后重试。')
    } finally {
      if (current(ticket)) saving.value = false
    }
  }
  function clear() {
    epoch++
    reader?.abort()
    detail.value = undefined
    asset.value = undefined
    result.value = undefined
    ready.value = false
    saving.value = false
    loading.value = false
    uncertain.value = false
    error.value = ''
    assetIntent = undefined
    saveIntent = undefined
  }
  watch(() => auth.token, clear, { flush: 'sync' })
  watch(
    () => JSON.stringify(auth.user?.permissions || []),
    () => {
      reader?.abort()
      ready.value = false
      detail.value = undefined
      loading.value = false
    },
    { flush: 'sync' },
  )
  onDeactivated(() => {
    active.value = false
    reader?.abort()
    ready.value = false
    loading.value = false
  })
  onActivated(() => {
    if (!active.value) {
      active.value = true
      if (!saving.value) void inspect()
    }
  })
  onBeforeUnmount(() => {
    alive = false
    clear()
  })
  onBeforeRouteLeave(() => !locked.value)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || !locked.value)
  void inspect()
  return {
    destination,
    active,
    detail,
    asset,
    result,
    loading,
    saving,
    uncertain,
    ready,
    error,
    locked,
    submit,
  }
}
