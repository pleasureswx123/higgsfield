<script setup lang="ts">
import { computed, ref } from 'vue'
import { IconCopy, IconCheck } from '@tabler/icons-vue'
import type { ElementRecord } from '@/api/elements'
import { useElementCellEdit } from '@/composables/useElementCellEdit'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const props = defineProps<{ row: ElementRecord; field?: 'alias' | 'label'; canEdit?: boolean; disabled?: boolean }>()
const emit = defineEmits<{ saved: [row: ElementRecord] }>()
const { saving, error, saveFields } = useElementCellEdit()
const isVersion = computed(() => props.field === 'label')
const fieldName = computed(() => isVersion.value ? '版本' : '元素 ID')
const currentValue = computed(() => isVersion.value ? props.row.label || '' : props.row.alias)
const trigger = ref<HTMLButtonElement>()
const open = ref(false)
const draft = ref('')
const input = ref<HTMLInputElement>()
const height = ref(0)
const hovered = ref(false)
const copied = ref(false)
const pointer = ref({ x: 0, y: 0 })
const editable = computed(() => !props.disabled && (props.row.allowedActions ? props.row.allowedActions.includes('element:edit') : props.canEdit))
function move(event: MouseEvent) {
  pointer.value = { x: event.clientX, y: event.clientY - 36 }
  height.value = (event.currentTarget as HTMLElement).offsetHeight
}
async function commit() {
  if (saving.value) return
  const alias = draft.value.trim()
  if ((!isVersion.value && !alias) || /[\x00-\x1f\x7f]/.test(alias)) { error.value = `请输入有效的${fieldName.value}`; return }
  if (alias === currentValue.value) { open.value = false; return }
  const updated = await saveFields(props.row, isVersion.value ? { label: alias } : { alias })
  if (updated) { emit('saved', updated); open.value = false }
}
function changeOpen(value: boolean) {
  if (value) { draft.value = currentValue.value; error.value = ''; open.value = true }
  else void commit()
}
function cancel(event: Event) { event.preventDefault(); if (!saving.value) open.value = false }
function focusInput(event: Event) { event.preventDefault(); input.value?.focus({ preventScroll: true }); input.value?.select() }
async function copy() {
  try { await navigator.clipboard.writeText(`@${props.row.alias}`); copied.value = true }
  catch { error.value = '复制失败，请重试' }
}
</script>

<template>
  <div class="alias-cell" @mouseenter="hovered = true; copied = false; move($event)" @mousemove="move" @mouseleave="hovered = false">
    <Popover :open="open" :modal="false" @update:open="changeOpen">
      <PopoverTrigger as-child>
        <button ref="trigger" type="button" class="alias-cell-trigger" :class="{ 'version-cell-trigger': isVersion }" :disabled="!editable || saving" :aria-label="`编辑 ${row.name} 的${fieldName}`" @focus="height = ($event.currentTarget as HTMLElement).offsetHeight"><span :class="{ muted: isVersion && !currentValue }">{{ isVersion ? currentValue || '—' : `@${row.alias}` }}</span></button>
      </PopoverTrigger>
      <PopoverContent side="bottom" align="start" :side-offset="-height" class="alias-cell-editor" @open-auto-focus="focusInput" @close-auto-focus.prevent="trigger?.focus({ preventScroll: true })" @escape-key-down="cancel" @interact-outside.prevent="commit">
        <div class="alias-input-wrap"><span v-if="!isVersion" aria-hidden="true">@</span><input ref="input" v-model="draft" :aria-label="fieldName" :placeholder="isVersion ? '添加版本' : undefined" maxlength="100" :disabled="saving" :aria-invalid="Boolean(error)" @keydown.enter.prevent="!$event.isComposing && commit()" /></div>
        <p v-if="error" role="alert" class="alias-error">{{ error }}</p>
      </PopoverContent>
    </Popover>
    <button v-if="!isVersion" type="button" class="alias-copy" :aria-label="copied ? '已复制元素 ID' : '复制元素 ID'" @click.stop="copy"><IconCheck v-if="copied" :size="16" /><IconCopy v-else :size="16" /></button>
  </div>
  <Teleport to="body"><span v-if="hovered && editable && !open && !saving" class="alias-hover-hint" :style="{ left: `${pointer.x}px`, top: `${pointer.y}px` }">点击编辑</span></Teleport>
</template>

<style scoped>
.alias-cell { position:absolute; inset:0; }
.alias-cell-trigger { width:100%; height:100%; display:flex; align-items:flex-start; padding:10px 36px 10px 12px; border:0; background:transparent; color:var(--foreground); font:inherit; text-align:left; align-content:start; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; cursor:text; }
.version-cell-trigger { padding-right:12px; }
.alias-cell-trigger > span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.alias-cell-trigger:disabled { cursor:default; opacity:1; }
.alias-cell-trigger:focus,.alias-cell-trigger:focus-visible { outline:none; box-shadow:none; }
.alias-copy { position:absolute; right:8px; top:10px; padding:2px; background:transparent; border:0; color:var(--muted-foreground); opacity:0; cursor:pointer; }
.alias-cell:hover .alias-copy,.alias-cell:focus-within .alias-copy { opacity:1; }
.alias-copy:hover { color:var(--foreground); }
:global(.alias-cell-editor) { width:280px; padding:8px; border:0; background:var(--surface); outline:none; font-size:12px; line-height:1.5; }
.alias-input-wrap { display:flex; align-items:center; gap:8px; border:1px solid var(--border); border-radius:10px; background:var(--surface-hover); padding:10px 12px; color:var(--muted-foreground); }
.alias-input-wrap input { width:100%; min-width:0; padding:0; border:0; outline:0; background:transparent; color:var(--foreground); font:inherit; }
.alias-error { margin:6px 0 0; color:var(--el-color-danger); font-size:12px; }
.alias-hover-hint { position:fixed; z-index:100; transform:translateX(-50%); pointer-events:none; padding:5px 12px; border:1px solid var(--border); border-radius:12px; background:var(--surface); color:var(--foreground); box-shadow:0 2px 6px #0003; font-size:12px; white-space:nowrap; }
</style>
