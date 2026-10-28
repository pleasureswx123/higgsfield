<script setup>
import { ref } from 'vue'
import JoinRequests from './JoinRequests.vue'
const approvalLocked = ref(false)
import { useProjectMembers } from '@/composables/studio/useProjectMembers'
const {
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
  selectProject: selectProjectInternal,
  searchProjects,
  changeProjectPage,
  changePage,
  changeStatus,
  invalidateCandidate,
  startAdd,
  lookup,
  add,
  modify,
} = useProjectMembers()
function selectProject(row) { if (!selected.value || !approvalLocked.value) selectProjectInternal(row) }
const rules = {
  account: [{ required: true, whitespace: true, message: '请输入完整登录账号', trigger: 'blur' }],
  roleId: [{ required: true, message: '请选择项目角色', trigger: 'change' }],
}
</script>
<template>
  <div class="app-container studio-members">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="仅显示你具有访问权的项目。成员授权按项目权限校验，系统管理员不自动获得项目内容权限。"
    />
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
      role="alert"
    />
    <div class="studio-member-columns">
      <section class="studio-project-list">
        <h3>选择项目</h3>
        <el-input
          v-model="projectSearch"
          clearable
          placeholder="搜索项目名称"
          @keyup.enter="searchProjects"
          @clear="searchProjects"
        />
        <el-button
          class="studio-search"
          :loading="projectsLoading"
          @click="searchProjects"
          >查询</el-button
        >
        <el-table
          v-loading="projectsLoading"
          :data="projects"
          highlight-current-row
          @row-click="selectProject"
        >
          <el-table-column
            prop="name"
            label="项目名称"
            show-overflow-tooltip
          />
          <el-table-column
            label="状态"
            width="88"
            ><template #default="{ row }">{{
              { active: '进行中', paused: '暂停', archived: '归档', pending_delete: '待删除' }[
                row.status
              ]
            }}</template></el-table-column
          >
        </el-table>
        <el-pagination
          v-if="projectTotal > 20"
          :current-page="projectPage"
          :page-size="20"
          :total="projectTotal"
          layout="prev,pager,next"
          @current-change="changeProjectPage"
        />
        <el-button
          link
          @click="loadProjects"
          >刷新项目</el-button
        >
      </section>
      <section class="studio-project-members">
        <template v-if="selected">
          <div class="studio-members-heading">
            <h3>{{ selected.name }} · 项目成员</h3>
            <el-button
              v-if="canManage"
              type="primary"
              :disabled="pending"
              @click="startAdd"
              >添加成员</el-button
            >
          </div>
          <el-radio-group
            v-model="status"
            :disabled="pending"
            @change="changeStatus"
          >
            <el-radio-button value="active">当前成员</el-radio-button
            ><el-radio-button value="removed">已移除</el-radio-button>
          </el-radio-group>
          <el-table
            v-loading="loading"
            :data="members"
          >
            <el-table-column
              prop="displayName"
              label="成员"
            /><el-table-column
              prop="userId"
              label="用户编号"
              width="110"
            />
            <el-table-column
              label="项目角色"
              min-width="170"
              ><template #default="{ row }">
                <el-select
                  v-if="canManage && status === 'active'"
                  :model-value="row.roleId"
                  :disabled="pending"
                  @change="modify(row, $event)"
                >
                  <el-option
                    v-for="role in roles"
                    :key="role.id"
                    :value="role.id"
                    :label="role.name"
                    :disabled="!role.canGrant"
                  /> </el-select
                ><span v-else>{{
                  roles.find((role) => role.id === row.roleId)?.name || '未知角色'
                }}</span>
              </template></el-table-column
            >
            <el-table-column
              v-if="canManage && status === 'active'"
              label="操作"
              width="85"
              ><template #default="{ row }">
                <el-button
                  link
                  type="danger"
                  :disabled="pending"
                  @click="modify(row)"
                  >移除</el-button
                >
              </template></el-table-column
            >
          </el-table>
          <el-pagination
            v-if="total > 20"
            :current-page="page"
            :page-size="20"
            :total="total"
            layout="prev,pager,next"
            @current-change="changePage"
          />
          <el-button
            link
            :disabled="pending"
            @click="loadMembers"
            >刷新成员</el-button
          >
          <JoinRequests :project-id="selected.id" :roles="roles" :can-manage="canManage" @locked="approvalLocked = $event" @changed="loadMembers" />
          </template
        ><el-empty
          v-else
          description="请先选择有权访问的项目"
        />
      </section>
    </div>
    <el-dialog
      v-model="open"
      title="添加项目成员"
      width="480px"
      :close-on-click-modal="!pending"
      :close-on-press-escape="!pending"
      :show-close="!pending"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        :disabled="pending"
      >
        <el-form-item
          label="完整登录账号"
          prop="account"
          ><el-input
            v-model="form.account"
            maxlength="30"
            @input="invalidateCandidate"
        /></el-form-item>
        <el-button
          :loading="searching"
          :disabled="pending || !form.account.trim()"
          @click="lookup"
          >查找账号</el-button
        >
        <p v-if="candidate">{{ candidate.displayName }} · 用户编号 {{ candidate.userId }}</p>
        <el-form-item
          label="项目角色"
          prop="roleId"
          ><el-select v-model="form.roleId">
            <el-option
              v-for="role in grantable"
              :key="role.id"
              :value="role.id"
              :label="role.name"
            /> </el-select
        ></el-form-item>
      </el-form>
      <el-alert
        v-if="dialogError"
        :title="dialogError"
        type="error"
        :closable="false"
      />
      <template #footer
        ><el-button
          :disabled="pending"
          @click="open = false"
          >取消</el-button
        >
        <el-button
          type="primary"
          :loading="pending"
          :disabled="!candidate || !canManage"
          @click="add"
          >确认添加</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>
<style scoped>
.studio-members .el-alert {
  margin-bottom: 16px;
}
.studio-member-columns {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(450px, 2fr);
  gap: 24px;
}
.studio-project-list,
.studio-project-members {
  padding: 20px;
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  background: var(--el-bg-color);
}
.studio-search,
.el-table,
.el-pagination {
  margin: 12px 0;
}
.studio-members-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
@media (max-width: 1000px) {
  .studio-member-columns {
    grid-template-columns: 1fr;
  }
}
</style>
