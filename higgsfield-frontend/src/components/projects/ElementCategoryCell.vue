<script setup lang="ts">
import { IconCheck } from '@tabler/icons-vue'
import { computed, ref, watch } from 'vue'
import { useElementMemberOptions } from '@/composables/useElementMemberOptions'
import type { ElementCategory, ElementRecord, WorkStatus } from '@/api/elements'
import { useElementCellEdit } from '@/composables/useElementCellEdit'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '@/components/ui/dropdown-menu'

const props = defineProps<{ row: ElementRecord; field?: 'category' | 'performer' | 'status'; canReview?: boolean; canEdit?: boolean; disabled?: boolean }>()
const emit = defineEmits<{ saved: [row: ElementRecord] }>()
const names = { character: '角色', scene: '场景', prop: '道具', other: '其他' }
const statuses = { none: '无状态', working: '进行中', review: '待审核', approved: '已通过', rejected: '已驳回' }
const isStatus = computed(() => props.field === 'status')
const isPerformer = computed(() => props.field === 'performer')
const fieldName = computed(() => isStatus.value ? '状态' : isPerformer.value ? '负责人' : '分类')
const memberOptions = useElementMemberOptions()
const options = computed(() => isStatus.value ? Object.entries(statuses).map(([value, label]) => ({ value, label })) : isPerformer.value ? [{ value: '', label: '未分配' }, ...memberOptions.members.value.map(member => ({ value: member.userId, label: member.displayName }))] : Object.entries(names).map(([value, label]) => ({ value, label })))
const currentLabel = computed(() => isStatus.value ? statuses[props.row.workStatus] : isPerformer.value ? props.row.performerName || (props.row.performerId ? '成员 ' + props.row.performerId : '未分配') : names[props.row.category] || '空')
const trigger = ref<HTMLButtonElement>()
const open = ref(false)
watch(open, value => { if (value && isPerformer.value) void memberOptions.load(props.row.projectId) })
const hovered = ref(false)
const pointer = ref({ x: 0, y: 0 })
const height = ref(0)
const { saving, error, save, saveFields } = useElementCellEdit()
const editable = computed(() => !props.disabled && (props.row.allowedActions ? props.row.allowedActions.includes('element:edit') : props.canEdit) && (!isStatus.value || (props.row.allowedActions ? props.row.allowedActions.includes('content:review') : props.canReview)))
function move(event: MouseEvent) {
  pointer.value = { x: event.clientX, y: event.clientY - 36 }
  height.value = (event.currentTarget as HTMLElement).offsetHeight
}
async function select(value: string) {
  if (isPerformer.value && (value || null) === props.row.performerId) return
  if (isStatus.value && value === props.row.workStatus) return
  const updated = isStatus.value ? await saveFields(props.row, { workStatus: value as WorkStatus }) : isPerformer.value ? await saveFields(props.row, { performerId: value || null }) : await save(props.row, value as ElementCategory)
  if (updated) emit('saved', updated)
}
</script>

<template>
  <DropdownMenu v-model:open="open" :modal="false">
    <DropdownMenuTrigger as-child>
      <button ref="trigger" type="button" class="category-cell-button" :disabled="!editable || saving" :aria-label="`修改 ${row.name} 的${fieldName}`" :aria-busy="saving" @mouseenter="hovered = true; move($event)" @mousemove="move" @mouseleave="hovered = false" @focus="height = ($event.currentTarget as HTMLElement).offsetHeight">
        <span v-if="isStatus" class="element-status-dot" :class="`status-${row.workStatus}`" aria-hidden="true" />
        <span :class="{ muted: !row.category }">{{ saving ? '保存中…' : currentLabel }}</span>
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" side="bottom" :side-offset="-height" class="category-cell-menu" @close-auto-focus.prevent="trigger?.focus({ preventScroll: true })">
      <div class="category-menu-label">选择{{ fieldName }}</div>
      <div v-if="isPerformer && memberOptions.loading.value" class="category-menu-label" role="status">加载中…</div>
      <div v-else-if="isPerformer && memberOptions.error.value" class="category-menu-label" role="alert">{{ memberOptions.error.value }}<button type="button" @click="memberOptions.load(row.projectId)">重试</button></div>
      <DropdownMenuItem v-for="option in options" :key="option.value" :class="{ 'status-option-selected': isStatus && option.value === row.workStatus }" :disabled="saving || (isPerformer && (memberOptions.loading.value || Boolean(memberOptions.error.value)))" @select="select(option.value)"><span v-if="isStatus" class="element-status-dot" :class="`status-${option.value}`" aria-hidden="true" />{{ option.label }}<IconCheck v-if="isStatus && option.value === row.workStatus" class="status-check" :size="14" /></DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
  <Teleport to="body"><span v-if="hovered && editable && !open && !saving" class="category-hover-hint" :style="{ left: `${pointer.x}px`, top: `${pointer.y}px` }">点击修改</span></Teleport>
  <span v-if="error" role="alert" class="category-save-error">{{ error }}</span>
</template>

<style scoped>
.category-cell-button { position:absolute; inset:0; width:100%; height:100%; display:flex; gap:8px; align-items:flex-start; padding:10px 12px; border:0; background:transparent; color:var(--foreground); text-align:left; cursor:pointer; font:inherit; }
.category-cell-button:disabled { cursor:default; opacity:1; }
.category-cell-button:focus,.category-cell-button:focus-visible { outline:none; box-shadow:none; }
.category-cell-button:focus-visible { background:var(--surface-hover); }
:global(.studio-action-menu.category-cell-menu) { width:240px; padding:10px; background:var(--surface-raised); }
.category-menu-label { padding:8px 10px 16px; color:var(--muted-foreground); font-size:12px; }
:global(.studio-action-menu.category-cell-menu [role=menuitem]) { padding:12px 10px; border-radius:9px; }
:global(.studio-action-menu.category-cell-menu [data-highlighted]) { background:var(--surface-hover); color:var(--foreground); }
.category-hover-hint { position:fixed; z-index:100; transform:translateX(-50%); pointer-events:none; padding:5px 12px; border:1px solid var(--border); border-radius:12px; background:var(--surface); color:var(--foreground); box-shadow:0 2px 6px #0003; font-size:12px; white-space:nowrap; }
.category-save-error { position:relative; display:block; margin-top:26px; color:var(--el-color-danger); font-size:12px; overflow-wrap:anywhere; }
.element-status-dot { display:inline-block; flex:0 0 12px; width:12px; height:12px; border-radius:50%; background:var(--element-status-color); }
.category-cell-button > .element-status-dot { margin-top:3px; }
.status-none { border:2px dotted var(--muted-foreground); background:transparent; }
.status-working { --element-status-color:#399af5; }
.status-review { --element-status-color:#f58a00; }
.status-approved { --element-status-color:#c6f000; }
.status-rejected { --element-status-color:#ed4145; }
.status-check { margin-left:auto; }
:global(.studio-action-menu.category-cell-menu .status-option-selected) { background:var(--surface-hover); }
</style>
