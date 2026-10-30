<script setup lang="ts">
import { ElCheckbox, ElSelect, ElOption } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useProjectPermissions } from '@/composables/useProjectPermissions'
const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()
const { matrix, draft, groups, dirty, loading, saving, error, notice, load, reset, save } = useProjectPermissions(props.projectId, () => emit('changed'))
</script>
<template>
  <section class="permission-panel" aria-label="角色和权限">
    <header class="workspace-section-heading">
      <div><h2>角色和权限 <span v-if="dirty" class="muted">· 未保存</span></h2><p class="muted">按角色设置当前项目的操作权限</p></div>
      <div v-if="matrix?.canEdit" class="permission-actions">
        <Button variant="outline" :disabled="saving || loading" @click="reset">恢复默认</Button>
        <Button :disabled="saving || loading || !dirty" @click="save">{{ saving ? '保存中…' : '保存权限' }}</Button>
      </div>
    </header>
    <p class="muted">Owner拥有本项目全部业务权限且不可取消，只有Owner可以修改此矩阵。项目访问、成员管理及治理权限固定。灰色选项不可调整；其他权限仍受成员的系统授权限制。选择“本人”仅允许操作本人内容；下载、跨项目复制需单独开启。费用统计与对账统一由后台费用管理员管理。</p>
    <p v-if="error" class="project-error" role="alert">{{ error }} <Button variant="ghost" :disabled="saving" @click="load">重新加载</Button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loading">正在加载权限…</p>
    <template v-if="matrix">
      <section v-for="group in groups" :key="group" class="permission-group">
        <h3>{{ group }}</h3>
        <div class="permission-table-wrap"><table class="permission-table">
          <thead><tr><th scope="col">操作</th><th v-for="role in matrix.roles" :key="role.code" scope="col">{{ role.name }}</th></tr></thead>
          <tbody><tr v-for="row in matrix.rows.filter(row => row.group === group)" :key="row.code">
            <th scope="row">{{ row.label }}</th>
            <td v-for="role in matrix.roles" :key="role.code">
              <ElCheckbox :model-value="!!draft[role.code]?.[row.code] && draft[role.code]?.[row.code] !== 'none'" :disabled="!matrix.canEdit || !row.editable || role.code === 'owner' || saving" :aria-label="`${role.name}：${row.label}`" @change="value => { draft[role.code]![row.code] = value ? (row.scoped ? 'own' : 'project') : 'none' }" />
              <ElSelect v-if="row.scoped && draft[role.code]?.[row.code] && draft[role.code]?.[row.code] !== 'none'" v-model="draft[role.code]![row.code]" :disabled="!matrix.canEdit || !row.editable || role.code === 'owner' || saving" :aria-label="`${role.name}：${row.label}范围`" size="small" class="permission-scope">
                <ElOption label="本人" value="own" /><ElOption label="全项目" value="project" />
              </ElSelect>
            </td>
          </tr></tbody>
        </table></div>
      </section>
    </template>
  </section>
</template>
<style scoped>
.permission-panel { max-width: 1080px; margin: 0 auto; padding: 28px 24px; }
.permission-actions { display: flex; gap: 10px; }
.permission-group { margin-top: 30px; }
.permission-group h3 { font-size: 15px; margin-bottom: 12px; }
.permission-table-wrap { border-radius: 16px; background: var(--surface); border: 1px solid var(--border); overflow-x: auto; padding: 0 16px; }
.permission-table { width: 100%; border-collapse: collapse; table-layout: fixed; min-width: 560px; }
.permission-table th, .permission-table td { padding: 16px 12px; border-bottom: 1px solid var(--border); }
.permission-table thead th { color: var(--muted-foreground); font-size: 12px; font-weight: 400; }
.permission-table th:first-child { text-align: left; width: 40%; }
.permission-table tbody th { font-size: 14px; font-weight: 500; }
.permission-table td { text-align: center; }
.permission-table tr:last-child td, .permission-table tr:last-child th { border-bottom: 0; }
.permission-table :deep(.el-checkbox__inner) { width: 18px; height: 18px; border-radius: 5px; }
.permission-table :deep(.el-checkbox__inner::after) { left: 6px; top: 3px; }
.permission-table :deep(.el-checkbox__input.is-checked:not(.is-disabled) .el-checkbox__inner::after) { border-color: var(--primary-foreground); }
.permission-scope { display: block; width: 88px; margin: 4px auto 0; }
@media (max-width: 640px) { .permission-panel { padding: 16px 0; } .workspace-section-heading { flex-wrap: wrap; gap: 12px; } }
</style>
