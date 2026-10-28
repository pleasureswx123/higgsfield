<script setup lang="ts">
import { ElPagination } from 'element-plus'
import { useProjectMembers } from '@/composables/useProjectWorkspace'
import { formatProjectDate } from '@/utils/projects'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ projectId: string }>()
const { members, roles, total, page, status, loading, error, load, changeStatus, changePage } =
  useProjectMembers(props.projectId)
</script>
<template>
  <section class="members-panel">
    <div class="workspace-section-heading">
      <h2>
        成员 <span class="muted">{{ total }}</span>
      </h2>
    </div>
    <p class="muted">成员添加、移除和角色分配统一在后台管理平台操作。</p>
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
              <span class="role-pill">{{
                roles.find((r) => r.id === member.roleId)?.name || '未知角色'
              }}</span>
            </td>
            <td class="muted">{{ formatProjectDate(member.joinedAt) }}</td>
          </tr>
          <tr v-if="!members.length">
            <td colspan="3" class="muted">暂无成员</td>
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
  </section>
</template>
