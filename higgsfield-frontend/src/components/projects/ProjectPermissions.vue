<script setup lang="ts">
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { IconChevronDown, IconInfoCircle } from '@tabler/icons-vue'
import StudioSelect from '@/components/ui/StudioSelect.vue'
import { Checkbox } from '@/components/ui/checkbox'
import Button from '@/components/ui/Button.vue'
import { useProjectPermissions } from '@/composables/useProjectPermissions'
const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()
const { matrix, draft, groups, dirty, loading, saving, error, notice, load, reset, save, changePermission } = useProjectPermissions(props.projectId, () => emit('changed'))
</script>
<template>
  <section class="permission-panel" aria-label="角色和权限">
    <header class="workspace-section-heading">
      <div><h2>角色和权限 <span v-if="dirty" class="permission-unsaved">未保存</span></h2><p class="muted">按角色设置当前项目的操作权限</p></div>
      <div v-if="matrix?.canEdit" class="permission-actions">
        <Button variant="outline" :disabled="saving || loading" @click="reset">恢复默认</Button>
        <Button :disabled="saving || loading || !dirty" @click="save">{{ saving ? '保存中…' : '保存权限' }}</Button>
      </div>
    </header>
    <div v-if="notice || dirty" class="permission-notice" role="status">
      <IconInfoCircle :size="16" aria-hidden="true" />
      <span>{{ notice || '权限已修改，尚未保存' }}</span>
    </div>
    <Collapsible class="permission-rules">
      <div class="permission-rules-summary">
        <p class="muted">仅项目所有者可修改权限，锁定项不可调整。</p>
        <CollapsibleTrigger as-child>
          <Button variant="ghost" class="permission-rules-trigger">查看权限规则<IconChevronDown :size="14" aria-hidden="true" /></Button>
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent>
        <ul class="permission-rule-list">
          <li>项目所有者拥有本项目全部业务权限；项目访问、成员管理和治理权限固定，不可调整。</li>
          <li>权限依次继承：项目所有者 ≥ 负责人 ≥ 制作人 ≥ 查看者。开启低级角色的权限时，高级角色同步开启；“全项目”范围包含“本人”。</li>
        </ul>
      </CollapsibleContent>
    </Collapsible>
    <p v-if="error" class="project-error" role="alert">{{ error }} <Button variant="ghost" :disabled="saving" @click="load">重新加载</Button></p>
    <p v-if="loading">正在加载权限…</p>
    <template v-if="matrix">
      <section v-for="group in groups" :key="group" class="permission-group">
        <h3>{{ group }}</h3>
        <div class="permission-table-wrap"><table class="permission-table">
          <thead><tr><th scope="col">操作</th><th v-for="role in matrix.roles" :key="role.code" scope="col">{{ role.code === 'owner' ? '项目所有者' : role.name }}</th></tr></thead>
          <tbody><tr v-for="row in matrix.rows.filter(row => row.group === group)" :key="row.code">
            <th scope="row">{{ row.label }}</th>
            <td v-for="role in matrix.roles" :key="role.code">
              <Checkbox :model-value="!!draft[role.code]?.[row.code] && draft[role.code]?.[row.code] !== 'none'" :disabled="!matrix.canEdit || !row.editable || role.code === 'owner' || saving" :aria-label="`${role.code === 'owner' ? '项目所有者' : role.name}：${row.label}`" @update:model-value="value => changePermission(role.code, row.code, value === true ? (row.scoped ? 'own' : 'project') : 'none')" />
              <StudioSelect v-if="row.scoped && draft[role.code]?.[row.code] && draft[role.code]?.[row.code] !== 'none'" :model-value="draft[role.code]![row.code]" @change="value => { if (value === 'own' || value === 'project') changePermission(role.code, row.code, value) }" :disabled="!matrix.canEdit || !row.editable || role.code === 'owner' || saving" :aria-label="`${role.code === 'owner' ? '项目所有者' : role.name}：${row.label}范围`" class="permission-scope" :options="[{ label: '本人', value: 'own' }, { label: '全项目', value: 'project' }]" />
            </td>
          </tr></tbody>
        </table></div>
      </section>
    </template>
  </section>
</template>
<style scoped>
.permission-panel { max-width: 1080px; margin: 0 auto; padding: 28px 24px; }
.permission-unsaved { display:inline-block; margin-left:8px; padding:3px 8px; border-radius:999px; background:var(--surface-hover); color:var(--muted-foreground); font-size:12px; font-weight:400; vertical-align:middle; }
.permission-notice { display:flex; align-items:flex-start; gap:8px; margin:16px 0; padding:10px 12px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--foreground); font-size:13px; line-height:20px; }
.permission-notice svg { flex-shrink:0; margin-top:2px; color:var(--muted-foreground); }
.permission-rules { margin-top:16px; }
.permission-rules-summary { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; }
.permission-rules-summary p { margin:0; font-size:12px; line-height:20px; }
.permission-rules-trigger { gap:6px; color:var(--muted-foreground); font-size:12px; }
.permission-rules-trigger[data-state="open"] svg { transform:rotate(180deg); }
.permission-rule-list { margin:8px 0 0; padding:12px 16px 12px 30px; border-radius:8px; background:var(--surface); color:var(--muted-foreground); font-size:12px; line-height:1.8; list-style:disc; }
.permission-rule-list li + li { margin-top:6px; }
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
