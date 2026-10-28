<script setup lang="ts">
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useThemeStore } from '@/stores/theme'
useThemeStore()
</script>
<template>
  <ElConfigProvider :locale="zhCn" :z-index="2000"><RouterView /></ElConfigProvider>
</template>
