import { ref, computed, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { getProjectViewPreference, saveProjectViewPreference, type ProjectViewSettings } from '@/api/viewPreferences'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'

export function useProjectViewPreference(current: () => ProjectViewSettings, apply: (value: ProjectViewSettings) => void) {
  return useViewPreference(current, apply, getProjectViewPreference, saveProjectViewPreference)
}

export function useViewPreference<T extends object>(current: () => T, apply: (value: T) => void,
  read: (signal?: AbortSignal) => Promise<{ data: { revision: string; settings: T } }>,
  write: (settings: T, revision: string, key: string, signal?: AbortSignal) => Promise<{ data: { revision: string } }>) {
  const auth = useAuthStore(), revision = ref('0'), ready = ref(false), loading = ref(false), saving = ref(false)
  const error = ref(''), notice = ref(''), uncertain = ref(false)
  const locked = computed(() => saving.value || uncertain.value)
  let epoch = 0, active = true, reader: AbortController | undefined, writer: AbortController | undefined
  let intent: { settings: T; revision: string; key: string } | undefined
  let stored: T | undefined
  async function load(restore = false) {
    if (!active || !auth.token || locked.value) return
    reader?.abort(); reader = new AbortController()
    const signal = reader.signal, ticket = ++epoch
    const before = JSON.stringify(current())
    loading.value = true; error.value = ''; notice.value = ''; ready.value = false
    try {
      const response = await read(signal)
      if (ticket !== epoch || signal.aborted) return
      revision.value = response.data.revision; ready.value = true
      stored = response.data.settings
      if (restore) {
        if (revision.value === '0') notice.value = '尚未保存视图，当前筛选保持不变。'
        else if (JSON.stringify(current()) !== before) notice.value = '读取期间筛选已变化，未覆盖当前视图，请再次恢复。'
        else { apply(response.data.settings); notice.value = '已恢复保存的视图。' }
      }
    } catch (cause) {
      if (ticket === epoch && !signal.aborted) error.value = cause instanceof Error ? cause.message : '视图读取失败'
    } finally { if (ticket === epoch) loading.value = false }
  }
  async function save() {
    if (!active || !auth.token || !ready.value || loading.value || saving.value) return
    // 设置仅允许 JSON 值；序列化同时解除 Vue 嵌套代理，固定重试快照。
    if (!intent) intent = { settings: JSON.parse(JSON.stringify({ ...stored, ...current() })), revision: revision.value, key: crypto.randomUUID() }
    const value = intent, ticket = epoch
    saving.value = true; uncertain.value = true; error.value = ''; notice.value = ''; writer = new AbortController()
    try {
      const response = await write(value.settings, value.revision, value.key, writer.signal)
      if (ticket !== epoch || !active) return
      revision.value = response.data.revision; stored = value.settings; intent = undefined; uncertain.value = false
      notice.value = '视图已保存；后续筛选变化需再次保存。'
    } catch (cause) {
      if (ticket !== epoch || !active) return
      if (cause instanceof ApiError && ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))) {
        intent = undefined; uncertain.value = false; ready.value = false
      }
      error.value = cause instanceof Error ? cause.message : '保存结果未确认，请重试同一请求'
    } finally { if (ticket === epoch) saving.value = false }
  }
  function clear() {
    epoch++; reader?.abort(); writer?.abort(); intent = undefined
    stored = undefined
    revision.value = '0'; ready.value = false; loading.value = false; saving.value = false
    uncertain.value = false; error.value = ''; notice.value = ''
  }
  watch(() => [auth.token, auth.user?.permissions.join('|')], () => { clear(); if (active && auth.token) void load() }, { flush: 'sync' })
  onMounted(() => load())
  onDeactivated(() => { active = false; epoch++; reader?.abort(); writer?.abort(); saving.value = false; loading.value = false })
  onActivated(() => { if (!active) { active = true; if (!uncertain.value) void load() } })
  onBeforeRouteLeave(() => !locked.value)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || !locked.value)
  onBeforeUnmount(clear)
  return { ready, loading, saving, uncertain, locked, error, notice, load, save }
}
