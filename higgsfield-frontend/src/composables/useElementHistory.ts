import { computed, onActivated, onDeactivated, onBeforeUnmount, ref, watch } from 'vue'
import { listRevisions, type ElementRevision } from '@/api/elements'
import { readMedia } from '@/api/assets'
import { useAuthStore } from '@/stores/auth'

export function useElementHistory(id: string, visible: () => boolean = () => true) {
  const auth = useAuthStore(), active = ref(visible())
  let mountedActive = true, alive = true
  const rows = ref<ElementRevision[]>([]),
    page = ref(1),
    total = ref(0),
    loading = ref(false),
    error = ref('')
  const selected = ref<ElementRevision>(),
    selectedVersion = ref(''),
    preview = ref(''),
    previewLoading = ref(false),
    previewError = ref('')
  const properties = computed(() => selected.value?.propertySnapshot || [])
  let listController: AbortController | undefined, mediaController: AbortController | undefined
  function clearMedia() {
    mediaController?.abort()
    if (preview.value) URL.revokeObjectURL(preview.value)
    preview.value = ''
    previewLoading.value = false
  }
  function choose(revision: ElementRevision) {
    if (!active.value || !auth.token || !alive) return
    selected.value = revision
    selectedVersion.value =
      revision.media.find((media) => media.isPrimary)?.assetVersionId ||
      revision.media[0]?.assetVersionId ||
      ''
  }
  async function load(preserveSelection = false) {
    if (!active.value || !auth.token || !alive) return
    listController?.abort()
    const controller = new AbortController()
    listController = controller
    loading.value = true
    error.value = ''
    try {
      const response = await listRevisions(id, page.value, controller.signal)
      if (!controller.signal.aborted) {
        rows.value = response.rows
        total.value = response.total
        const retained = preserveSelection && rows.value.find(item => item.id === selected.value?.id)
        if (retained) {
          selected.value = retained
          if (retained.media.some(item => item.assetVersionId === selectedVersion.value))
            void loadMedia(selectedVersion.value)
          else choose(retained)
        }
        else if (rows.value[0]) choose(rows.value[0])
        else {
          selected.value = undefined
          selectedVersion.value = ''
        }
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        rows.value = []
        selected.value = undefined
        selectedVersion.value = ''
        error.value = cause instanceof Error ? cause.message : '历史修订加载失败'
      }
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }
  async function loadMedia(version: string) {
    clearMedia()
    previewError.value = ''
    if (!version || !active.value || !auth.token || !alive) return
    const controller = new AbortController()
    mediaController = controller
    previewLoading.value = true
    try {
      const blob = await readMedia(version, false, controller.signal, () => {})
      if (!controller.signal.aborted) preview.value = URL.createObjectURL(blob)
    } catch (cause) {
      if (!controller.signal.aborted)
        previewError.value = cause instanceof Error ? cause.message : '历史图片不可读取'
    } finally {
      if (!controller.signal.aborted) previewLoading.value = false
    }
  }
  watch(selectedVersion, loadMedia)
  watch(page, () => {
    void load()
  })
  watch(
    () => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions || [])],
    () => {
      listController?.abort()
      clearMedia()
      rows.value = []
      selected.value = undefined
      selectedVersion.value = ''
      total.value = 0
      loading.value = false
      error.value = ''
      if (active.value && auth.token) void load()
    },
    { flush: 'sync' },
  )
  function suspend() {
    active.value = false
    listController?.abort()
    loading.value = false
    clearMedia()
  }
  function resume() {
    if (active.value || !mountedActive || !visible()) return
    active.value = true
    void load(true)
  }
  onDeactivated(() => { mountedActive = false; suspend() })
  onActivated(() => { mountedActive = true; resume() })
  watch(visible, value => value ? resume() : suspend(), { flush: 'sync' })
  onBeforeUnmount(() => {
    alive = false
    listController?.abort()
    clearMedia()
  })
  void load()
  return {
    active,
    rows,
    page,
    total,
    loading,
    error,
    selected,
    selectedVersion,
    preview,
    previewLoading,
    previewError,
    properties,
    choose,
    load,
  }
}
