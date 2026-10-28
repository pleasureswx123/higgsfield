<script setup lang="ts">
import type { ProjectViewSettings } from '@/api/viewPreferences'
import { useProjectViewPreference } from '@/composables/useProjectViewPreference'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ settings: ProjectViewSettings }>()
const emit = defineEmits<{ restore: [settings: ProjectViewSettings] }>()
const { ready, loading, saving, uncertain, locked, error, notice, load, save } = useProjectViewPreference(() => props.settings, value => emit('restore', value))
</script>
<template>
  <div class="view-preference-controls">
    <Button variant="ghost" :disabled="locked || loading" @click="load(true)">恢复已保存视图</Button>
    <Button v-if="!ready && !locked" variant="ghost" :disabled="loading" @click="load()">重新读取视图版本</Button>
    <Button variant="ghost" :disabled="!ready || loading || saving" @click="save">{{ saving ? '正在保存…' : uncertain ? '重试同一请求' : '保存当前视图' }}</Button>
    <span v-if="uncertain && !saving" role="status">保存结果未确认，请重试原请求。</span>
    <span v-if="error" role="alert">{{ error }}</span><span v-else-if="notice" role="status">{{ notice }}</span>
  </div>
</template>
<style scoped>
.view-preference-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; color: var(--muted-foreground); font-size: 13px; }
</style>
