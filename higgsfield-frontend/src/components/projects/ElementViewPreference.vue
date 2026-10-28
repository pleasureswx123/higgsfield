<script setup lang="ts">
import type { ElementViewSettings } from '@/api/viewPreferences'
import { useElementViewPreference } from '@/composables/useElementViewPreference'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ projectId?: string; settings: ElementViewSettings }>()
const emit = defineEmits<{ restore: [settings: ElementViewSettings] }>()
const { ready, loading, saving, uncertain, locked, error, notice, load, save } = useElementViewPreference(
  props.projectId, () => props.settings, value => emit('restore', value))
</script>
<template>
  <div class="element-view-controls">
    <Button variant="ghost" :disabled="locked || loading" @click="load(true)">恢复元素视图</Button>
    <Button v-if="!ready && !locked" variant="ghost" :disabled="loading" @click="load()">重新读取视图版本</Button>
    <Button variant="ghost" :disabled="!ready || loading || saving" @click="save">{{ saving ? '正在保存…' : uncertain ? '重试同一请求' : '保存元素视图' }}</Button>
    <span v-if="error" role="alert">{{ error }}</span><span v-else-if="notice" role="status">{{ notice }}</span>
  </div>
</template>
<style scoped>
.element-view-controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; color: var(--muted-foreground); font-size: 13px; }
</style>
