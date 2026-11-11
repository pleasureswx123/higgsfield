<script setup lang="ts">
import type { LibraryViewSettings } from '@/api/viewPreferences'
import { useLibraryViewPreference } from '@/composables/useLibraryViewPreference'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ projectId: string; settings: LibraryViewSettings }>()
const emit = defineEmits<{ restore: [settings: LibraryViewSettings] }>()
const { ready, loading, saving, uncertain, locked, error, load, save } = useLibraryViewPreference(
  props.projectId, () => props.settings, value => emit('restore', value))
</script>
<template>
  <div class="library-view-preference">
    <Button variant="ghost" class="library-neutral-button" :disabled="locked || loading" @click="load(true)">恢复已保存设置</Button>
    <Button v-if="!ready && !locked" variant="outline" :disabled="loading" @click="load()">重新加载设置</Button>
    <Button variant="outline" :disabled="!ready || loading || saving" @click="save">{{ saving ? '正在保存…' : uncertain ? '重试保存' : '保存当前设置' }}</Button>
    <span v-if="error" role="alert">{{ error }}</span>
  </div>
</template>
