import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { readProjectPermissions, saveProjectPermissions, type PermissionMatrix, type PermissionScope } from '@/api/projectPermissions'

export function useProjectPermissions(id: string, changed: () => void) {
  const matrix = ref<PermissionMatrix>(), draft = ref<Record<string, Record<string, PermissionScope>>>({})
  const loading = ref(false), saving = ref(false), error = ref(''), notice = ref('')
  const baseline = ref(''), dirty = computed(() => JSON.stringify(draft.value) !== baseline.value && !!matrix.value)
  const groups = computed(() => [...new Set(matrix.value?.rows.map(row => row.group) ?? [])])
  let controller: AbortController | undefined, alive = true, epoch = 0, key = '', previousPayload = ''
  function apply(data: PermissionMatrix) {
    matrix.value = data
    draft.value = Object.fromEntries(data.roles.map(role => [role.code, Object.fromEntries(data.rows.map(row => [row.code, role.permissions[row.code] ?? 'none']))]))
    baseline.value = JSON.stringify(draft.value)
  }
  async function load() {
    if (saving.value) return
    if (dirty.value) {
      try { await ElMessageBox.confirm('重新加载会丢弃未保存的权限修改。是否继续？', '重新加载', { confirmButtonText: '重新加载', cancelButtonText: '取消' }) } catch { return }
    }
    controller?.abort(); const current = new AbortController(); controller = current
    loading.value = true; error.value = ''
    try {
      const result = await readProjectPermissions(id, current.signal)
      if (alive && !current.signal.aborted) apply(result.data)
    } catch (cause) { if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '加载失败' }
    finally { if (!current.signal.aborted) loading.value = false }
  }
  function reset() {
    if (!matrix.value?.canEdit || saving.value) return
    for (const role of matrix.value.roles) {
      if (role.code === 'owner') continue
      for (const row of matrix.value.rows.filter(row => row.editable)) draft.value[role.code]![row.code] = role.defaults[row.code] ?? 'none'
    }
    notice.value = '已恢复默认值，点击保存后生效。'
  }
  async function save() {
    if (!matrix.value?.canEdit || saving.value || !dirty.value) return
    const overrides = Object.fromEntries(matrix.value.roles.filter(role => role.code !== 'owner').map(role => [role.code, Object.fromEntries(matrix.value!.rows.filter(row => row.editable).map(row => [row.code, draft.value[role.code]?.[row.code] ?? 'none']))]))
    const payload = { revision: matrix.value.revision, overrides }
    const serialized = JSON.stringify(payload)
    if (serialized !== previousPayload) { key = crypto.randomUUID(); previousPayload = serialized }
    const stamp = epoch; saving.value = true; error.value = ''; notice.value = ''
    try {
      const result = await saveProjectPermissions(id, payload, key)
      if (!alive || stamp !== epoch) return
      apply(result.data); previousPayload = ''; notice.value = '权限已保存，仅对当前项目生效。'; changed()
    } catch (cause) { if (alive && stamp === epoch) error.value = cause instanceof Error ? cause.message : '保存失败' }
    finally { if (stamp === epoch) saving.value = false }
  }
  watch(() => useAuthStore().token, () => { epoch++; controller?.abort(); matrix.value = undefined; draft.value = {}; error.value = ''; saving.value = false }, { flush: 'sync' })
  async function leave() {
    if (saving.value) return false
    if (!dirty.value) return true
    try { await ElMessageBox.confirm('角色权限尚未保存，是否离开？', '未保存的修改', { confirmButtonText: '离开', cancelButtonText: '继续编辑' }); return true } catch { return false }
  }
  onBeforeRouteLeave(leave)
  const unload = (event: BeforeUnloadEvent) => { if (dirty.value || saving.value) { event.preventDefault(); event.returnValue = '' } }
  window.addEventListener('beforeunload', unload)
  onBeforeUnmount(() => { alive = false; controller?.abort(); window.removeEventListener('beforeunload', unload) })
  void load()
  return { matrix, draft, groups, dirty, loading, saving, error, notice, load, reset, save }
}
