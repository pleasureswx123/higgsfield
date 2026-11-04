<script setup lang="ts">
import { useId } from 'vue'

withDefaults(defineProps<{ size?: number }>(), { size: 24 })
const gradientId = `folder-front-${useId()}`
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 28 28" fill="none" aria-hidden="true" class="folder-volume-icon">
    <defs>
      <linearGradient :id="gradientId" x1="14" y1="9" x2="14" y2="25" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="var(--folder-highlight)" />
        <stop offset="0.38" stop-color="currentColor" />
        <stop offset="1" stop-color="var(--folder-shadow)" />
      </linearGradient>
    </defs>
    <path d="M3 9V6.5A2 2 0 0 1 5 4.5h6l2.2 2H23a2 2 0 0 1 2 2V21H3Z" fill="currentColor" />
    <path d="M3 9V6.5A2 2 0 0 1 5 4.5h6l2.2 2H23a2 2 0 0 1 2 2V21H3Z" fill="black" opacity=".22" />
    <rect x="4" y="8" width="20" height="12" rx="1" fill="var(--folder-highlight)" />
    <rect x="2" y="10" width="24" height="15" rx="2.5" :fill="`url(#${gradientId})`" />
    <path d="M4.5 10.5h19" stroke="white" stroke-opacity=".45" stroke-linecap="round" />
    <path d="M4.5 24.5h19" stroke="black" stroke-opacity=".12" stroke-linecap="round" />
  </svg>
</template>

<style scoped>
.folder-volume-icon { flex-shrink:0; --folder-highlight:color-mix(in srgb, currentColor 45%, white); --folder-shadow:color-mix(in srgb, currentColor 88%, black); filter:drop-shadow(0 1px 1px #0002); }
</style>
