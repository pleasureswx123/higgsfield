import { ref, reactive, computed, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { getProjectCollections, createProjectCollection, updateProjectCollection, deleteProjectCollection, type ProjectCollection } from '@/api/projectPreferences'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

export function useProjectCollections(changed: (deletedId?: string) => void) {
  const auth = useAuthStore(), rows = ref<ProjectCollection[]>([]), open = ref(false), editing = ref(false)
  const loading = ref(false), saving = ref(false), uncertain = ref(false), error = ref(''), form = ref<FormInstance>()
  const target = ref<ProjectCollection | null>(null)
  const readError = ref('')
  const conflict = ref(false)
  const fields = reactive({ name: '', description: '', color: '', orderNum: 0 })
  const rules: FormRules = {
    name: [{ required: true, whitespace: true, max: 200, message: '请输入 1–200 字符的集合名称', trigger: 'blur' }],
    description: [{ max: 2000, message: '说明最多 2000 字符', trigger: 'blur' }],
    color: [{ pattern: /^(#[0-9a-f]{6})?$/, message: '请输入小写 #rrggbb，或留空', trigger: 'blur' }],
    orderNum: [{ type: 'integer', required: true, min: -2147483648, max: 2147483647, message: '请输入有效整数', trigger: 'change' }],
  }
  type Intent = { action: 'create' | 'update' | 'delete'; key: string; id: string; revision: string; data: typeof fields }
  let intent: Intent | undefined, epoch = 0, readSequence = 0, active = true
  let reader: AbortController | undefined, writer: AbortController | undefined
  const locked = computed(() => saving.value || uncertain.value)
  const baseline = ref('')
  const dirty = computed(() => editing.value && JSON.stringify(fields) !== baseline.value)
  async function load() {
    if (!active || !auth.token) return
    reader?.abort(); reader = new AbortController()
    const signal = reader.signal, ticket = ++readSequence
    loading.value = true; readError.value = ''
    try {
      const items: ProjectCollection[] = []
      for (let page = 1; ; page++) {
        const result = await getProjectCollections(page, signal)
        if (signal.aborted || ticket !== readSequence) return
        items.push(...result.rows)
        if (!result.hasNext) break
      }
      rows.value = items
    } catch (cause) {
      if (ticket === readSequence && !signal.aborted) { rows.value = []; readError.value = cause instanceof Error ? cause.message : '集合加载失败' }
    } finally { if (ticket === readSequence) loading.value = false }
  }
  function reload() { if (!locked.value) { error.value = ''; void load() } }
  function edit(row: ProjectCollection | null = null) {
    if (locked.value) return
    target.value = row ? { ...row } : null
    Object.assign(fields, { name: row?.name || '', description: row?.description || '', color: row?.color || '', orderNum: row?.orderNum || 0 })
    baseline.value = JSON.stringify(fields)
    editing.value = true; error.value = ''; conflict.value = false
  }
  function confirmDiscard() {
    if (locked.value) return false
    if (!dirty.value) return true
    const ticket = epoch
    return ElMessageBox.confirm('集合修改尚未保存，是否放弃修改？', '未保存的修改', {
      confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning',
    }).then(() => ticket === epoch && !locked.value).catch(() => false)
  }
  function leaveEditor(closeDialog: boolean) {
    const ticket = epoch, decision = confirmDiscard()
    const finish = (confirmed: boolean) => {
      if (!confirmed || ticket !== epoch || locked.value) return
      epoch++; editing.value = false; target.value = null; error.value = ''
      if (closeDialog) open.value = false
    }
    if (typeof decision === 'boolean') finish(decision)
    else return decision.then(finish)
  }
  function close() { return leaveEditor(true) }
  function back() { return leaveEditor(false) }
  async function reloadEditor() {
    if (!target.value || locked.value || loading.value) return
    const ticket = epoch, id = target.value.id
    if (!(await confirmDiscard()) || ticket !== epoch || locked.value) return
    error.value = ''; await load()
    if (ticket !== epoch || !active || readError.value) return
    const latest = rows.value.find(row => row.id === id)
    if (!latest) { error.value = '此集合已不存在，请保留需要的输入后返回集合列表'; return }
    edit(latest)
  }
  async function submit() {
    if (locked.value || !active || conflict.value || loading.value) return
    const ticket = epoch
    if (!(await form.value?.validate().catch(() => false)) || ticket !== epoch || locked.value || !active) return
    intent = { action: target.value ? 'update' : 'create', id: target.value?.id || '', revision: target.value?.revision || '', key: crypto.randomUUID(), data: { ...fields, name: fields.name.trim() } }
    await execute()
  }
  async function remove(row: ProjectCollection) {
    if (locked.value || !active) return
    const ticket = epoch
    try { await ElMessageBox.confirm(`删除“${row.name}”将解除其中项目的个人分组，项目和成员保持不变。`, '删除个人集合', { type: 'warning', confirmButtonText: '删除集合', cancelButtonText: '取消' }) } catch { return }
    if (ticket !== epoch || locked.value || !active) return
    intent = { action: 'delete', id: row.id, revision: row.revision, key: crypto.randomUUID(), data: { ...fields } }
    await execute()
  }
  async function execute() {
    if (!intent || saving.value || !active) return
    const current = intent, ticket = epoch
    saving.value = true; uncertain.value = true; error.value = ''; writer = new AbortController()
    try {
      if (current.action === 'delete') await deleteProjectCollection(current.id, current.revision, current.key, writer.signal)
      else if (current.action === 'create') await createProjectCollection({ name: current.data.name, orderNum: current.data.orderNum }, current.key, writer.signal)
      else await updateProjectCollection(current.id, { ...current.data, revision: current.revision, description: current.data.description || null, color: current.data.color || null }, current.key, writer.signal)
      if (ticket !== epoch || !active) return
      intent = undefined; uncertain.value = false; editing.value = false; target.value = null
      changed(current.action === 'delete' ? current.id : undefined); await load()
    } catch (cause) {
      if (ticket !== epoch || !active) return
      const definite = cause instanceof ApiError && ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') || (cause.code >= 400 && cause.code < 500))
      if (definite) {
        intent = undefined; uncertain.value = false
        if (current.action === 'delete') await load()
        else conflict.value = cause.errorCode === 'REVISION_CONFLICT'
      }
      if (ticket !== epoch || !active) return
      error.value = cause instanceof Error ? cause.message : '操作结果未确认，请重试同一请求'
    } finally { if (ticket === epoch) saving.value = false }
  }
  function clear() {
    epoch++; readSequence++; reader?.abort(); writer?.abort(); intent = undefined
    rows.value = []; open.value = false; editing.value = false; target.value = null
    saving.value = false; uncertain.value = false; loading.value = false; error.value = ''
    readError.value = ''
    conflict.value = false
    Object.assign(fields, { name: '', description: '', color: '', orderNum: 0 })
  }
  watch(() => [auth.token, auth.user?.permissions.join('|')], () => { clear(); if (active && auth.token) void load() }, { flush: 'sync' })
  onBeforeRouteLeave(confirmDiscard)
  onMounted(load)
  onDeactivated(() => { active = false; epoch++; readSequence++; reader?.abort(); writer?.abort(); saving.value = false; loading.value = false })
  onActivated(() => { if (!active) { active = true; void load() } })
  onBeforeUnmount(clear)
  return { rows, open, editing, loading, saving, uncertain, conflict, error, readError, form, fields, rules, target, locked, load, reload, reloadEditor, edit, close, back, submit, remove, retry: execute }
}
