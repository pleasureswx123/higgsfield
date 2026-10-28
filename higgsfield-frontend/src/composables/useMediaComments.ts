import { nextTick, computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ApiError } from '@/api/client'
import { ElMessageBox, type FormInstance } from 'element-plus'
import {
  listCommentThreads,
  createCommentThread,
  listComments,
  postComment,
  changeComment,
  type CommentTarget,
  type CommentThread,
  type MediaComment,
  type Annotation,
} from '@/api/comments'
import { useAuthStore } from '@/stores/auth'
import { validCommentVideoTime } from '@/utils/commentVideoTime'
import {
  readCommentRecovery,
  saveCommentRecovery,
  finishCommentRecovery,
  clearCommentRecovery,
} from '@/utils/commentRecovery'

export function useMediaComments(target: () => CommentTarget, mediaKind: () => string = () => '', visible: () => boolean = () => true) {
  const auth = useAuthStore()
  const hasPermission = (code: string) => {
    const values = auth.user?.permissions || []
    return values.includes('*:*:*') || values.includes(code)
  }
  const canRead = computed(() => hasPermission('comment:read'))
  const canCreate = computed(() => canRead.value && hasPermission('comment:create'))
  let active = visible(), mountedActive = true,
    alive = true
  const available = () => alive && active && Boolean(auth.token)
  const form = ref<FormInstance>(),
    threads = ref<CommentThread[]>([]),
    rows = ref<MediaComment[]>([])
  const threadId = ref(''),
    threadPage = ref(1),
    threadTotal = ref(0),
    page = ref(1),
    total = ref(0)
  const videoTime = ref('')
  const annotations = ref<Annotation[]>([]),
    annotationsChanged = ref(false)
  function updateAnnotations(value: Annotation[]) {
    if (!available() || locked.value) return
    annotations.value = JSON.parse(JSON.stringify(value))
    annotationsChanged.value = true
  }
  const body = ref(''),
    parent = ref<MediaComment>(),
    editing = ref<MediaComment>()
  const loading = ref(false),
    threadLoading = ref(false),
    threadError = ref(''),
    commentsError = ref(''),
    saving = ref(false),
    error = ref(''),
    notice = ref('')
  const uncertain = ref(false),
    locked = computed(() => saving.value || uncertain.value)
  let retryMode: 'thread' | 'save' | 'delete' = 'save',
    retryRow: MediaComment | undefined
  const retryBlocked = computed(
    () =>
      uncertain.value &&
      (!canRead.value ||
        ((retryMode === 'thread' || (retryMode === 'save' && !editing.value)) && !canCreate.value)),
  )
  let reader: AbortController | undefined,
    threadReader: AbortController | undefined,
    writer: AbortController | undefined
  let adjustingPage = false
  let epoch = 0,
    key = '',
    signature = ''
  async function loadThreads() {
    if (!available() || !canRead.value) return
    threadReader?.abort()
    const current = new AbortController()
    threadReader = current
    threads.value = []
    threadTotal.value = 0
    threadLoading.value = true
    threadError.value = ''
    try {
      const result = await listCommentThreads(target(), threadPage.value, current.signal)
      if (!current.signal.aborted) {
        threads.value = result.rows
        threadTotal.value = result.total
      }
    } catch (cause) {
      if (!current.signal.aborted)
        threadError.value = cause instanceof Error ? cause.message : '主题读取失败'
    } finally {
      if (!current.signal.aborted) threadLoading.value = false
    }
  }
  async function refresh(latest = false) {
    if (!available() || !canRead.value) return
    reader?.abort()
    rows.value = []
    loading.value = false
    commentsError.value = ''
    if (!threadId.value) {
      total.value = 0
      return
    }
    const current = new AbortController()
    reader = current
    loading.value = true
    try {
      const result = await listComments(threadId.value, page.value, current.signal)
      if (!current.signal.aborted) {
        total.value = result.total
        const lastPage = Math.max(1, Math.ceil(result.total / 30))
        const destination = latest === true ? lastPage : Math.min(page.value, lastPage)
        if (page.value !== destination) {
          adjustingPage = true
          page.value = destination
          adjustingPage = false
          await refresh()
          return
        }
        rows.value = result.rows
      }
    } catch (cause) {
      if (!current.signal.aborted)
        commentsError.value = cause instanceof Error ? cause.message : '评论读取失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  function resetEditor() {
    annotations.value = []
    annotationsChanged.value = false
    videoTime.value = ''
    body.value = ''
    parent.value = undefined
    editing.value = undefined
  }
  function reply(row: MediaComment) {
    if (!available() || !canCreate.value || locked.value) return
    resetEditor()
    parent.value = JSON.parse(JSON.stringify(row))
  }
  function edit(row: MediaComment) {
    if (!available() || locked.value) return
    resetEditor()
    editing.value = JSON.parse(JSON.stringify(row))
    body.value = row.body
    annotations.value = JSON.parse(JSON.stringify(row.annotations || []))
  }
  const editorSnapshot = () => JSON.stringify({ threadId: threadId.value, body: body.value,
    parent: parent.value, editing: editing.value, videoTime: videoTime.value,
    annotations: annotations.value, annotationsChanged: annotationsChanged.value })
  async function mutate(mode: 'thread' | 'save' | 'delete', row?: MediaComment) {
    if (!available() || !canRead.value || saving.value) return
    if ((mode === 'thread' || (mode === 'save' && !editing.value)) && !canCreate.value) return
    const existing = readCommentRecovery(auth.token, JSON.stringify(target()))
    if (existing && existing.key !== key) {
      restore()
      return
    }
    const stamp = epoch, validatedEditor = editorSnapshot()
    if (
      mode === 'save' &&
      !uncertain.value &&
      (!(await form.value?.validate().catch(() => false)) || stamp !== epoch || saving.value ||
        validatedEditor !== editorSnapshot())
    )
      return
    if (!available() || !canRead.value || stamp !== epoch) return
    if ((mode === 'thread' || (mode === 'save' && !editing.value)) && !canCreate.value) return
    const afterValidation = readCommentRecovery(auth.token, JSON.stringify(target()))
    if (afterValidation && afterValidation.key !== key) {
      restore()
      return
    }
    if (mode !== 'thread' && !threadId.value) return
    const editRow = mode === 'delete' ? row : editing.value
    if (
      mode === 'save' &&
      !editRow &&
      videoTime.value &&
      (mediaKind() !== 'video' || !validCommentVideoTime(videoTime.value))
    ) {
      error.value = '视频时间必须是非负秒数，最多六位小数。'
      return
    }
    const data =
      mode === 'thread'
        ? target()
        : editRow
          ? {
              revision: editRow.revision,
              ...(mode === 'save'
                ? {
                    body: body.value,
                    ...(annotationsChanged.value ? { annotations: annotations.value } : {}),
                  }
                : {}),
            }
          : {
              body: body.value,
              ...(parent.value ? { parentId: parent.value.id } : {}),
              ...(videoTime.value ? { videoTime: videoTime.value } : {}),
              ...(annotations.value.length ? { annotations: annotations.value } : {}),
            }
    const next = JSON.stringify({ mode, id: editRow?.id || threadId.value, data })
    if (uncertain.value && signature !== next) return
    if (signature !== next) {
      key = crypto.randomUUID()
      signature = next
    }
    const current = new AbortController()
    writer = current
    saving.value = true
    error.value = ''
    notice.value = ''
    const token = auth.token,
      targetKey = JSON.stringify(target()),
      requestKey = key
    saveCommentRecovery(token, targetKey, {
      key,
      signature,
      mode,
      row,
      threadId: threadId.value,
      body: body.value,
      videoTime: videoTime.value,
      annotations: annotations.value,
      annotationsChanged: annotationsChanged.value,
      parent: parent.value,
      editing: editing.value,
    })
    try {
      if (mode === 'thread') {
        const result = await createCommentThread(target(), key, current.signal)
        finishCommentRecovery(token, targetKey, requestKey)
        if (stamp !== epoch) return
        threadId.value = result.data.id
        await loadThreads()
      } else {
        if (editRow)
          await changeComment(
            editRow.id,
            data as { revision: string; body?: string },
            mode === 'delete',
            key,
            current.signal,
          )
        else
          await postComment(
            threadId.value,
            data as { body: string; parentId?: string },
            key,
            current.signal,
          )
        finishCommentRecovery(token, targetKey, requestKey)
        if (stamp !== epoch) return
        resetEditor()
        await nextTick()
        if (stamp !== epoch) return
        form.value?.clearValidate?.()
        notice.value = mode === 'delete' ? '评论已删除' : '评论已保存'
        await refresh(mode === 'save' && !editRow)
      }
      if (stamp === epoch) {
        signature = ''
        key = ''
        uncertain.value = false
      }
    } catch (cause) {
      const ambiguous =
        !(cause instanceof ApiError) ||
        cause.code === 0 ||
        cause.code === 408 ||
        cause.errorCode === 'IDEMPOTENCY_IN_PROGRESS' ||
        (cause.code >= 500 && cause.code < 600)
      if (!ambiguous && !uncertain.value) finishCommentRecovery(token, targetKey, requestKey)
      if (stamp === epoch) {
        uncertain.value = uncertain.value || ambiguous
        retryMode = mode
        retryRow = row
        error.value = cause instanceof Error ? cause.message : '评论操作失败'
      }
    } finally {
      if (stamp === epoch) saving.value = false
    }
  }
  function clear() {
    epoch++
    reader?.abort()
    threadReader?.abort()
    writer?.abort()
    threads.value = []
    rows.value = []
    threadId.value = ''
    page.value = 1
    threadPage.value = 1
    total.value = 0
    threadTotal.value = 0
    loading.value = false
    threadLoading.value = false
    threadError.value = ''
    commentsError.value = ''
    saving.value = false
    error.value = ''
    notice.value = ''
    key = ''
    signature = ''
    resetEditor()
    uncertain.value = false
    retryRow = undefined
  }
  function restore() {
    if (!available() || !canRead.value) return
    const saved = readCommentRecovery(auth.token, JSON.stringify(target()))
    if (!saved) return
    threadId.value = saved.threadId
    body.value = saved.body
    videoTime.value = saved.videoTime || ''
    annotations.value = saved.annotations || []
    annotationsChanged.value = saved.annotationsChanged || false
    parent.value = saved.parent
    editing.value = saved.editing
    key = saved.key
    signature = saved.signature
    retryMode = saved.mode
    retryRow = saved.row
    uncertain.value = true
    notice.value = '存在尚未确认的评论操作，请重试确认原请求。'
  }
  watch(
    threadId,
    () => {
      adjustingPage = true
      page.value = 1
      adjustingPage = false
      resetEditor()
      void refresh()
    },
    { flush: 'sync' },
  )
  watch(
    page,
    () => {
      if (!adjustingPage) void refresh()
    },
    { flush: 'sync' },
  )
  watch(threadPage, () => {
    void loadThreads()
  })
  watch(
    () => JSON.stringify(target()),
    () => {
      clear()
      restore()
      void loadThreads()
    },
    { immediate: true, flush: 'sync' },
  )
  watch(
    () => auth.token,
    () => {
      clearCommentRecovery()
      clear()
    },
    { flush: 'sync' },
  )
  watch(
    () => JSON.stringify(auth.user?.permissions || []),
    () => {
      clear()
      if (available()) {
        restore()
        void loadThreads()
      }
    },
    { flush: 'sync' },
  )
  onDeactivated(() => {
    mountedActive = false
    active = false
    clear()
  })
  function resume() {
    if (active || !mountedActive || !visible()) return
    active = true
    restore()
    void loadThreads()
    void refresh()
  }
  onActivated(() => {
    mountedActive = true
    resume()
  })
  watch(visible, value => {
    if (value) { resume(); return }
    if (!active) return
    active = false
    epoch++
    reader?.abort()
    threadReader?.abort()
    writer?.abort()
    if (saving.value) uncertain.value = true
    saving.value = false
    loading.value = false
    threadLoading.value = false
  }, { flush: 'sync' })
  onBeforeUnmount(() => {
    alive = false
    active = false
    window.removeEventListener('beforeunload', beforeUnload)
    clear()
  })
  const dirty = computed(
    () =>
      body.value !== (editing.value?.body || '') || !!videoTime.value || annotationsChanged.value,
  )
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (available() && canRead.value && !retryBlocked.value && (dirty.value || locked.value)) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  window.addEventListener('beforeunload', beforeUnload)
  async function confirmLeave() {
    // 失效会话或撤权时允许退出；未知写入仍保留在账号隔离的内存恢复记录中。
    if (!available() || !canRead.value || retryBlocked.value) return true
    if (locked.value) return false
    if (!dirty.value) return true
    const stamp = epoch, before = editorSnapshot()
    const confirmed = await ElMessageBox.confirm(
      '评论有未发送修改，离开会丢弃这些修改。',
      '未发送评论',
      {
        type: 'warning',
        confirmButtonText: '丢弃并离开',
        cancelButtonText: '继续编辑',
      },
    )
      .then(() => true)
      .catch(() => false)
    return confirmed && stamp === epoch && before === editorSnapshot() && !locked.value
  }
  /** 等待离开确认期间，媒体、主题或身份变化不得继续执行旧界面动作。 */
  async function runConfirmed(action: () => void | Promise<void>) {
    const stamp = epoch, thread = threadId.value
    if (!(await confirmLeave()) || stamp !== epoch || thread !== threadId.value || !available()) return
    await action()
  }
  onBeforeRouteLeave(confirmLeave)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || confirmLeave())
  return {
    canRead,
    canCreate,
    retryBlocked,
    form,
    dirty,
    confirmLeave,
    runConfirmed,
    threads,
    rows,
    threadId,
    threadPage,
    threadTotal,
    page,
    total,
    body,
    videoTime,
    annotations,
    updateAnnotations,
    parent,
    editing,
    loading,
    threadLoading,
    threadError,
    commentsError,
    saving,
    locked,
    uncertain,
    retry: () => mutate(retryMode, retryRow),
    error,
    notice,
    loadThreads,
    refresh,
    resetEditor,
    reply,
    edit,
    mutate,
  }
}
