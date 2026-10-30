import { onBeforeUnmount, ref, watch } from 'vue'
import { readBrief } from '@/api/projectWorkspace'

/** 按当前项目授权打开已有元素编辑器。 */
export function useReferenceElementCreate(projectId: () => string, visible: () => boolean) {
  const open = ref(false), loading = ref(false), error = ref(''), actions = ref<string[]>([])
  let sequence = 0
  function reset() { sequence++; open.value = false; loading.value = false; actions.value = []; error.value = '' }
  async function show() {
    if (!visible() || loading.value) return
    const ticket = ++sequence
    loading.value = true; error.value = ''
    try {
      const result = await readBrief(projectId())
      if (ticket !== sequence || !visible()) return
      if (!result.data.allowedActions.includes('element:create')) throw new Error('当前项目没有创建元素权限')
      actions.value = result.data.allowedActions
      open.value = true
    } catch (cause) {
      if (ticket === sequence) error.value = cause instanceof Error ? cause.message : '无法读取项目权限'
    } finally { if (ticket === sequence) loading.value = false }
  }
  watch(() => [visible(), projectId()], reset)
  onBeforeUnmount(reset)
  return { open, loading, error, actions, show }
}
