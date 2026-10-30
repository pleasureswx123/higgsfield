<script setup lang="ts">
import { computed } from 'vue'
import type { ElementRecord } from '@/api/elements'
import { groupContentByDate, contentCardWidth } from '@/utils/contentView'
import ElementCollection from './ElementCollection.vue'
const props = defineProps<{ rows: ElementRecord[]; layout: 'grid' | 'board' | 'table'; cardSize: number; splitByDate: boolean; showProject?: boolean; selectable?: boolean; selected?: string[]; selectionDisabled?: boolean }>()
const emit = defineEmits<{ open: [element: ElementRecord]; select: [id: string, checked: boolean]; preview: [versionId: string] }>()
const groups = computed(() => groupContentByDate(props.rows, props.splitByDate))
</script>
<template>
  <div :style="{ '--element-card-width': `${contentCardWidth(cardSize)}px` }">
    <p v-if="splitByDate" class="muted">按上海日期分组，仅展示当前页元素。</p>
    <p v-if="splitByDate && !rows.length" class="muted">暂无匹配的元素。</p>
    <section v-for="group in groups" :key="group.key" class="element-date-group">
      <h3 v-if="splitByDate">{{ group.label }} <small class="muted">{{ group.rows.length }} 项</small></h3>
      <ElementCollection @preview="emit('preview', $event)" :rows="group.rows" :selectable="selectable" :selected="selected" :selection-disabled="selectionDisabled" @select="(id, checked) => emit('select', id, checked)" :layout="layout" :show-project="showProject" @open="emit('open', $event)" />
    </section>
  </div>
</template>
<style scoped>
.element-date-group + .element-date-group { margin-top: 24px; }
.element-date-group h3 { font-size: 14px; margin: 0 0 12px; }
</style>
