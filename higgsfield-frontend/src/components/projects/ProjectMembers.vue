<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { Member, ProjectRole } from '@/api/projectWorkspace'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '@/components/ui/dropdown-menu'
import MemberPicker from './MemberPicker.vue'
import StudioSelect from '@/components/ui/StudioSelect.vue'
import StudioPagination from '@/components/ui/StudioPagination.vue'
import { ElDialog, ElForm, ElFormItem, ElSelect, ElOption } from 'element-plus'
import { useMemberManagement } from '@/composables/useMemberManagement'
import { formatProjectDate } from '@/utils/projects'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()
const { members, roles, total, page, status, loading, error, load, changeStatus, changePage,
  grantable, canManage, open, pending, dialogError, roleId, candidate, formRef,
  isOwner, canEditMember, transfer, startAdd, add, modify } = useMemberManagement(props.projectId, () => emit('changed'))
const auth = useAuthStore()
const editingMember = ref<Member>()
const editOpen = ref(false), selectedRole = ref('')
const roleName = (role?: ProjectRole) => role?.code === 'owner' ? '项目所有者' : role?.name || '未知角色'
const roleOptions = computed(() => grantable.value.map(role => ({ value: role.id, label: roleName(role) })))
function editRole(member: Member) {
  editingMember.value = member
  selectedRole.value = member.roleId
  editOpen.value = true
}
async function saveRole() {
  if (!editingMember.value || !canEditMember(editingMember.value) || !grantable.value.some(role => role.id === selectedRole.value)) return
  if (await modify(editingMember.value, selectedRole.value, true)) editOpen.value = false
}
watch(() => auth.token, () => { editOpen.value = false; editingMember.value = undefined })
watch(canManage, value => { if (!value) editOpen.value = false })
const rules = {
  candidate: [{ required: true, message: '请选择人员', trigger: 'change' }],
  roleId: [{ required: true, message: '请选择项目角色', trigger: 'change' }],
}
</script>
<template>
  <section class="members-panel">
    <div class="workspace-section-heading">
      <h2>
        项目成员
      </h2>
      <Button v-if="canManage" :disabled="pending" @click="startAdd">添加成员</Button>
    </div>

    <div class="member-status-tabs">
      <button :class="{ active: status === 'active' }" @click="changeStatus('active')">
        当前成员 <span v-if="status === 'active' && !loading">{{ total }}</span>
      </button>
      <button :class="{ active: status === 'removed' }" @click="changeStatus('removed')">
        已移除 <span v-if="status === 'removed' && !loading">{{ total }}</span>
      </button>
    </div>
    <div v-if="error" class="project-error" role="alert">
      {{ error }} <Button variant="ghost" @click="load">重新加载</Button>
    </div>
    <p v-if="loading" role="status">正在加载成员…</p>
    <div v-else-if="!error" class="member-table-wrap">
      <table class="member-table">
        <thead>
          <tr>
            <th>成员</th>
            <th>项目角色</th>
            <th>加入时间</th>
            <th v-if="canManage && status === 'active'">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="member in members" :key="member.userId">
            <td>
              <div class="member-identity">
                <span class="member-avatar">{{ member.displayName.slice(0, 1) }}</span>
                <div>
                  <strong>{{ member.displayName }}</strong><span v-if="String(auth.user?.user.userId) === member.userId" class="member-self">我</span>
                  <small>{{ member.userName || '账号不可用' }}</small>
                </div>
              </div>
            </td>
            <td>
              <span class="role-pill">{{ roleName(roles.find(role => role.id === member.roleId)) }}</span>
            </td>
            <td class="muted">{{ formatProjectDate(member.joinedAt) }}</td>
            <td v-if="canManage && status === 'active'">
              <div v-if="canEditMember(member)" class="member-actions">
                <Button variant="ghost" :disabled="pending" @click="editRole(member)">修改角色</Button>
                <DropdownMenu>
                  <DropdownMenuTrigger as-child><Button variant="ghost" :disabled="pending" :aria-label="`${member.displayName}的更多操作`">更多</Button></DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem @select="modify(member)">移除成员</DropdownMenuItem>
                    <DropdownMenuItem v-if="isOwner" @select="transfer(member)">转让所有权</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <span v-else class="muted">—</span>
            </td>
          </tr>
          <tr v-if="!members.length">
            <td :colspan="canManage && status === 'active' ? 4 : 3" class="muted member-empty">{{ status === 'removed' ? '暂无已移除成员' : '暂无当前成员' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <StudioPagination
      v-if="total > 20"
      :current-page="page"
      :page-size="20"
      :total="total"
      layout="prev,pager,next"
      @current-change="changePage"
    />
    <ElDialog v-model="open" destroy-on-close title="添加项目成员" width="480px" :close-on-click-modal="false" :close-on-press-escape="!pending" :show-close="!pending">
      <ElForm ref="formRef" :model="{ candidate, roleId }" :rules="rules" label-position="top" :disabled="pending" @submit.prevent>
        <ElFormItem label="1. 选择人员" prop="candidate">
          <MemberPicker v-model="candidate" :project-id="projectId" :disabled="pending" />
        </ElFormItem>
        <ElFormItem label="2. 选择项目角色" prop="roleId">
          <ElSelect v-model="roleId" placeholder="选择项目角色" style="width:100%" :disabled="!candidate || pending">
            <ElOption v-for="option in roleOptions" :key="option.value" :value="option.value" :label="option.label" />
          </ElSelect>
        </ElFormItem>
        <p v-if="dialogError" class="project-error" role="alert">{{ dialogError }}</p>
      </ElForm>
      <template #footer>
        <Button variant="ghost" :disabled="pending" @click="open = false">取消</Button>
        <Button :disabled="pending || !candidate || !roleId" @click="add">{{ pending ? '添加中…' : '添加成员' }}</Button>
      </template>
    </ElDialog>
    <ElDialog v-model="editOpen" title="修改项目角色" width="480px" :close-on-click-modal="false" :close-on-press-escape="!pending" :show-close="!pending">
      <div class="member-candidate"><strong>{{ editingMember?.displayName }}</strong><small>{{ editingMember?.userName }}</small></div>
      <p class="muted">当前角色：{{ roleName(roles.find(role => role.id === editingMember?.roleId)) }}</p>
      <StudioSelect v-model="selectedRole" aria-label="新的项目角色" :options="roleOptions" :disabled="pending" style="width:100%" />
      <template #footer>
        <Button variant="ghost" :disabled="pending" @click="editOpen = false">取消</Button>
        <Button :disabled="pending || !selectedRole || selectedRole === editingMember?.roleId" @click="saveRole">{{ pending ? '保存中…' : '保存角色' }}</Button>
      </template>
    </ElDialog>
  </section>
</template>
<style scoped>
.member-status-tabs { margin:20px 0 0; }
.member-status-tabs button span { margin-left:6px; color:var(--muted-foreground); }
.member-self { display:inline-block; margin-left:8px; font-size:11px; color:var(--muted-foreground); }
.member-actions { display:flex; align-items:center; gap:4px; white-space:nowrap; }
.member-actions button { padding:6px 8px; }
.member-candidate { display:flex; flex-direction:column; gap:6px; padding:14px 16px; border:1px solid var(--border); border-radius:10px; background:var(--surface); margin:0 0 18px; }
.member-candidate small { color:var(--muted-foreground); }
.member-empty { text-align:center; padding:32px; }
.member-table td { vertical-align:middle; }
.member-table th:last-child { min-width:160px; }
</style>
