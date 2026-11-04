<script setup lang="ts">
import { ref, computed } from 'vue'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
const props = withDefaults(defineProps<{ visible?: boolean; disabled?: boolean; width?: number; placement?: string; popperClass?: string; trigger?: string; showArrow?: boolean }>(), { visible: undefined, width: 260, placement: 'bottom' })
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()
const localOpen = ref(false)
const open = computed(() => !props.disabled && (props.visible ?? localOpen.value))
function update(value: boolean) { localOpen.value = value; emit('update:visible', value) }
</script>
<template>
  <Popover :open="open" @update:open="update">
    <PopoverTrigger as-child :disabled="disabled"><slot name="reference" /></PopoverTrigger>
    <PopoverContent :side="placement.startsWith('top') ? 'top' : 'bottom'" :align="placement.endsWith('start') ? 'start' : placement.endsWith('end') ? 'end' : 'center'" :class="['studio-popover', popperClass]" :style="{ width: `${width}px`, maxWidth: 'calc(100vw - 24px)' }"><slot /></PopoverContent>
  </Popover>
</template>
