import { computed, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { ElMessageBox } from 'element-plus'
import {
  listStudioProjects,
  getProjectMembers,
  getProjectRoles,
  findProjectCandidate,
  addProjectMember,
  updateProjectMember,
  removeProjectMember,
} from '@/api/studio/projects'

export function useProjectMembers() {
  const user = useUserStore()
  const active = ref(true)
  let epoch = 0
  const projects = ref([]),
    projectTotal = ref(0),
    projectPage = ref(1),
    projectSearch = ref(''),
    selected = ref(null)
  const members = ref([]),
    roles = ref([]),
    total = ref(0),
    page = ref(1),
    status = ref('active')
  const loading = ref(false),
    projectsLoading = ref(false),
    pending = ref(false),
    error = ref('')
  const open = ref(false),
    formRef = ref(),
    form = reactive({ account: '', roleId: '' })
  const candidate = ref(null),
    searching = ref(false),
    dialogError = ref('')
  const grantable = computed(() => roles.value.filter((role) => role.canGrant))
  const canManage = computed(
    () => active.value && selected.value?.status === 'active' && grantable.value.length > 0 &&
      (user.permissions.includes('*:*:*') || user.permissions.includes('member:manage'))
  )
  let projectSequence = 0,
    memberSequence = 0,
    lookupSequence = 0,
    signature = '',
    key = '',
    alive = true
  const message = (cause) => (cause instanceof Error ? cause.message : '请求失败，请重试')
  async function loadProjects() {
    if (!alive || !active.value || !user.token) return
    const ticket = ++projectSequence
    projectsLoading.value = true
    error.value = ''
    try {
      const result = await listStudioProjects({
        pageNum: projectPage.value,
        pageSize: 20,
        q: projectSearch.value,
      })
      if (!alive || ticket !== projectSequence) return
      projects.value = result.rows
      projectTotal.value = result.total
    } catch (cause) {
      if (alive && ticket === projectSequence) {
        error.value = message(cause)
        projects.value = []
      }
    } finally {
      if (alive && ticket === projectSequence) projectsLoading.value = false
    }
  }
  async function loadMembers() {
    if (!alive || !active.value || !user.token) return
    const id = selected.value?.id
    if (!id) return
    const ticket = ++memberSequence
    loading.value = true
    error.value = ''
    try {
      const [list, roleList] = await Promise.all([
        getProjectMembers(id, { pageNum: page.value, pageSize: 20, status: status.value }),
        getProjectRoles(id),
      ])
      if (!alive || ticket !== memberSequence) return
      members.value = list.rows
      total.value = list.total
      roles.value = roleList.data.items
    } catch (cause) {
      if (alive && ticket === memberSequence) {
        error.value = message(cause)
        members.value = []
        roles.value = []
        total.value = 0
      }
    } finally {
      if (alive && ticket === memberSequence) loading.value = false
    }
  }
  function selectProject(project) {
    if (pending.value) return
    selected.value = project
    page.value = 1
    status.value = 'active'
    members.value = []
    roles.value = []
    open.value = false
    lookupSequence++
    void loadMembers()
  }
  function searchProjects() {
    projectPage.value = 1
    void loadProjects()
  }
  function changeProjectPage(value) {
    projectPage.value = value
    void loadProjects()
  }
  function changePage(value) {
    page.value = value
    void loadMembers()
  }
  function changeStatus() {
    page.value = 1
    void loadMembers()
  }
  function invalidateCandidate() {
    lookupSequence++
    candidate.value = null
    dialogError.value = ''
    searching.value = false
  }
  function startAdd() {
    if (pending.value || !canManage.value) return
    form.account = ''
    form.roleId = grantable.value.find((role) => role.code === 'viewer')?.id || ''
    invalidateCandidate()
    signature = ''
    open.value = true
  }
  async function lookup() {
    if (!active.value || !canManage.value || !selected.value || !form.account.trim()) return
    const ticket = ++lookupSequence
    searching.value = true
    candidate.value = null
    dialogError.value = ''
    try {
      const result = await findProjectCandidate(selected.value.id, form.account.trim())
      if (!alive || ticket !== lookupSequence) return
      candidate.value = result.data.items[0] || null
      if (!candidate.value) dialogError.value = '未找到可用账号，请核对完整登录账号'
    } catch (cause) {
      if (alive && ticket === lookupSequence) dialogError.value = message(cause)
    } finally {
      if (alive && ticket === lookupSequence) searching.value = false
    }
  }
  async function add() {
    const stamp = epoch, selectedId = selected.value?.id
    if (
      pending.value ||
      !canManage.value ||
      !candidate.value ||
      !(await formRef.value?.validate().catch(() => false))
    )
      return
    if (stamp !== epoch || pending.value || !canManage.value || !candidate.value || selected.value?.id !== selectedId) return
    const id = selected.value.id
    const data = { userId: candidate.value.userId, roleId: form.roleId }
    const next = JSON.stringify([id, data])
    if (next !== signature) {
      signature = next
      key = crypto.randomUUID()
    }
    pending.value = true
    dialogError.value = ''
    try {
      await addProjectMember(id, data, key)
      if (stamp !== epoch) return
      open.value = false
      page.value = 1
      status.value = 'active'
      await loadMembers()
    } catch (cause) {
      if (stamp === epoch) dialogError.value = message(cause)
    } finally {
      if (stamp === epoch) pending.value = false
    }
  }
  async function modify(member, roleId) {
    const stamp = epoch
    if (pending.value || !canManage.value || roleId === member.roleId) return
    const id = selected.value.id
    try {
      await ElMessageBox.confirm(
        roleId
          ? `确认调整“${member.displayName}”的项目角色？`
          : `移除“${member.displayName}”后立即撤销项目访问权，历史身份记录保留。`,
        '成员授权',
        { confirmButtonText: '确认', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
    if (stamp !== epoch || pending.value || !canManage.value || selected.value?.id !== id) return
    pending.value = true
    error.value = ''
    try {
      if (roleId) await updateProjectMember(id, member, roleId, crypto.randomUUID())
      else await removeProjectMember(id, member, crypto.randomUUID())
      if (stamp !== epoch) return
      await loadMembers()
    } catch (cause) {
      if (stamp === epoch) error.value = message(cause)
    } finally {
      if (stamp === epoch) pending.value = false
    }
  }
  onMounted(loadProjects)
  function clear(full = false) {
    epoch++; projectSequence++; memberSequence++; lookupSequence++
    projects.value = []; members.value = []; roles.value = []
    projectTotal.value = 0; total.value = 0; candidate.value = null
    pending.value = false; loading.value = false; projectsLoading.value = false; searching.value = false
    error.value = ''; dialogError.value = ''; open.value = false
    if (full) {
      selected.value = null; form.account = ''; form.roleId = ''; projectSearch.value = ''
      page.value = 1; projectPage.value = 1; signature = ''; key = ''
    }
  }
  watch([() => user.token, () => user.permissions.join(',')], () => clear(true), { flush: 'sync' })
  onDeactivated(() => { active.value = false; clear() })
  onActivated(() => {
    const resume = !active.value
    active.value = true
    if (resume) { void loadProjects(); if (selected.value) void loadMembers() }
  })
  onBeforeRouteLeave(() => !pending.value)
  onBeforeUnmount(() => {
    alive = false
    clear(true)
  })
  return {
    projects,
    projectTotal,
    projectPage,
    projectSearch,
    selected,
    members,
    roles,
    total,
    page,
    status,
    loading,
    projectsLoading,
    pending,
    error,
    open,
    formRef,
    form,
    candidate,
    searching,
    dialogError,
    grantable,
    canManage,
    loadProjects,
    loadMembers,
    selectProject,
    searchProjects,
    changeProjectPage,
    changePage,
    changeStatus,
    invalidateCandidate,
    startAdd,
    lookup,
    add,
    modify,
  }
}

