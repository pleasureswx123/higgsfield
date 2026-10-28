import { ref, reactive, computed, watch, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { listJoinRequests, reviewJoinRequest } from '@/api/studio/joinRequests'

export function useJoinRequests(project, roles, canManage, changed) {
  const user = useUserStore(), rows = ref([]), total = ref(0), page = ref(1), status = ref('pending')
  const loading = ref(false), error = ref(''), target = ref(), formRef = ref()
  const form = reactive({ decision: 'approved', roleId: '', reason: '' })
  const saving = ref(false), uncertain = ref(false), actionError = ref('')
  const locked = computed(() => saving.value || uncertain.value)
  const allowed = () => user.permissions.includes('*:*:*') || user.permissions.includes('member:manage')
  let reader, writer, epoch = 0, key = '', intent, active = true
  async function load() {
    reader?.abort()
    rows.value = []; total.value = 0; loading.value = false
    if (!active) return
    if (!allowed() || !user.token) { error.value = '没有读取加入申请的权限'; return }
    const current = new AbortController(); reader = current
    rows.value = []; total.value = 0; error.value = ''; loading.value = true
    try {
      const result = await listJoinRequests(project(), { pageNum: page.value, pageSize: 20, ...(status.value ? { status: status.value } : {}) }, current.signal)
      if (!current.signal.aborted) { rows.value = result.rows; total.value = result.total }
    } catch (cause) { if (!current.signal.aborted) error.value = cause?.message || '申请读取失败' }
    finally { if (!current.signal.aborted) loading.value = false }
  }
  function start(row) {
    if (!active || locked.value || !allowed() || !canManage() || row.status !== 'pending') return
    target.value = { ...row }; Object.assign(form, { decision: 'approved', roleId: '', reason: '' })
    key = ''; intent = undefined; actionError.value = ''
  }
  function close() { if (!locked.value) target.value = undefined }
  async function submit() {
    if (!active || saving.value || !allowed() || !target.value || !canManage()) return
    const stamp = epoch
    saving.value = true; actionError.value = ''
    try {
      if (!uncertain.value) {
        if (!(await formRef.value?.validate().catch(() => false)) || stamp !== epoch) return
        if (form.decision === 'approved' && !roles().some(role => role.id === form.roleId && role.canGrant)) throw new Error('请选择可授予的项目角色')
        intent = { revision: target.value.revision, decision: form.decision, reason: form.reason.trim(), ...(form.decision === 'approved' ? { roleId: form.roleId } : {}) }
        key = crypto.randomUUID()
      }
      if (stamp !== epoch || !canManage()) return
      const current = new AbortController(); writer = current
      // 请求发出后锁定意图，未确认响应只重试原请求。
      uncertain.value = true
      await reviewJoinRequest(target.value.id, intent, key, current.signal)
      if (stamp !== epoch) return
      uncertain.value = false; target.value = undefined; intent = undefined; key = ''
      await load(); changed()
    } catch (cause) {
      if (stamp === epoch) {
        if ((cause?.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') || (cause?.response?.status >= 400 && cause.response.status < 500)) uncertain.value = false
        actionError.value = cause?.message || '审批结果未确认，请重试原请求'
      }
    } finally { if (stamp === epoch) saving.value = false }
  }
  function clear() {
    epoch++; reader?.abort(); writer?.abort(); rows.value = []; total.value = 0
    target.value = undefined; loading.value = false; saving.value = false; uncertain.value = false
    key = ''; intent = undefined; error.value = ''; actionError.value = ''
  }
  watch([project, () => user.token, () => user.permissions.join(',')], () => { clear(); page.value = 1; void load() }, { immediate: true, flush: 'sync' })
  function filter() { if (locked.value) return; page.value = 1; void load() }
  function changePage(value) { if (!locked.value) { page.value = value; void load() } }
  onBeforeUnmount(clear)
  onDeactivated(() => {
    active = false; epoch++; reader?.abort(); writer?.abort()
    rows.value = []; total.value = 0; loading.value = false; saving.value = false
    // 已发出的审批保留原意图，重新进入后仍须确认原结果。
  })
  onActivated(() => {
    const resume = !active
    active = true
    if (resume) void load()
  })
  onBeforeRouteLeave(() => !locked.value)
  return { rows, total, page, status, loading, error, target, form, formRef, saving, uncertain, locked, actionError, load, start, close, submit, filter, changePage }
}
