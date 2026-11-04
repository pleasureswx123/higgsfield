<script setup lang="ts">
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
defineOptions({ inheritAttrs: false })
const model = defineModel<string>({ default: '' })
defineProps<{ options: { value: string; label: string }[]; disabled?: boolean; placeholder?: string }>()
const emit = defineEmits<{ change: [value: string] }>()
// Reka Select 不允许空选项，界面哨兵值只在组件内部使用。
const empty = '__studio_all__'
function update(value: unknown) {
  const next = value === empty ? '' : String(value ?? '')
  model.value = next
  emit('change', next)
}
</script>
<template>
  <Select :model-value="model || empty" :disabled="disabled" @update:model-value="update">
    <SelectTrigger v-bind="$attrs" class="studio-select"><SelectValue :placeholder="placeholder" /></SelectTrigger>
    <SelectContent class="studio-select-content"><SelectItem v-for="option in options" :key="option.value" :value="option.value || empty">{{ option.label }}</SelectItem></SelectContent>
  </Select>
</template>
