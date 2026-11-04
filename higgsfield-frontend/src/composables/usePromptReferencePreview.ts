import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { readAssetVersion, type Asset } from '@/api/assets'
import type { DraftReference } from '@/api/creation'
import { useReferenceElementCreate } from './useReferenceElementCreate'

/** 行内引用的预览与现有元素创建流程共用固定素材版本。 */
export function usePromptReferencePreview(
  projectId: () => string,
  references: () => DraftReference[],
  disabled: () => boolean,
) {
  const anchor = shallowRef<HTMLElement>(),
    reference = shallowRef<DraftReference>()
  const label = ref(''),
    visible = ref(false),
    initialAsset = shallowRef<Asset>(),
    error = ref('')
  const creator = useReferenceElementCreate(projectId, () => !disabled())
  let timer: ReturnType<typeof setTimeout> | undefined, controller: AbortController | undefined
  function keep() {
    clearTimeout(timer)
  }
  function hide() {
    keep()
    timer = setTimeout(() => {
      visible.value = false
    }, 180)
  }
  function show(event: MouseEvent) {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-type="mention"]')
    if (!target) {
      hide()
      return
    }
    const item = references().find((value) => value.referenceKey === target.dataset.id)
    if (!item) return
    keep()
    reference.value = item
    anchor.value = target
    label.value = target.dataset.label || ''
    visible.value = true
  }
  async function saveAsElement() {
    const item = reference.value
    if (!item || item.elementRevisionId || disabled()) return
    controller?.abort()
    controller = new AbortController()
    const current = controller
    error.value = ''
    try {
      const result = await readAssetVersion(item.assetVersionId, current.signal)
      if (current.signal.aborted || disabled()) return
      initialAsset.value = result.data
      await creator.show()
      visible.value = false
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '无法读取素材'
    }
  }
  function reset() {
    keep()
    controller?.abort()
    visible.value = false
    creator.open.value = false
  }
  watch([projectId, disabled], reset)
  watch(
    references,
    () => {
      if (!references().some((item) => item.referenceKey === reference.value?.referenceKey))
        visible.value = false
    },
    { deep: true },
  )
  onBeforeUnmount(reset)
  return {
    anchor,
    reference,
    label,
    visible,
    initialAsset,
    error,
    creator,
    show,
    hide,
    keep,
    saveAsElement,
  }
}
