<script setup lang="ts">
import { computed } from 'vue'
import type { GenerationSnapshot } from '@/api/generations'
import { generationGuidance } from '@/utils/generationGuidance'

const props = defineProps<{ detail: GenerationSnapshot }>()
const items = computed(() => generationGuidance(props.detail))
</script>

<template>
  <aside v-if="items.length || detail.diagnostic" class="generation-guidance" aria-label="任务状态说明与处理方式">
    <section v-for="item in items" :key="item.code">
      <strong>{{ item.title }}</strong>
      <p>{{ item.message }}</p>
    </section>
    <section v-if="detail.diagnostic">
      <strong>已记录原因 · {{ { prepare: '准备阶段', submit: '提交阶段', poll: '查询阶段' }[detail.diagnostic.phase] }}</strong>
      <p>{{ detail.diagnostic.message }}</p>
      <p class="muted">诊断代码：{{ detail.diagnostic.code }}。此说明不代表费用已结算。</p>
    </section>
  </aside>
</template>

<style scoped>
.generation-guidance { margin: 12px 0; padding: 12px 16px; border: 1px solid var(--border); border-radius: 12px; background: var(--muted); color: var(--foreground); }
section + section { margin-top: 12px; }
p { margin: 6px 0 0; line-height: 1.6; }
</style>
