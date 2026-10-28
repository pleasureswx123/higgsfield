<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElSelect, ElOption, ElDialog, ElForm, ElFormItem, ElInput, ElInputNumber, ElAlert, ElTable, ElTableColumn } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useProjectCollections } from '@/composables/useProjectCollections'
import type { ProjectCollection } from '@/api/projectPreferences'
const selected = defineModel<string>({ required: true })
const emit = defineEmits<{ filter: []; changed: [] }>()
const { rows, open, editing, loading, saving, uncertain, conflict, error, readError, form, fields, rules, target, locked, reload, reloadEditor, edit, close, back, submit, remove, retry } = useProjectCollections((deletedId) => {
  if (deletedId && selected.value === deletedId) { selected.value = ''; emit('filter') }
  else emit('changed')
})
</script>
<template>
  <div class="collection-controls">
    <ElSelect v-model="selected" placeholder="全部集合" aria-label="个人集合筛选" :loading="loading" @change="emit('filter')">
      <ElOption label="全部集合" value="" />
      <ElOption v-if="selected && !rows.some(row => row.id === selected)" :value="selected" label="当前集合（未加载或已删除）" />
      <ElOption v-for="row in rows" :key="row.id" :value="row.id" :label="row.name" />
    </ElSelect>
    <Button variant="ghost" @click="open = true">管理集合</Button>
    <span v-if="readError && !open" role="alert">集合加载失败，请打开管理集合重试。</span>
  </div>
  <ElDialog :model-value="open" title="个人项目集合" width="min(720px, 94vw)" align-center :close-on-click-modal="false"
    :show-close="!locked" :close-on-press-escape="!locked" :before-close="() => close()">
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="个人项目集合" />
    </template>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />
    <ElAlert v-if="readError" :title="readError" type="error" :closable="false" />
    <ElAlert v-if="editing && conflict" title="集合已被修改，你的输入已保留。请先复制需要保留的内容，再重新载入最新版本后编辑。" type="warning" :closable="false" />
    <ElAlert v-if="uncertain && !saving" title="操作结果未确认，请重试同一请求；确认前不能更改内容或离开。" type="warning" :closable="false" />
    <template v-if="!editing">
      <Button :disabled="locked" @click="edit()">新建集合</Button>
      <Button variant="ghost" :disabled="locked || loading" @click="reload">刷新</Button>
      <p v-if="loading" role="status">正在加载个人集合…</p>
      <ElTable v-else-if="!readError" :data="rows" empty-text="暂无个人集合">
        <ElTableColumn prop="name" label="名称" /><ElTableColumn prop="orderNum" label="排序" width="80" />
        <ElTableColumn label="操作" width="150"><template #default="{ row }">
          <Button variant="ghost" :disabled="locked" @click="edit(row as ProjectCollection)">编辑</Button>
          <Button variant="ghost" :disabled="locked" @click="remove(row as ProjectCollection)">删除</Button>
        </template></ElTableColumn>
      </ElTable>
    </template>
    <ElForm v-else ref="form" :model="fields" :rules="rules" label-position="top" :disabled="locked || loading">
      <ElFormItem label="集合名称" prop="name"><ElInput v-model="fields.name" maxlength="200" /></ElFormItem>
      <ElFormItem label="排序" prop="orderNum"><ElInputNumber v-model="fields.orderNum" :precision="0" :min="-2147483648" :max="2147483647" /></ElFormItem>
      <template v-if="target">
        <ElFormItem label="说明" prop="description"><ElInput v-model="fields.description" type="textarea" maxlength="2000" /></ElFormItem>
        <ElFormItem label="颜色（可留空）" prop="color"><ElInput v-model="fields.color" placeholder="#rrggbb" maxlength="7" /></ElFormItem>
      </template>
    </ElForm>
    <template #footer>
      <Button v-if="editing" variant="ghost" :disabled="locked" @click="back">返回集合列表</Button>
      <Button v-if="editing && conflict" variant="outline" :disabled="locked || loading" @click="reloadEditor">重新载入最新版本</Button>
      <Button v-if="editing && !uncertain" :disabled="saving || loading || conflict" @click="submit">保存集合</Button>
      <Button v-if="uncertain" :disabled="saving" @click="retry">{{ saving ? '正在处理…' : '重试同一请求' }}</Button>
      <Button variant="ghost" :disabled="locked" @click="close">关闭</Button>
    </template>
  </ElDialog>
</template>
<style scoped>
.collection-controls { display: flex; align-items: center; gap: 8px; }
.collection-controls :deep(.el-select) { width: 200px; }
</style>
