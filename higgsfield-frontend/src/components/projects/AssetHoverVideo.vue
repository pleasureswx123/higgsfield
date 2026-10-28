<script setup lang="ts">
import ReferenceThumbnail from './ReferenceThumbnail.vue'
import { IconPlayerPlayFilled } from '@tabler/icons-vue'
import { useAssetHoverVideo } from '@/composables/useAssetHoverVideo'
const props = defineProps<{ versionId: string; name: string; enabled: boolean }>()
const { url, start, stop } = useAssetHoverVideo(() => props.versionId, () => props.enabled)
defineExpose({ start, stop })
</script>
<template>
  <ReferenceThumbnail :version-id="versionId" :alt="name" fill passive />
  <video v-if="url" class="asset-hover-video" :src="url" autoplay muted loop playsinline aria-label="视频静音预播" />
  <span v-if="!url" class="asset-video-play" aria-hidden="true"><IconPlayerPlayFilled :size="30" /></span>
</template>
