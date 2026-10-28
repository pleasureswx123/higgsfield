<script setup lang="ts">
import { onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import { IconDots } from '@tabler/icons-vue'

const props = defineProps<{ compact?: boolean; name: string }>()
const menu = ref<HTMLDetailsElement>()
function close() {
  if (props.compact && menu.value) menu.value.open = false
}
function outside(event: PointerEvent) {
  if (menu.value && !event.composedPath().includes(menu.value)) close()
}
function action(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (target.closest('button:not(:disabled)')) close()
}
function escape(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !props.compact || !menu.value?.open) return
  const focusedInside = menu.value.contains(document.activeElement)
  close()
  if (focusedInside) menu.value.querySelector('summary')?.focus()
}
onMounted(() => {
  document.addEventListener('pointerdown', outside, true)
  document.addEventListener('keydown', escape)
})
onDeactivated(close)
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside, true)
  document.removeEventListener('keydown', escape)
})
</script>

<template>
  <details ref="menu" class="asset-card-actions" :open="!compact">
    <summary :aria-label="`素材操作 ${name}`"><IconDots :size="16" /></summary>
    <div class="asset-card-action-menu" @click="action"><slot /></div>
  </details>
</template>
