import { onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { readBrief } from '@/api/projectWorkspace'
import { useAssetUploads } from './useAssetUploads'
import { assetUploadMime } from '@/utils/assetFormats'

/** 引用选择器复用素材上传流水线，上传前实时核验当前项目授权。 */
export function useReferenceUploads(projectId: string, folder: () => string | null, disabled: () => boolean, changed: () => void) {
  const auth = useAuthStore()
  const uploads = useAssetUploads(projectId, changed)
  const checking = ref(false), error = ref('')
  let epoch = 0, alive = true
  async function enqueue(files: File[]) {
    if (!alive || disabled() || checking.value || !auth.token || !files.length) return
    const ticket = ++epoch, folderId = folder()
    error.value = ''
    if (files.some(file => !/^(image|video)\//.test(assetUploadMime(file) || ''))) {
      error.value = '参考素材只支持图片或视频，请重新选择文件'
      return
    }
    checking.value = true
    try {
      const result = await readBrief(projectId)
      if (!alive || ticket !== epoch || disabled()) return
      if (!['asset:upload', 'asset:create', 'asset:reference'].every(code => result.data.allowedActions.includes(code)))
        throw new Error('当前项目尚未授予上传、创建及引用素材权限，请联系项目管理员')
      uploads.enqueue(files, folderId)
    } catch (cause) {
      if (alive && ticket === epoch) error.value = cause instanceof Error ? cause.message : '无法核验上传权限'
    } finally {
      if (ticket === epoch) checking.value = false
    }
  }
  watch(() => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions ?? []), disabled()], () => {
    epoch++; checking.value = false; error.value = ''; uploads.pause()
  }, { flush: 'sync' })
  onBeforeUnmount(() => { alive = false; epoch++ })
  return { ...uploads, enqueue, checking, error }
}
