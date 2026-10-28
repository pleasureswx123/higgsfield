import { onActivated, onBeforeUnmount, onDeactivated, ref, watch, type Ref } from 'vue'
import {
  listAssets,
  readMedia,
  readDocumentText,
  type Asset,
  type LibraryEntry,
} from '@/api/assets'
import { assetExtension, type AssetFileType } from '@/utils/assetFormats'
import { useAuthStore } from '@/stores/auth'
import { libraryWindow } from '@/utils/libraryWindow'

export function useAssetLibrary(
  projectId: string,
  folderId: Ref<string | null>,
  visible: () => boolean = () => true,
) {
  const auth = useAuthStore()
  let active = visible(),
    mountedActive = true
  const rows = ref<LibraryEntry[]>([]),
    total = ref(0),
    page = ref(1),
    search = ref('')
  const fileType = ref<'' | AssetFileType>(''),
    loading = ref(false),
    error = ref('')
  const lastViewedId = ref<string | null>(null)
  const selected = ref<Asset | null>(null),
    mediaUrl = ref(''),
    mediaError = ref(''),
    mediaLoading = ref(false),
    loadedBytes = ref(0)
  const activity = ref<'' | 'generated' | 'uploaded' | 'liked' | 'downloaded'>('')
  const documentSections = ref<string[]>([])
  const pdfBlob = ref<Blob | null>(null)
  const dates = ref<string[] | null>(null)
  const includeDescendants = ref(false)
  type FilterKey = 'search' | 'fileType' | 'activity' | 'dates' | 'includeDescendants'
  function clearFilter(key?: FilterKey) {
    if (!key || key === 'search') search.value = ''
    if (!key || key === 'fileType') fileType.value = ''
    if (!key || key === 'activity') activity.value = ''
    if (!key || key === 'dates') dates.value = null
    if (!key || key === 'includeDescendants') includeDescendants.value = false
    filter()
  }
  let listController: AbortController | undefined, mediaController: AbortController | undefined
  let correctingPage = false
  async function refresh() {
    if (!active || !auth.token) return
    listController?.abort()
    const controller = new AbortController()
    listController = controller
    loading.value = true
    error.value = ''
    const requestedPage = page.value
    try {
      const data = await listAssets(
        projectId,
        {
          ...libraryWindow(dates.value),
          folderId: folderId.value,
          includeDescendants: includeDescendants.value,
          q: search.value,
          pageNum: requestedPage,
          fileType: fileType.value || undefined,
          activity: activity.value || undefined,
        },
        controller.signal,
      )
      if (!controller.signal.aborted) {
        const lastPage = Math.max(1, Math.ceil(data.total / 30))
        if (requestedPage > lastPage) {
          correctingPage = true
          page.value = lastPage
          correctingPage = false
          rows.value = []
          total.value = data.total
          if (data.total > 0) await refresh()
          return
        }
        rows.value = data.rows
        total.value = data.total
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        rows.value = []
        total.value = 0
        error.value = cause instanceof Error ? cause.message : '素材加载失败'
      }
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }
  function closePreview() {
    mediaController?.abort()
    if (mediaUrl.value) URL.revokeObjectURL(mediaUrl.value)
    mediaUrl.value = ''
    documentSections.value = []
    pdfBlob.value = null
    selected.value = null
    mediaLoading.value = false
  }
  async function openMedia(asset: Asset, download = false) {
    if (!active || !auth.token) return
    closePreview()
    selected.value = asset
    mediaError.value = ''
    loadedBytes.value = 0
    mediaLoading.value = true
    const controller = new AbortController()
    mediaController = controller
    try {
      if (
        !download &&
        asset.mediaType === 'document' &&
        asset.file.mimeType !== 'application/pdf'
      ) {
        const result = await readDocumentText(asset.currentVersionId, controller.signal)
        if (!controller.signal.aborted) { documentSections.value = result.data.sections; lastViewedId.value = asset.id }
        return
      }
      const blob = await readMedia(asset.currentVersionId, download, controller.signal, (value) => {
        if (!controller.signal.aborted) loadedBytes.value = value
      })
      if (controller.signal.aborted) return
      if (!download) lastViewedId.value = asset.id
      if (!download && asset.file.mimeType === 'application/pdf') {
        pdfBlob.value = blob
        return
      }
      mediaUrl.value = URL.createObjectURL(blob)
      if (download) {
        const anchor = document.createElement('a')
        const extension = assetExtension(asset.file.mimeType)
        anchor.href = mediaUrl.value
        anchor.download = asset.name.toLowerCase().endsWith(extension)
          ? asset.name
          : asset.name + extension
        anchor.click()
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        mediaError.value = cause instanceof Error ? cause.message : '媒体读取失败'
    } finally {
      if (!controller.signal.aborted) mediaLoading.value = false
    }
  }
  function filter() {
    if (page.value !== 1) page.value = 1
    else void refresh()
  }
  watch(
    folderId,
    () => {
      closePreview()
      rows.value = []
      filter()
    },
    { immediate: true },
  )
  watch(
    page,
    () => {
      if (!correctingPage) void refresh()
    },
    { flush: 'sync' },
  )
  function clear() {
    lastViewedId.value = null
    listController?.abort()
    rows.value = []
    total.value = 0
    loading.value = false
    error.value = ''
    closePreview()
    mediaError.value = ''
    loadedBytes.value = 0
  }
  function suspend() {
    if (!active) return
    active = false
    listController?.abort()
    loading.value = false
    mediaController?.abort()
    mediaLoading.value = false
  }
  function resume() {
    if (active || !mountedActive || !visible()) return
    active = true
    void refresh()
    if (selected.value) void openMedia(selected.value)
  }
  onDeactivated(() => {
    mountedActive = false
    suspend()
    clear()
  })
  onActivated(() => {
    mountedActive = true
    resume()
  })
  watch(
    visible,
    (value) => {
      if (value) resume()
      else suspend()
    },
    { flush: 'sync' },
  )
  watch(
    () => [auth.token, JSON.stringify(auth.user?.permissions || [])],
    () => {
      clear()
      if (active) void refresh()
    },
    { flush: 'sync' },
  )
  onBeforeUnmount(() => {
    active = false
    clear()
  })
  return {
    rows,
    total,
    page,
    search,
    fileType,
    dates,
    includeDescendants,
    activity,
    loading,
    error,
    refresh,
    filter,
    clearFilter,
    lastViewedId,
    selected,
    mediaUrl,
    documentSections,
    pdfBlob,
    mediaError,
    mediaLoading,
    loadedBytes,
    openMedia,
    closePreview,
  }
}
