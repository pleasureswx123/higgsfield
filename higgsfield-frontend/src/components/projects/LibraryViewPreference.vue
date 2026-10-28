<script setup lang="ts">
import type { LibraryViewSettings } from '@/api/viewPreferences'
import { useLibraryViewPreference } from '@/composables/useLibraryViewPreference'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ projectId: string; settings: LibraryViewSettings }>()
const emit = defineEmits<{ restore: [settings: LibraryViewSettings] }>()
const { ready, loading, saving, uncertain, locked, error, notice, load, save } = useLibraryViewPreference(
  props.projectId, () => props.settings, value => emit('restore', value))
</script>
<template>
  <div class="asset-toolbar">
    <Button variant="ghost" :disabled="locked || loading" @click="load(true)">恢复素材视图</Button>
    <Button v-if="!ready && !locked" variant="ghost" :disabled="loading" @click="load()">重新读取视图版本</Button>
    <Button variant="ghost" :disabled="!ready || loading || saving" @click="save">{{ saving ? '正在保存…' : uncertain ? '重试同一请求' : '保存素材视图' }}</Button>
    <span v-if="error" role="alert">{{ error }}</span><span v-else-if="notice" role="status">{{ notice }}</span>
  </div>
</template>
