import { ref, reactive, computed, watch, onBeforeUnmount, onDeactivated, onActivated } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessageBox } from 'element-plus'
import { getProject, changeProjectLifecycle, type Project } from '@/api/projects'
import { readBrief } from '@/api/projectWorkspace'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

export function useProjectLifecycle(changed: (project: Project) => void) {
  const auth = useAuthStore(), open = ref(false), target = ref<Project | null>(null)
  type Action = 'archive' | 'restore' | 'rename' | 'pause' | 'resume'
  const action = ref<Action>('archive'), form = ref<FormInstance>()
  const loading = ref(false), saving = ref(false), uncertain = ref(false), ready = ref(false), error = ref('')
  const fields = reactive({ reason: '', name: '' })
  const locked = computed(() => saving.value || uncertain.value)
  const initialName = ref('')
  const dirty = computed(() => open.value && (action.value === 'rename'
    ? fields.name !== initialName.value : Boolean(fields.reason.trim())))
  const rules = computed<FormRules>(() => ({ reason: [{ validator: (_rule, value, callback) => {
    if (['archive', 'pause'].includes(action.value) && !String(value ?? '').trim()) callback(new Error('请填写操作原因'))
    else if (String(value ?? '').length > 4000) callback(new Error('原因不能超过4000字'))
    else callback()
  }, trigger: 'blur' }], name: [{ validator: (_rule, value, callback) => {
    const name = String(value ?? '').trim()
    if (!name || name.length > 200 || /[\u0000-\u001f]/.test(name)) callback(new Error('请输入1至200字的项目名称，不含控制字符'))
    else callback()
  }, trigger: 'blur' }] }))
  let epoch = 0, active = true, reader: AbortController | undefined, writer: AbortController | undefined
  let intent: { id: string; action: Action; key: string; data: { revision: string; reason?: string; name?: string } } | undefined
  async function load(refreshName = false) {
    if (!target.value || !active || locked.value) return
    reader?.abort(); reader = new AbortController()
    const signal = reader.signal, ticket = ++epoch, id = target.value.id
    loading.value = true; ready.value = false; error.value = ''
    try {
      const [project, brief] = await Promise.all([getProject(id, signal), readBrief(id, signal)])
      if (ticket !== epoch || signal.aborted) return
      target.value = project.data
      if (refreshName) { fields.name = project.data.name; initialName.value = project.data.name }
      const permission = ['archive', 'restore'].includes(action.value) ? 'project:archive' : 'project:manage'
      if (!brief.data.allowedActions.includes(permission)) throw new Error('当前没有执行此项目操作的权限')
      const sources: Record<Action, string[]> = { rename: ['active'], archive: ['active', 'paused'], restore: ['archived'], pause: ['active'], resume: ['paused'] }
      if (!sources[action.value].includes(project.data.status))
        throw new Error('项目状态已变化，请关闭窗口后刷新项目')
      ready.value = true
    } catch (cause) {
      if (ticket === epoch && !signal.aborted) error.value = cause instanceof Error ? cause.message : '项目状态读取失败'
    } finally { if (ticket === epoch) loading.value = false }
  }
  function start(project: Project, value: Action) {
    if (!active || locked.value) return
    target.value = { ...project }; action.value = value; fields.reason = ''; fields.name = project.name; initialName.value = project.name; open.value = true
    void load(true)
  }
  function dismiss() {
    if (locked.value) return
    epoch++; reader?.abort(); open.value = false; target.value = null; ready.value = false; loading.value = false
  }
  function confirmDiscard() {
    if (locked.value) return false
    if (!dirty.value) return true
    const ticket = epoch
    return ElMessageBox.confirm('项目名称或操作原因尚未提交，是否放弃修改？', '未提交的修改', {
      confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning',
    }).then(() => ticket === epoch && !locked.value).catch(() => false)
  }
  function close() {
    const ticket = epoch, decision = confirmDiscard()
    if (typeof decision === 'boolean') { if (decision) dismiss(); return }
    return decision.then(confirmed => { if (confirmed && ticket === epoch) dismiss() })
  }
  async function save() {
    if (!active || saving.value || !ready.value || !target.value) return
    const ticket = epoch
    if (!intent) {
      if (!(await form.value?.validate().catch(() => false)) || ticket !== epoch || !active || saving.value) return
      intent = { id: target.value.id, action: action.value, key: crypto.randomUUID(),
        data: action.value === 'rename' ? { revision: target.value.revision, name: fields.name.trim() }
          : { revision: target.value.revision, reason: fields.reason.trim() } }
    }
    const current = intent
    saving.value = true; uncertain.value = true; error.value = ''; writer = new AbortController()
    try {
      const result = await changeProjectLifecycle(current.id, current.action, current.data, current.key, writer.signal)
      if (ticket !== epoch || !active) return
      intent = undefined; uncertain.value = false; saving.value = false; dismiss(); changed(result.data)
    } catch (cause) {
      if (ticket !== epoch || !active) return
      const definite = cause instanceof ApiError && ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') || (cause.code >= 400 && cause.code < 500))
      if (definite) { intent = undefined; uncertain.value = false; ready.value = false }
      error.value = cause instanceof Error ? cause.message : '操作结果尚未确认，请重试同一请求'
    } finally { if (ticket === epoch) saving.value = false }
  }
  function clear() {
    epoch++; reader?.abort(); writer?.abort(); intent = undefined
    open.value = false; target.value = null; fields.reason = ''; fields.name = ''; error.value = ''
    saving.value = false; loading.value = false; uncertain.value = false; ready.value = false
  }
  watch(() => [auth.token, auth.user?.permissions.join('|')], clear, { flush: 'sync' })
  onBeforeRouteLeave(confirmDiscard)
  onBeforeRouteUpdate((to, from) => to.params.id === from.params.id ? true : confirmDiscard())
  onDeactivated(() => { active = false; epoch++; reader?.abort(); writer?.abort(); saving.value = false; loading.value = false })
  onActivated(() => { active = true; if (open.value && !uncertain.value) void load() })
  onBeforeUnmount(clear)
  return { open, target, action, form, fields, rules, loading, saving, uncertain, ready, locked, error, start, close, load, save }
}
