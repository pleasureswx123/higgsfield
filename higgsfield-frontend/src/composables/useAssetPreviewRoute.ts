import { onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { readAsset, readAssetVersion, type Asset } from '@/api/assets'
import { useAuthStore } from '@/stores/auth'

/** 素材预览由地址驱动，不依赖列表分页或浏览器内存。 */
export function useAssetPreviewRoute(projectId: string, visible: () => boolean,
  open: (asset: Asset, download?: boolean) => Promise<void>, close: () => void,
  failure: (message: string) => void, folder: () => string | null) {
  const route = useRoute(), router = useRouter(), auth = useAuthStore()
  let controller: AbortController | undefined
  watch(() => [route.query.asset, route.query.assetVersion, route.params.id, visible(), folder(), auth.token, JSON.stringify(auth.user?.permissions || [])], async () => {
    controller?.abort()
    close()
    if (!visible() || !auth.token || String(route.params.id) !== projectId || !(route.query.asset || route.query.assetVersion)) return
    const id = route.query.assetVersion || route.query.asset
    if (typeof id !== 'string' || !/^[1-9]\d{0,18}$/.test(id)) { failure('素材链接无效'); return }
    const current = new AbortController()
    controller = current
    try {
      const result = await (route.query.assetVersion ? readAssetVersion(id, current.signal) : readAsset(id, current.signal))
      if (!current.signal.aborted) await open(result.data)
    } catch (cause) {
      if (!current.signal.aborted) failure(cause instanceof Error ? cause.message : '素材不存在或无权访问')
    }
  }, { immediate: true })
  async function openPreview(asset: Asset, download = false) {
    if (download) { await open(asset, true); return }
    await router.push({ query: { ...route.query, tab: 'folders', asset: asset.id, assetVersion: undefined } })
  }
  function closePreview() {
    // 保留项目、目录和筛选地址，只清理素材标识。
    if (route.query.asset || route.query.assetVersion) return router.push({ query: { ...route.query, asset: undefined, assetVersion: undefined, tab: route.query.previewFrom === 'elements' ? 'elements' : route.query.tab, previewFrom: undefined } })
    else close()
  }
  onBeforeUnmount(() => controller?.abort())
  return { openPreview, closePreview }
}
