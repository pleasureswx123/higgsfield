import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { transferOwnership, addMember, changeMember, removeMember, type Candidate, type Member } from '@/api/projectWorkspace'
import { useProjectMembers } from './useProjectWorkspace'
import { useAuthStore } from '@/stores/auth'

export function useMemberManagement(projectId: string, changed: () => void = () => {}) {
  const list = useProjectMembers(projectId)
  const grantable = computed(() => list.roles.value.filter((role) => role.canGrant))
  const isOwner = computed(() => list.roles.value.some((role) => role.code === 'owner' && role.isCurrentRole))
  const canEditMember = (member: Member) => grantable.value.some((role) => role.id === member.roleId)
  const canManage = computed(() => grantable.value.length > 0)
  const open = ref(false), pending = ref(false), dialogError = ref('')
  const roleId = ref(''), candidate = ref<Candidate>()
  const formRef = ref<FormInstance>()
  let epoch = 0, alive = true, lastPayload = '', mutationKey = ''
  watch(() => useAuthStore().token, () => {
    epoch++; candidate.value = undefined; open.value = false
    pending.value = false; lastPayload = ''; mutationKey = ''
  }, { flush: 'sync' })
  onBeforeUnmount(() => { alive = false })
  watch(canManage, value => {
    if (!value) { open.value = false; candidate.value = undefined }
  }, { flush: 'sync' })
  function startAdd() {
    candidate.value = undefined; roleId.value = ''
    dialogError.value = ''; open.value = true
  }
  async function mutate(action: 'add' | 'role' | 'remove' | 'transfer', member?: Member, nextRole?: string) {
    if (pending.value || !canManage.value) return
    const stamp = epoch
    const payload = JSON.stringify([action, member?.userId ?? candidate.value?.userId, member?.revision, nextRole ?? roleId.value])
    if (payload !== lastPayload) { lastPayload = payload; mutationKey = crypto.randomUUID() }
    pending.value = true; dialogError.value = ''
    try {
      if (action === 'transfer' && member) await transferOwnership(projectId, { userId: member.userId, revision: list.ownershipRevision.value, targetRevision: member.revision }, mutationKey)
      else if (action === 'add' && candidate.value) await addMember(projectId, { userId: candidate.value.userId, roleId: roleId.value }, mutationKey)
      else if (action === 'role' && member && nextRole) await changeMember(projectId, member, nextRole, mutationKey)
      else if (action === 'remove' && member) await removeMember(projectId, member, mutationKey)
      else return
      if (!alive || stamp !== epoch) return
      lastPayload = ''; mutationKey = ''
      open.value = false
      ElMessage.success(action === 'transfer' ? '所有权已转让，你已成为项目负责人' : action === 'add' ? '成员已添加' : action === 'role' ? '角色已更新' : '成员已移除')
      if (action === 'add') list.page.value = 1
      await list.load()
      changed()
      return true
    } catch (cause) {
      if (!alive || stamp !== epoch) return
      const message = cause instanceof Error ? cause.message : '操作失败'
      if (action === 'add') dialogError.value = message
      else { ElMessage.error(message); await list.load() }
    } finally { if (stamp === epoch) pending.value = false }
  }
  async function add() {
    if (pending.value || !await formRef.value?.validate().catch(() => false)) return
    if (!candidate.value || candidate.value.alreadyMember) { dialogError.value = '请选择要添加的人员。'; return }
    await mutate('add')
  }
  async function modify(member: Member, nextRole?: string, confirmed = false) {
    if (pending.value || !canEditMember(member) || nextRole === member.roleId) return
    if (nextRole && !grantable.value.some(role => role.id === nextRole)) return
    if (!confirmed) try {
      await ElMessageBox.confirm(nextRole ? `将“${member.displayName}”的角色改为“${grantable.value.find((r) => r.id === nextRole)?.name}”？` : `将“${member.displayName}”移出本项目？`, nextRole ? '修改项目角色' : '移除成员', { confirmButtonText: '确认', cancelButtonText: '取消' })
    } catch { return }
    return await mutate(nextRole ? 'role' : 'remove', member, nextRole)
  }
  async function transfer(member: Member) {
    if (!isOwner.value || pending.value || !canEditMember(member)) return
    try {
      await ElMessageBox.confirm(`将项目所有权转让给“${member.displayName}”？对方将拥有本项目全部权限，你将成为负责人。`, '转让项目所有权', { confirmButtonText: '确认转让', cancelButtonText: '取消', type: 'warning' })
    } catch { return }
    await mutate('transfer', member)
  }
  return { ...list, isOwner, canEditMember, transfer, grantable, canManage, open, pending, dialogError, roleId, candidate, formRef, startAdd, add, modify }
}
