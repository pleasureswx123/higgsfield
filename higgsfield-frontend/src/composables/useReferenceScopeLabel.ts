import { ref, watch } from 'vue'
import { getProject } from '@/api/projects'
import { readFolder } from '@/api/folders'

export function useReferenceScopeLabel(projectId: () => string, folderId: () => string | null, visible: () => boolean) {
  const projectName = ref('当前项目'), folderPath = ref('当前目录')
  watch(() => [projectId(), folderId(), visible()], async (_, __, cleanup) => {
    const controller = new AbortController(); cleanup(() => controller.abort())
    if (!visible()) return
    try {
      const [project, folder] = await Promise.all([getProject(projectId(), controller.signal), folderId() ? readFolder(folderId()!, controller.signal) : Promise.resolve(null)])
      if (controller.signal.aborted) return
      projectName.value = project.data.name
      folderPath.value = [project.data.name, ...(folder ? [...folder.data.ancestors, folder.data.folder].map(item => item.name) : [])].join(' / ')
    } catch { /* 名称不可读取时保留通用标签，不影响候选权限校验。 */ }
  }, { immediate: true })
  return { projectName, folderPath }
}
