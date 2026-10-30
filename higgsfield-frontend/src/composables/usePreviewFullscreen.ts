import { onBeforeUnmount, onMounted, ref } from 'vue'

/** 浏览器全屏与页面最大化保持一致；宿主不支持全屏时保留页面内最大化。 */
export function usePreviewFullscreen(target: () => HTMLElement | null | undefined) {
  const expanded = ref(false)
  let fullscreenTarget: HTMLElement | undefined
  let disposed = false
  const sync = () => {
    if (fullscreenTarget && document.fullscreenElement !== fullscreenTarget) {
      fullscreenTarget = undefined
      expanded.value = false
    }
  }
  async function restore() {
    expanded.value = false
    if (fullscreenTarget && document.fullscreenElement === fullscreenTarget) {
      try { await document.exitFullscreen() } catch { /* 宿主退出失败时保留可操作界面。 */ }
    }
    fullscreenTarget = undefined
  }
  async function toggle() {
    if (expanded.value) { await restore(); return }
    const element = target()
    if (!element) return
    expanded.value = true
    if (!element.requestFullscreen || !document.fullscreenEnabled) return
    fullscreenTarget = element
    try {
      await element.requestFullscreen()
      if (disposed || !expanded.value) await restore()
    } catch {
      fullscreenTarget = undefined
    }
  }
  function escape(event: KeyboardEvent) {
    if (event.key === 'Escape' && expanded.value && !document.fullscreenElement) {
      event.preventDefault()
      event.stopImmediatePropagation()
      void restore()
    }
  }
  onMounted(() => {
    document.addEventListener('fullscreenchange', sync)
    document.addEventListener('keydown', escape, true)
  })
  onBeforeUnmount(() => {
    disposed = true
    document.removeEventListener('fullscreenchange', sync)
    document.removeEventListener('keydown', escape, true)
    void restore()
  })
  return { expanded, toggle, restore }
}
