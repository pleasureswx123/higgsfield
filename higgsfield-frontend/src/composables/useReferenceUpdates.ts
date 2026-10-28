import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch, type Ref } from 'vue'
import type { DraftReference, ModelCapability } from '@/api/creation'
import { checkReferenceUpdates, type ReferenceUpdate } from '@/api/references'
import { useAuthStore } from '@/stores/auth'
import { upgradeReferenceGroup } from '@/utils/draftReferences'

export function useReferenceUpdates(projectId: () => string, references: Ref<DraftReference[]>,
  disabled: () => boolean, model: () => ModelCapability | null | undefined) {
  const auth = useAuthStore(), items = ref<ReferenceUpdate[]>([]), loading = ref(false), error = ref('')
  let active = true, epoch = 0, request: AbortController | undefined
  const identities = computed(() => [...new Set(references.value.map(item => item.elementRevisionId).filter((id): id is string => !!id))].sort())
  const updates = computed(() => Object.fromEntries(items.value.map(item => [item.elementRevisionId, item])))
  async function check() {
    const ticket = ++epoch
    request?.abort()
    items.value = []; error.value = ''; loading.value = false
    if (!active || !auth.token || disabled() || !identities.value.length) return
    request = new AbortController(); loading.value = true
    try {
      const result = await checkReferenceUpdates(projectId(), identities.value, request.signal)
      if (ticket === epoch) items.value = result.data.items
    } catch (cause) {
      if (ticket === epoch) error.value = cause instanceof Error ? cause.message : '修订检查失败，旧引用保持不变'
    } finally { if (ticket === epoch) loading.value = false }
  }
  async function upgrade(key: string, confirm: (message: string) => Promise<boolean>) {
    if (!active || disabled() || !auth.token) return
    const old = references.value.find(item => item.referenceKey === key)?.elementRevisionId
    const candidate = old ? updates.value[old]?.candidate : undefined
    if (!old || !candidate || candidate.projectId !== projectId()) return
    const before = JSON.stringify(references.value), ticket = epoch
    const accepted = await confirm(`将引用 #${key} 从元素修订 ${old} 升级为 ${candidate.elementRevisionId}。参考图将使用新修订全部 ${candidate.assetVersionIds.length} 张图片，首帧使用新主图；原选择会被替换。提示词引用编号不变，尚未保存草稿。是否继续？`)
    if (!accepted || ticket !== epoch || !active || disabled() || !auth.token) return
    if (before !== JSON.stringify(references.value)) { error.value = '确认期间草稿引用已变化，请重新检查后升级'; return }
    try { references.value = upgradeReferenceGroup(references.value, key, old, candidate, model()); error.value = '' }
    catch (cause) { error.value = cause instanceof Error ? cause.message : '升级失败，原引用已保留' }
  }
  watch(() => [projectId(), identities.value.join(','), disabled(), auth.token, auth.user?.user.userId,
    JSON.stringify(auth.user?.permissions ?? [])], check, { immediate: true, flush: 'sync' })
  function stop() { active = false; epoch++; request?.abort(); items.value = []; loading.value = false; error.value = '' }
  onDeactivated(stop)
  onActivated(() => { if (!active) { active = true; void check() } })
  onBeforeUnmount(stop)
  return { updates, loading, error, check, upgrade }
}
