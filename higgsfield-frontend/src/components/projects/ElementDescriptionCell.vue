<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ElementRecord } from '@/api/elements'
import { useElementCellEdit } from '@/composables/useElementCellEdit'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const props = defineProps<{ row: ElementRecord; canEdit?: boolean; disabled?: boolean }>()
const emit = defineEmits<{ saved: [row: ElementRecord] }>()
const { saving, error, saveFields } = useElementCellEdit()
const trigger = ref<HTMLButtonElement>()
const open = ref(false)
const draft = ref('')
const input = ref<HTMLTextAreaElement>()
const height = ref(0)
const hovered = ref(false)
const pointer = ref({ x: 0, y: 0 })
const editable = computed(() => !props.disabled && (props.row.allowedActions ? props.row.allowedActions.includes('element:edit') : props.canEdit))
function move(event: MouseEvent) {
  pointer.value = { x: event.clientX, y: event.clientY - 36 }
  height.value = (event.currentTarget as HTMLElement).offsetHeight
}
async function commit() {
  if (saving.value) return
  if (draft.value === (props.row.description || '')) { open.value = false; return }
  const updated = await saveFields(props.row, { description: draft.value })
  if (updated) { emit('saved', updated); open.value = false }
}
function changeOpen(value: boolean) {
  if (value) { draft.value = props.row.description || ''; error.value = ''; open.value = true }
  else void commit()
}
function cancel(event: Event) { event.preventDefault(); if (!saving.value) open.value = false }
function focusInput(event: Event) { event.preventDefault(); input.value?.focus({ preventScroll: true }) }
</script>

<template>
  <Popover :open="open" :modal="false" @update:open="changeOpen">
    <PopoverTrigger as-child>
      <button ref="trigger" type="button" class="description-cell-trigger" :disabled="!editable || saving" :aria-label="`编辑 ${row.name} 的描述`" :aria-busy="saving" @mouseenter="hovered = true; move($event)" @mousemove="move" @mouseleave="hovered = false" @focus="height = ($event.currentTarget as HTMLElement).offsetHeight">
        <span :class="{ muted: !row.description }">{{ row.description || '空' }}</span>
      </button>
    </PopoverTrigger>
    <PopoverContent side="bottom" align="start" :side-offset="-height" class="description-cell-editor" @open-auto-focus="focusInput" @close-auto-focus.prevent="trigger?.focus({ preventScroll: true })" @escape-key-down="cancel" @interact-outside.prevent="commit">
      <textarea class="description-input" ref="input" v-model="draft" aria-label="元素描述" placeholder="输入描述" :disabled="saving" :aria-invalid="Boolean(error)" />
      <p v-if="error" role="alert" class="description-save-error">{{ error }}</p>
    </PopoverContent>
  </Popover>
  <Teleport to="body"><span v-if="hovered && editable && !open && !saving" class="description-hover-hint" :style="{ left: `${pointer.x}px`, top: `${pointer.y}px` }">点击编辑</span></Teleport>
</template>

<style scoped>
.description-cell-trigger { position:absolute; inset:0; width:100%; height:100%; display:block; padding:10px 12px; border:0; background:transparent; color:var(--foreground); font:inherit; text-align:left; cursor:text; overflow-y:auto; overscroll-behavior:contain; scrollbar-width:thin; }
.description-cell-trigger > span { display:block; position:absolute; top:10px; left:12px; right:12px; padding-bottom:10px; white-space:pre-wrap; overflow-wrap:anywhere; }
.description-cell-trigger:disabled { cursor:default; opacity:1; }
.description-cell-trigger:focus,.description-cell-trigger:focus-visible { outline:none; box-shadow:none; }
:global(.description-cell-editor) { width:340px; padding:8px; border:0; background:var(--surface); outline:none; font-size:12px; line-height:1.5; }
.description-input { display:block; box-sizing:border-box; width:100%; height:148px; padding:12px; resize:none; border:1px solid var(--border); border-radius:10px; outline:none; background:var(--surface-hover); color:var(--foreground); font:inherit; white-space:pre-wrap; overflow-wrap:anywhere; overflow-y:auto; overscroll-behavior:contain; scrollbar-width:thin; }
.description-input::placeholder { color:var(--muted-foreground); }
.description-save-error { margin:6px 0 0; color:var(--el-color-danger); font-size:12px; }
.description-hover-hint { position:fixed; z-index:100; transform:translateX(-50%); pointer-events:none; padding:5px 12px; border:1px solid var(--border); border-radius:12px; background:var(--surface); color:var(--foreground); box-shadow:0 2px 6px #0003; font-size:12px; white-space:nowrap; }
</style>
