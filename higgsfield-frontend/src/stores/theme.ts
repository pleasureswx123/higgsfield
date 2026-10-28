import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
export const useThemeStore = defineStore('studio-theme', () => {
  const theme = ref<'light' | 'dark'>(
    document.documentElement.classList.contains('dark') ? 'dark' : 'light',
  )
  watch(
    theme,
    (value) => {
      document.documentElement.classList.toggle('dark', value === 'dark')
      document.documentElement.style.colorScheme = value
      try {
        localStorage.setItem('higgsfield.theme', value)
      } catch {
        /* 隐私模式仍允许当前页面切换主题。 */
      }
    },
    { immediate: true },
  )
  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }
  return { theme, toggle }
})
