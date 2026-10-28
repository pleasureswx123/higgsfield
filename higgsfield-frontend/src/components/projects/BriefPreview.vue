<script setup lang="ts">
import type { BriefBody, TextNode } from '@/api/projectWorkspace'
defineProps<{ body: BriefBody }>()
function safeHref(node: TextNode) {
  const value = node.marks.find((m) => m.type === 'link')?.href
  if (!value) return undefined
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password
      ? value
      : undefined
  } catch {
    return undefined
  }
}
</script>
<template>
  <div class="brief-preview">
    <p v-if="!body.content.length" class="muted">尚未填写项目简报。</p>
    <p v-for="(paragraph, index) in body.content" :key="index">
      <component
        :is="safeHref(node) ? 'a' : 'span'"
        v-for="(node, n) in paragraph.content"
        :key="n"
        :href="safeHref(node)"
        :target="safeHref(node) ? '_blank' : undefined"
        rel="noopener noreferrer"
        :class="{
          'text-bold': node.marks.some((m) => m.type === 'bold'),
          'text-italic': node.marks.some((m) => m.type === 'italic'),
        }"
        >{{ node.text }}</component
      >
    </p>
  </div>
</template>
