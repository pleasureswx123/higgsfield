<script setup lang="ts">
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableHeader, TableHead, TableBody, TableRow, TableCell } from '@/components/ui/table'
import Button from '@/components/ui/Button.vue'
import { Checkbox } from '@/components/ui/checkbox'
import { useProjectTrash } from '@/composables/useProjectTrash'
import { formatProjectDate } from '@/utils/projects'
const props = defineProps<{ projectId: string; actions: string[]; visible: boolean; refreshRelated: () => Promise<void> }>()
const { category, kinds, shownKinds, rows, total, hasMore, errors, loading, batch, load, refresh, restore } = useProjectTrash(props.projectId, () => props.actions, () => props.visible, () => props.refreshRelated())
const labels = { asset: '素材', element: '元素', folder: '文件夹' }
</script>
<template>
  <section class="project-trash" aria-label="项目回收站">
    <header><div><h2>回收站</h2><p>当前项目已删除的内容，可在删除后 30 天内恢复。</p></div><Button variant="outline" :disabled="loading || batch.pending.value" @click="refresh()">刷新</Button></header>
    <Tabs v-model="category"><TabsList class="studio-tabs studio-pill-tabs" aria-label="回收内容分类"><TabsTrigger value="all" :disabled="batch.pending.value">全部</TabsTrigger><TabsTrigger v-for="kind in kinds" :key="kind" :value="kind" :disabled="batch.pending.value">{{ labels[kind] }}</TabsTrigger></TabsList></Tabs>
    <div class="trash-actions"><Button :disabled="loading || batch.pending.value || !batch.selected.value.length" @click="batch.restore">{{ batch.pending.value ? '正在恢复…' : `恢复所选（${batch.selected.value.length}）` }}</Button><span>已显示 {{ rows.length }} / {{ total }} 条</span></div>
    <template v-for="kind in shownKinds" :key="kind"><p v-if="errors[kind]" role="alert">{{ labels[kind] }}：{{ errors[kind] }}</p></template>
    <p v-if="batch.message.value" role="status">{{ batch.message.value }}</p>
    <div v-if="batch.uncertainCount.value" role="status"><span>有 {{ batch.uncertainCount.value }} 项恢复结果尚未确认。</span><Button variant="outline" :disabled="loading || batch.pending.value" @click="batch.retryUncertain">重试确认原请求</Button></div>
    <Table><TableHeader><TableRow><TableHead class="selection-column"><Checkbox :model-value="batch.allSelected.value ? true : batch.selected.value.length > 0 ? 'indeterminate' : false" :disabled="loading || batch.pending.value || !rows.some(item => item.canRestore)" aria-label="选择当前列表中可恢复的内容" title="选择当前列表中可恢复的内容" @update:model-value="batch.selectAll($event === true)" /></TableHead><TableHead>名称</TableHead><TableHead>类型</TableHead><TableHead>删除时间</TableHead><TableHead>恢复期限</TableHead><TableHead class="action-column">操作</TableHead></TableRow></TableHeader>
      <TableBody><TableRow v-for="item in rows" :key="item.id"><TableCell><Checkbox :model-value="batch.selected.value.includes(item.id)" :aria-label="`选择 ${item.name}`" :disabled="loading || batch.pending.value || !item.canRestore" @update:model-value="batch.toggle(item.id, $event === true)" /></TableCell><TableCell class="trash-name">{{ item.name }}</TableCell><TableCell>{{ labels[item.kind] }}</TableCell><TableCell>{{ formatProjectDate(item.deletedTime) }}</TableCell><TableCell>{{ formatProjectDate(item.restoreUntil) }}</TableCell><TableCell><Button variant="ghost" :disabled="loading || batch.pending.value || !item.canRestore" @click="restore(item)">{{ item.canRestore ? '恢复' : '不可恢复' }}</Button></TableCell></TableRow></TableBody>
    </Table>
    <p v-if="loading" role="status">正在加载…</p><p v-else-if="!rows.length && !shownKinds.some(kind => errors[kind])" class="trash-empty">{{ kinds.length ? '暂无已删除的内容' : '暂无查看回收站的权限' }}</p>
    <Button v-if="hasMore" variant="outline" :disabled="loading || batch.pending.value" @click="load(true)">加载更多</Button>
  </section>
</template>
<style scoped>
.project-trash { display:flex; flex-direction:column; gap:16px; padding:8px 0; }
header, .trash-actions { display:flex; align-items:center; gap:16px; }
header { justify-content:space-between; }
h2 { margin:0 0 8px; font-size:20px; }
header p, .trash-actions span { margin:0; color:var(--muted-foreground); font-size:12px; }
.trash-actions { flex-wrap:wrap; }
.trash-actions span { margin-left:auto; }
.selection-column { width:40px; }
.action-column { width:90px; }
.trash-name { max-width:280px; overflow-wrap:anywhere; }
.trash-empty { text-align:center; padding:60px 0; color:var(--muted-foreground); }
.project-trash :deep(table) { width:100%; border-collapse:collapse; font-size:12px; }
.project-trash :deep(th) { background:var(--surface); color:var(--muted-foreground); font-weight:500; }
.project-trash :deep(th), .project-trash :deep(td) { padding:10px 12px; text-align:left; border-bottom:1px solid var(--border); }
.project-trash :deep(tbody tr:hover) { background:var(--surface-hover); }
</style>
