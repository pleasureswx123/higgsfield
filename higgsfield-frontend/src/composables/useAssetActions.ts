import { computed, onActivated, onDeactivated, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox, type FormInstance } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
import {
  listAssetTrash,
  recycleAsset,
  renameAsset,
  type Asset,
  type RecycledAsset,
} from '@/api/assets'

export function useAssetActions(projectId: string, changed: () => void, visible: () => boolean = () => true) {
  const auth = useAuthStore()
  let epoch = 0,
    interaction = 0,
    alive = true,
    correctingPage = false,
    refreshOnActivation = false
  let mountedActive = true
  const active = ref(visible())
  const current = (ticket: number) => alive && ticket === epoch && Boolean(auth.token)
  const editing = ref<Asset | null>(null),
    form = ref<FormInstance>(),
    draft = reactive({ name: '' })
  const pending = ref(false),
    error = ref(''),
    trashOpen = ref(false),
    trashLoading = ref(false)
  const recycled = ref<RecycledAsset[]>([]),
    total = ref(0),
    page = ref(1)
  const keys = new Map<string, string>()
  const renameUncertain = ref(false)
  const renameLocked = computed(() => pending.value || renameUncertain.value)
  const lifecycleUncertain = ref(false),
    lifecycleLabel = ref('')
  const actionsLocked = computed(() => renameLocked.value || lifecycleUncertain.value)
  let lifecycleIntent: { id: string; revision: string; restore: boolean; key: string } | undefined
  let renameIntent: { asset: Asset; name: string; key: string } | undefined
  let controller: AbortController | undefined
  function requestKey(identity: string) {
    const key = keys.get(identity) || crypto.randomUUID()
    keys.set(identity, key)
    return key
  }
  function edit(asset: Asset) {
    if (!active.value || !alive || !auth.token || actionsLocked.value) return
    interaction++
    editing.value = { ...asset }
    draft.name = asset.name
    error.value = ''
  }
  async function save() {
    const ticket = epoch,
      viewTicket = interaction
    const before = JSON.stringify([editing.value, draft.name])
    if (
      !active.value ||
      !current(ticket) ||
      pending.value ||
      lifecycleUncertain.value ||
      !editing.value
    )
      return
    if (!renameIntent && !(await form.value?.validate().catch(() => false))) return
    if (
      !active.value ||
      viewTicket !== interaction ||
      !current(ticket) ||
      pending.value ||
      !editing.value ||
      before !== JSON.stringify([editing.value, draft.name])
    )
      return
    pending.value = true
    error.value = ''
    const asset = editing.value,
      name = draft.name.trim()
    renameIntent ??= {
      asset: { ...asset },
      name,
      key: requestKey(`rename:${asset.id}:${asset.revision}:${name}`),
    }
    const request = renameIntent
    renameUncertain.value = true
    try {
      await renameAsset(request.asset, request.name, request.key)
      if (!current(ticket)) return
      renameIntent = undefined
      renameUncertain.value = false
      editing.value = null
      notifyChanged()
    } catch (cause) {
      if (current(ticket)) {
        if (
          cause instanceof ApiError &&
          cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
          (cause.code === 601 || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
        ) {
          renameIntent = undefined
          renameUncertain.value = false
        }
        error.value = cause instanceof Error ? cause.message : '保存失败'
      }
    } finally {
      if (current(ticket)) pending.value = false
    }
  }
  async function refreshTrash() {
    if (!active.value || !alive || !auth.token || !trashOpen.value) return
    controller?.abort()
    const current = new AbortController()
    controller = current
    trashLoading.value = true
    error.value = ''
    recycled.value = []
    const requestedPage = page.value
    try {
      const result = await listAssetTrash(projectId, requestedPage, current.signal)
      if (!current.signal.aborted) {
        const lastPage = Math.max(1, Math.ceil(result.total / 30))
        if (requestedPage > lastPage) {
          correctingPage = true
          page.value = lastPage
          correctingPage = false
          total.value = result.total
          if (result.total > 0) await refreshTrash()
          return
        }
        recycled.value = result.rows
        total.value = result.total
      }
    } catch (cause) {
      if (!current.signal.aborted) {
        total.value = 0
        error.value = cause instanceof Error ? cause.message : '回收站加载失败'
      }
    } finally {
      if (!current.signal.aborted) trashLoading.value = false
    }
  }
  function notifyChanged() {
    if (active.value) changed()
    else refreshOnActivation = true
  }
  async function lifecycle(item: Asset | RecycledAsset, restore: boolean) {
    const ticket = epoch,
      viewTicket = interaction,
      snapshot = { ...item }
    if (
      !active.value ||
      !current(ticket) ||
      actionsLocked.value ||
      (restore && 'canRestore' in snapshot && !snapshot.canRestore)
    )
      return
    // 确认框同样属于进行中的操作，避免重复确认和切换路由后提交。
    pending.value = true
    try {
      try {
        await ElMessageBox.confirm(
          restore
            ? `恢复“${snapshot.name}”到原目录。`
            : `将“${snapshot.name}”移入回收站。该素材将停止预览和新引用，历史版本及文件保留，可在30天内恢复。`,
          restore ? '恢复素材' : '删除素材',
          { confirmButtonText: restore ? '恢复' : '删除', cancelButtonText: '取消' },
        )
      } catch {
        return
      }
      if (!active.value || viewTicket !== interaction || !current(ticket)) return
      error.value = ''
      const id = 'targetId' in snapshot ? snapshot.targetId : snapshot.id
      lifecycleIntent = {
        id,
        revision: snapshot.revision,
        restore,
        key: requestKey(`${restore}:${id}:${snapshot.revision}`),
      }
      lifecycleLabel.value = `${restore ? '恢复' : '删除'}“${snapshot.name}”`
      await executeLifecycle(ticket)
    } catch (cause) {
      if (current(ticket)) error.value = cause instanceof Error ? cause.message : '操作失败'
    } finally {
      if (current(ticket)) pending.value = false
    }
  }
  async function executeLifecycle(ticket: number) {
    const request = lifecycleIntent
    if (!request) return
    lifecycleUncertain.value = true
    try {
      await recycleAsset(request.id, request.revision, request.restore, request.key)
      if (!current(ticket)) return
      lifecycleIntent = undefined
      lifecycleUncertain.value = false
      lifecycleLabel.value = ''
      notifyChanged()
      if (active.value && trashOpen.value) await refreshTrash()
    } catch (cause) {
      if (!current(ticket)) return
      if (
        cause instanceof ApiError &&
        cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
        (cause.code === 601 || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
      ) {
        lifecycleIntent = undefined
        lifecycleUncertain.value = false
        lifecycleLabel.value = ''
      }
      error.value = cause instanceof Error ? cause.message : '操作失败'
    }
  }
  async function retryLifecycle() {
    const ticket = epoch
    if (!active.value || !current(ticket) || pending.value || !lifecycleIntent) return
    pending.value = true
    error.value = ''
    try {
      await executeLifecycle(ticket)
    } finally {
      if (current(ticket)) pending.value = false
    }
  }
  watch(
    [trashOpen, page],
    () => {
      if (correctingPage) return
      if (trashOpen.value) void refreshTrash()
      else {
        controller?.abort()
        trashLoading.value = false
      }
    },
    { flush: 'sync' },
  )
  function clear() {
    lifecycleIntent = undefined
    lifecycleUncertain.value = false
    lifecycleLabel.value = ''
    renameIntent = undefined
    renameUncertain.value = false
    epoch++
    interaction++
    refreshOnActivation = false
    controller?.abort()
    keys.clear()
    editing.value = null
    draft.name = ''
    trashOpen.value = false
    recycled.value = []
    total.value = 0
    page.value = 1
    pending.value = false
    trashLoading.value = false
    error.value = ''
  }
  watch(() => auth.token, clear, { flush: 'sync' })
  watch(
    () => JSON.stringify(auth.user?.permissions || []),
    () => {
      const wasOpen = trashOpen.value
      clear()
      // 丢弃旧授权下的编辑对象；回收站重新通过服务端鉴权读取。
      if (wasOpen && auth.token) trashOpen.value = true
    },
    { flush: 'sync' },
  )
  function suspend() {
    if (!active.value) return
    active.value = false
    interaction++
    controller?.abort()
    recycled.value = []
    total.value = 0
    trashLoading.value = false
  }
  function resume() {
    if (active.value || !mountedActive || !visible()) return
    active.value = true
    if (refreshOnActivation) {
      refreshOnActivation = false
      changed()
    }
    if (trashOpen.value) void refreshTrash()
  }
  onDeactivated(() => {
    mountedActive = false
    suspend()
  })
  onActivated(() => {
    mountedActive = true
    resume()
  })
  watch(visible, value => value ? resume() : suspend(), { flush: 'sync' })
  onBeforeUnmount(() => {
    alive = false
    clear()
  })
  async function confirmLeave() {
    if (actionsLocked.value) return false
    const ticket = epoch,
      view = interaction
    if (editing.value && draft.name !== editing.value.name) {
      try {
        await ElMessageBox.confirm('名称尚未保存，是否离开？', '未保存修改', {
          confirmButtonText: '离开',
          cancelButtonText: '继续编辑',
        })
      } catch {
        return false
      }
    }
    return ticket === epoch && view === interaction && !actionsLocked.value
  }
  async function cancelEdit() {
    if (!(await confirmLeave())) return
    interaction++
    editing.value = null
    draft.name = ''
  }
  onBeforeRouteLeave(confirmLeave)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || confirmLeave())
  return {
    active,
    editing,
    form,
    draft,
    pending,
    renameLocked,
    actionsLocked,
    lifecycleUncertain,
    lifecycleLabel,
    retryLifecycle,
    renameUncertain,
    cancelEdit,
    error,
    trashOpen,
    trashLoading,
    recycled,
    total,
    page,
    edit,
    save,
    lifecycle,
    refreshTrash,
  }
}
