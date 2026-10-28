<script setup lang="ts">
import { IconHeart, IconHeartFilled } from '@tabler/icons-vue'
import type { FavoriteTarget } from '@/api/favorites'
import { useFavoriteAction } from '@/composables/useFavoriteAction'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ target: FavoriteTarget; iconOnly?: boolean }>()
const { pending, saved, error, save } = useFavoriteAction(() => props.target)
</script>
<template>
  <span>
    <button v-if="iconOnly" type="button" class="asset-round-action" :disabled="pending || saved" :aria-label="saved ? '已收藏' : '收藏'" :title="saved ? '已收藏' : '收藏'" @click="save"><component :is="saved ? IconHeartFilled : IconHeart" :size="19" /></button>
    <Button v-else variant="ghost" :disabled="pending || saved" @click="save">{{
      pending ? '收藏中…' : saved ? '已收藏' : '收藏'
    }}</Button>
    <span v-if="error" class="project-error" role="alert">{{ error }}</span>
  </span>
</template>
