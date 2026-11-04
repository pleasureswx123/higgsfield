<script setup lang="ts">
import { Pagination, PaginationContent, PaginationItem, PaginationPrevious, PaginationNext, PaginationEllipsis } from '@/components/ui/pagination'
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-vue'
const page = defineModel<number>('currentPage', { default: 1 })
const emit = defineEmits<{ 'current-change': [value: number] }>()
function update(value: number) { page.value = value; emit('current-change', value) }
withDefaults(defineProps<{ total: number; pageSize?: number; disabled?: boolean; layout?: string }>(), { pageSize: 20, layout: 'total, prev, pager, next' })
</script>
<template>
  <Pagination :page="page" @update:page="update" :total="total" :items-per-page="pageSize" :sibling-count="1" show-edges :disabled="disabled" class="studio-pagination" aria-label="分页">
    <span v-if="layout.includes('total')" class="muted">共 {{ total }} 条</span>
    <PaginationContent v-slot="{ items }">
      <PaginationPrevious size="icon-sm" aria-label="上一页"><IconChevronLeft :size="14" /></PaginationPrevious>
      <template v-for="(item, index) in items" :key="index">
        <PaginationItem v-if="item.type === 'page'" :value="item.value" :aria-label="`第 ${item.value} 页`" :is-active="item.value === page" size="icon-sm">{{ item.value }}</PaginationItem>
        <PaginationEllipsis v-else />
      </template>
      <PaginationNext size="icon-sm" aria-label="下一页"><IconChevronRight :size="14" /></PaginationNext>
    </PaginationContent>
  </Pagination>
</template>
