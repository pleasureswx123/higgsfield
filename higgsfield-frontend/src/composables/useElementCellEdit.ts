import { ref } from 'vue'
import { readElement, saveElement, type ElementCategory, type ElementRecord } from '@/api/elements'

export function useElementCellEdit() {
  const saving = ref(false)
  const error = ref('')
  async function saveFields(row: ElementRecord, patch: Partial<Pick<ElementRecord, 'category' | 'alias' | 'description' | 'label' | 'performerId' | 'workStatus'>>) {
    if (saving.value) return false
    saving.value = true
    error.value = ''
    try {
      // 读取最新完整内容，仅替换当前字段，避免覆盖图片和自定义属性。
      const { data } = await readElement(row.id)
      if (!data.element.allowedActions?.includes('element:edit')) throw new Error('你没有编辑此元素的权限')
      if (patch.workStatus !== undefined && !data.element.allowedActions?.includes('content:review')) throw new Error('你没有修改状态的权限')
      if (data.element.revision !== row.revision) throw new Error('元素已被更新，请刷新列表后重试')
      const { element, currentRevision } = data
      const result = await saveElement(row.id, element.revision, {
        name: element.name, alias: patch.alias ?? element.alias, category: patch.category ?? element.category,
        workStatus: patch.workStatus ?? element.workStatus, performerId: patch.performerId !== undefined ? patch.performerId : element.performerId,
        description: patch.description ?? currentRevision.description, label: patch.label ?? currentRevision.label,
        media: currentRevision.media, propertyValues: currentRevision.propertyValues,
        isFictionalPerson: currentRevision.isFictionalPerson,
      }, crypto.randomUUID())
      return { ...result.data.element, description: result.data.currentRevision.description, label: result.data.currentRevision.label, media: result.data.currentRevision.media }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '保存失败，请刷新列表确认后重试'
      return false
    } finally {
      saving.value = false
    }
  }
  function save(row: ElementRecord, category: ElementCategory) {
    if (category === row.category) return Promise.resolve(false as const)
    return saveFields(row, { category })
  }
  return { saving, error, save, saveFields }
}
