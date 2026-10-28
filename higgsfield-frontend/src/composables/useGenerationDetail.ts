import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  getGeneration,
  getGenerationInput,
  getOutputMedia,
  subscribeGeneration,
  type GenerationSnapshot,
  type GenerationInput,
  type GenerationOutput,
} from '@/api/generations'

export function useGenerationDetail(identity: () => string | undefined) {
  const auth = useAuthStore()
  let active = true
  const detail = ref<GenerationSnapshot>(),
    input = ref<GenerationInput>()
  const loading = ref(false),
    inputLoading = ref(false),
    mediaLoading = ref(false)
  const error = ref(''),
    inputError = ref(''),
    mediaError = ref('')
  const mediaUrl = ref(''),
    mediaKind = ref('')
  const liveState = ref<'connecting' | 'live' | 'reconnecting' | 'stopped'>('stopped')
  let subscription: AbortController | undefined
  let retryTimer: ReturnType<typeof setTimeout> | undefined
  let detailRequest: AbortController | undefined,
    inputRequest: AbortController | undefined,
    mediaRequest: AbortController | undefined
  let selectedMedia: { id: string; revision: string; download: boolean } | undefined
  const message = (cause: unknown) => (cause instanceof Error ? cause.message : '读取失败，请重试')
  function clearMedia() {
    mediaRequest?.abort()
    selectedMedia = undefined
    if (mediaUrl.value) URL.revokeObjectURL(mediaUrl.value)
    mediaUrl.value = ''
    mediaKind.value = ''
    mediaLoading.value = false
    mediaError.value = ''
  }
  function clear() {
    subscription?.abort()
    if (retryTimer) clearTimeout(retryTimer)
    liveState.value = 'stopped'
    detailRequest?.abort()
    inputRequest?.abort()
    clearMedia()
    detail.value = undefined
    input.value = undefined
    loading.value = false
    inputLoading.value = false
    error.value = ''
    inputError.value = ''
  }
  function subscribe(id: string, initialCursor: string) {
    subscription?.abort()
    const current = new AbortController()
    subscription = current
    let cursor: string | undefined = initialCursor,
      attempts = 0
    function isCurrentSnapshot(snapshot: GenerationSnapshot) {
      if (snapshot.id !== id) throw new Error('事件任务身份不匹配')
      if (!/^[1-9][0-9]*$/.test(snapshot.revision) ||
        !/^[1-9][0-9]*:(0|[1-9][0-9]*)$/.test(snapshot.eventCursor) ||
        snapshot.eventCursor.split(':')[0] !== id) throw new Error('任务快照版本或游标无效')
      // 同版本也可能携带权限变化；仅拒绝修订或事件游标向后移动。
      if (detail.value && BigInt(snapshot.revision) < BigInt(detail.value.revision)) return false
      return !cursor || BigInt(snapshot.eventCursor.split(':')[1]!) >= BigInt(cursor.split(':')[1]!)
    }
    async function connect() {
      if (current.signal.aborted) return
      liveState.value = attempts ? 'reconnecting' : 'connecting'
      try {
        await subscribeGeneration(
          id,
          cursor,
          current.signal,
          async (event) => {
            if (current.signal.aborted) return
            liveState.value = 'live'
            attempts = 0
            if (event.event === 'access.revoked') {
              clear()
              error.value = '访问权限已变化，请关闭详情并重新加载列表。'
              return
            }
            const payload = JSON.parse(event.data)
            if (event.event === 'task.snapshot' || event.event === 'stream.reset') {
              const snapshot = event.event === 'stream.reset' ? payload.snapshot : payload
              if (!isCurrentSnapshot(snapshot)) return
              inputRequest?.abort()
              input.value = undefined
              inputLoading.value = false
              inputError.value = ''
              clearMedia()
              detail.value = snapshot
              cursor = snapshot.eventCursor
            } else {
              if (
                !event.id ||
                !/^[1-9][0-9]*:(0|[1-9][0-9]*)$/.test(event.id) ||
                event.id.split(':')[0] !== id
              )
                throw new Error('事件游标无效')
              if (cursor && BigInt(event.id.split(':')[1]!) <= BigInt(cursor.split(':')[1]!)) return
              // 从已授权快照刷新所有状态，不用局部事件推断费用或归档完成。
              const response = await getGeneration(id, current.signal)
              if (current.signal.aborted) return
              if (!isCurrentSnapshot(response.data)) return
              if (response.data.outputsVisibility === 'hidden') {
                inputRequest?.abort()
                input.value = undefined
                inputLoading.value = false
                inputError.value = ''
                clearMedia()
              }
              if (!detail.value || BigInt(response.data.revision) >= BigInt(detail.value.revision)) {
                // 普通事件也可能移除输出或撤销媒体访问，不能保留旧的本地预览。
                if (selectedMedia) {
                  const output = response.data.outputs.find((row) => row.id === selectedMedia?.id)
                  if (
                    !output?.previewUrl ||
                    output.revision !== selectedMedia.revision ||
                    (selectedMedia.download && !output.downloadUrl)
                  ) clearMedia()
                }
                detail.value = response.data
              }
              cursor = response.data.eventCursor
            }
          },
          () => {
            if (!current.signal.aborted) liveState.value = 'live'
          },
        )
      } catch (cause) {
        if (current.signal.aborted) return
        const code = (cause as { code?: number }).code
        if (code === 401 || code === 403 || code === 601) {
          clear()
          error.value = message(cause)
          return
        }
      }
      if (!current.signal.aborted) {
        liveState.value = 'reconnecting'
        const delay = Math.min(30000, 3000 * 2 ** Math.min(attempts++, 4))
        retryTimer = setTimeout(() => {
          void connect()
        }, delay)
      }
    }
    void connect()
  }
  async function refresh() {
    clear()
    const id = identity()
    if (!id || !active || !auth.token) return
    const current = new AbortController()
    detailRequest = current
    loading.value = true
    try {
      const response = await getGeneration(id, current.signal)
      if (!current.signal.aborted) {
        detail.value = response.data
        subscribe(id, response.data.eventCursor)
      }
    } catch (cause) {
      if (!current.signal.aborted) error.value = message(cause)
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  async function readInput() {
    const id = identity()
    if (!id || !active || !auth.token || !detail.value || detail.value.kind === 'chat') return
    inputRequest?.abort()
    const current = new AbortController()
    inputRequest = current
    inputLoading.value = true
    inputError.value = ''
    input.value = undefined
    try {
      const response = await getGenerationInput(id, current.signal)
      if (!current.signal.aborted) input.value = response.data
    } catch (cause) {
      if (!current.signal.aborted) inputError.value = message(cause)
    } finally {
      if (!current.signal.aborted) inputLoading.value = false
    }
  }
  async function media(output: GenerationOutput, download = false) {
    const latest = detail.value?.outputs.find((row) => row.id === output.id)
    if (
      !active || !auth.token ||
      !latest?.previewUrl ||
      (download && !latest.downloadUrl)
    )
      return
    clearMedia()
    selectedMedia = { id: latest.id, revision: latest.revision, download }
    const current = new AbortController()
    mediaRequest = current
    mediaLoading.value = true
    try {
      const blob = await getOutputMedia(latest.id, download, current.signal)
      if (current.signal.aborted) return
      mediaUrl.value = URL.createObjectURL(blob)
      mediaKind.value = latest.kind
      if (download) {
        const link = document.createElement('a')
        link.href = mediaUrl.value
        link.download = `output-${latest.id}`
        link.click()
      }
    } catch (cause) {
      if (!current.signal.aborted) mediaError.value = message(cause)
    } finally {
      if (!current.signal.aborted) mediaLoading.value = false
    }
  }
  watch(
    () => [identity(), auth.token, JSON.stringify(auth.user?.permissions || [])],
    () => {
      void refresh()
    },
    { immediate: true, flush: 'sync' },
  )
  onDeactivated(() => { active = false; clear() })
  onActivated(() => { if (!active) { active = true; void refresh() } })
  onBeforeUnmount(() => { active = false; clear() })
  return {
    liveState,
    detail,
    input,
    loading,
    inputLoading,
    mediaLoading,
    error,
    inputError,
    mediaError,
    mediaUrl,
    mediaKind,
    refresh,
    readInput,
    media,
    clearMedia,
  }
}
