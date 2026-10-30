<script setup lang="ts">
import { ElPagination, ElDialog, ElForm, ElFormItem, ElInput, ElSelect, ElOption } from 'element-plus'
import { useMemberManagement } from '@/composables/useMemberManagement'
import { formatProjectDate } from '@/utils/projects'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()
const { members, roles, total, page, status, loading, error, load, changeStatus, changePage,
  grantable, canManage, open, pending, searching, dialogError, account, roleId, candidate, formRef,
  isOwner, canEditMember, transfer, startAdd, lookup, add, modify } = useMemberManagement(props.projectId, () => emit('changed'))
const rules = {
  account: [{ required: true, whitespace: true, message: '请输入完整登录账号', trigger: 'blur' }],
  roleId: [{ required: true, message: '请选择项目角色', trigger: 'change' }],
}
</script>
<template>
  <section class="members-panel">
    <div class="workspace-section-heading">
      <h2>
        成员 <span class="muted">{{ total }}</span>
      </h2>
      <Button v-if="canManage" :disabled="pending" @click="startAdd">添加成员</Button>
    </div>
    <p class="muted">创建者自动成为唯一 Owner，拥有本项目全部业务权限；Owner 可转让所有权，负责人可管理制作人和查看者。</p>
    <div class="member-status-tabs">
      <button :class="{ active: status === 'active' }" @click="changeStatus('active')">
        当前成员
      </button>
      <button :class="{ active: status === 'removed' }" @click="changeStatus('removed')">
        已移除
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
            <th>角色</th>
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
                  <strong>{{ member.displayName }}</strong
                  ><small>用户编号 {{ member.userId }}</small>
                </div>
              </div>
            </td>
            <td>
              <ElSelect v-if="canEditMember(member) && status === 'active'" :model-value="member.roleId" :disabled="pending" aria-label="项目角色" style="width: 130px" @change="(value: string) => modify(member, value)">
                <ElOption v-for="role in grantable" :key="role.id" :label="role.name" :value="role.id" />
              </ElSelect>
              <span v-else class="role-pill">{{
                roles.find((r) => r.id === member.roleId)?.name || '未知角色'
              }}</span>
            </td>
            <td class="muted">{{ formatProjectDate(member.joinedAt) }}</td>
            <td v-if="canManage && status === 'active'"><Button v-if="canEditMember(member)" variant="ghost" :disabled="pending" @click="modify(member)">移除</Button><Button v-if="isOwner && canEditMember(member)" variant="ghost" :disabled="pending" @click="transfer(member)">转让所有权</Button></td>
          </tr>
          <tr v-if="!members.length">
            <td :colspan="canManage && status === 'active' ? 4 : 3" class="muted">暂无成员</td>
          </tr>
        </tbody>
      </table>
    </div>
    <ElPagination
      v-if="total > 20"
      :current-page="page"
      :page-size="20"
      :total="total"
      layout="prev,pager,next"
      @current-change="changePage"
    />
    <ElDialog v-model="open" title="添加项目成员" width="480px" :close-on-click-modal="false" :close-on-press-escape="!pending" :show-close="!pending">
      <ElForm ref="formRef" :model="{ account, roleId }" :rules="rules" label-position="top" :disabled="pending" @submit.prevent>
        <ElFormItem label="登录账号" prop="account">
          <ElInput v-model="account" placeholder="例如 hf_test_maker_a" @keyup.enter="lookup">
            <template #append><button type="button" :disabled="searching || pending || !account.trim()" @click="lookup">{{ searching ? '查找中…' : '查找' }}</button></template>
          </ElInput>
        </ElFormItem>
        <p v-if="candidate">已找到：{{ candidate.displayName }}（用户编号 {{ candidate.userId }}）</p>
        <ElFormItem label="项目角色" prop="roleId">
          <ElSelect v-model="roleId" placeholder="选择项目角色" style="width: 100%">
            <ElOption v-for="role in grantable" :key="role.id" :label="role.name" :value="role.id" />
          </ElSelect>
        </ElFormItem>
        <p class="muted">负责人管理成员和项目；制作成员参与制作；只读成员浏览项目。已移除的成员可在此重新添加。</p>
        <p v-if="dialogError" class="project-error" role="alert">{{ dialogError }}</p>
      </ElForm>
      <template #footer>
        <Button variant="ghost" :disabled="pending" @click="open = false">取消</Button>
        <Button :disabled="pending || searching || !candidate" @click="add">{{ pending ? '添加中…' : '添加成员' }}</Button>
      </template>
    </ElDialog>
  </section>
</template>
