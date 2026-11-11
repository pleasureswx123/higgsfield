import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  readProduction,
  executeProduction,
  assignProduction,
  type ProductionAction,
  type ProductionCommand,
  type ProductionKind,
  type ProductionState,
} from '@/api/production'
import { readMembers, readRoles, type Member } from '@/api/projectWorkspace'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
// 当前应用会话内保留意见，关闭弹层或切换页签后可恢复；按账号、登录会话、对象和版本隔离。
const reasonDrafts = new Map<string, string>()
export function useProduction(
  target: () => { kind: ProductionKind; id: string; projectId: string; versionId: string },
  disabled: () => boolean,
  changed: (state: ProductionState) => void,
) {
  const state = ref<ProductionState>(),
    loading = ref(false),
    pending = ref(false),
    error = ref(''),
    reason = ref(''),
    members = ref<Member[]>([]),
    performer = ref<string | null>(null)
  const auth = useAuthStore()
  let activeDraftKey = ''
  watch(
    () =>
      JSON.stringify([
        auth.token,
        auth.user?.user.userId,
        target().projectId,
        target().kind,
        target().id,
        target().versionId,
      ]),
    (key) => {
      activeDraftKey = key
      reason.value = reasonDrafts.get(key) || ''
    },
    { immediate: true, flush: 'sync' },
  )
  watch(
    reason,
    (value) => {
      if (value) reasonDrafts.set(activeDraftKey, value)
      else reasonDrafts.delete(activeDraftKey)
    },
    { flush: 'sync' },
  )
  function clearDraft() {
    if (pending.value || intent.value) return
    reason.value = ''
    reasonDrafts.delete(activeDraftKey)
  }
  let epoch = 0,
    controller: AbortController | undefined
  const intent = ref<{
    key: string
    command?: ProductionCommand
    assignment?: { revision: string; performerId: string | null }
  }>()
  const oldVersion = computed(() => !!state.value && target().versionId !== state.value.versionId)
  const blocked = computed(
    () => disabled() || loading.value || pending.value || oldVersion.value || !state.value,
  )
  async function load() {
    if (pending.value || intent.value) return
    controller?.abort()
    controller = new AbortController()
    const signal = controller.signal,
      ticket = ++epoch,
      current = target()
    loading.value = true
    error.value = ''
    try {
      const result = await readProduction(current.kind, current.id, signal)
      if (ticket !== epoch || signal.aborted) return
      state.value = result.data
      performer.value = result.data.performerId
      if (result.data.canAssign) {
        const roles = await readRoles(current.projectId, signal)
        const eligible = new Set(
          roles.data.items.filter((role) => role.code !== 'viewer').map((role) => role.id),
        )
        const all: Member[] = []
        for (let page = 1; ; page++) {
          const result = await readMembers(current.projectId, page, 'active', signal)
          if (ticket !== epoch || signal.aborted) return
          all.push(...result.rows)
          if (!result.rows.length || all.length >= result.total) break
        }
        members.value = all.filter((member) => eligible.has(member.roleId))
      }
    } catch (cause) {
      if (ticket === epoch && !signal.aborted)
        error.value = cause instanceof Error ? cause.message : '读取制作信息失败'
    } finally {
      if (ticket === epoch) loading.value = false
    }
  }
  async function run(action?: ProductionAction, assign = false) {
    if (blocked.value || !state.value) return
    if (!intent.value) {
      if (assign ? !state.value.canAssign : !action || !state.value.allowedActions.includes(action))
        return
      if (action === 'request_changes' && !reason.value.trim()) {
        error.value = '请填写具体修改意见'
        return
      }
      intent.value = {
        key: crypto.randomUUID(),
        ...(assign
          ? { assignment: { revision: state.value.revision, performerId: performer.value } }
          : {
              command: {
                revision: state.value.revision,
                versionId: target().versionId,
                action: action!,
                ...(action === 'request_changes' ? { reason: reason.value.trim() } : {}),
              },
            }),
      }
    }
    const request = intent.value,
      requestDraftKey = activeDraftKey,
      ticket = epoch,
      current = target()
    pending.value = true
    error.value = ''
    try {
      const result = request.assignment
        ? await assignProduction(current.kind, current.id, request.assignment, request.key)
        : await executeProduction(current.kind, current.id, request.command!, request.key)
      if (ticket !== epoch) return
      state.value = result.data
      performer.value = result.data.performerId
      intent.value = undefined
      if (request.command) {
        reasonDrafts.delete(requestDraftKey)
        if (activeDraftKey === requestDraftKey) reason.value = ''
      }
      changed(result.data)
    } catch (cause) {
      if (ticket !== epoch) return
      error.value = cause instanceof Error ? cause.message : '操作失败，请重试'
      // 明确拒绝允许修正后提交；网络未知结果保留原请求和幂等键。
      if (
        cause instanceof ApiError &&
        cause.code !== 408 &&
        cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
        (cause.code === 601 || (cause.code >= 400 && cause.code < 500))
      )
        intent.value = undefined
    } finally {
      if (ticket === epoch) pending.value = false
    }
  }
  watch(
    () => [target().kind, target().id, target().projectId, auth.token, auth.user?.user.userId],
    () => {
      epoch++
      controller?.abort()
      state.value = undefined
      intent.value = undefined
      pending.value = false
      members.value = []
      void load()
    },
    { immediate: true, flush: 'sync' },
  )
  const canLeave = () => !pending.value && !intent.value
  onBeforeRouteLeave(canLeave)
  onBeforeRouteUpdate(canLeave)
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (!canLeave()) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  window.addEventListener('beforeunload', beforeUnload)
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', beforeUnload)
    epoch++
    controller?.abort()
  })
  return {
    state,
    loading,
    pending,
    error,
    reason,
    clearDraft,
    members,
    performer,
    intent,
    oldVersion,
    blocked,
    load,
    run,
  }
}
