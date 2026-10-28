<script setup lang="ts">
import { IconSun, IconMoon } from '@tabler/icons-vue'
import { storeToRefs } from 'pinia'
import { useThemeStore } from '@/stores/theme'
import Button from '@/components/ui/Button.vue'
const store = useThemeStore()
const { theme } = storeToRefs(store)
</script>
<template>
  <Button
    type="button"
    variant="ghost"
    class="icon-button"
    :aria-label="theme === 'dark' ? '切换到亮色主题' : '切换到暗黑主题'"
    :title="theme === 'dark' ? '切换到亮色主题' : '切换到暗黑主题'"
    @click="store.toggle"
    ><IconSun v-if="theme === 'dark'" :size="20" /><IconMoon v-else :size="20"
  /></Button>
</template>
