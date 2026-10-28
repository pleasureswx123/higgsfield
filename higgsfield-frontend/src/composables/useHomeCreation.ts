import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getProjects, type Project } from '@/api/projects'
import { readBrief } from '@/api/projectWorkspace'
import { saveCreationDraft, type DraftBody } from '@/api/creation'

export function useHomeCreation(inline = false) {
  const selectedProject = ref<Project | null>(null)
  const auth = useAuthStore()
  const mode = ref<'image' | 'video'>('video'),
    prompt = ref(''),
    dialog = ref(false)
  const projects = ref<Project[]>([]),
    q = ref(''),
    page = ref(1),
    total = ref(0)
  const loading = ref(false),
    saving = ref(false),
    error = ref('')
  const router = useRouter()
  let controller: AbortController | undefined,
    epoch = 0,
    signature = '',
    key = ''
  let navigating = false
  let active = true
  async function load() {
    if (!active || !auth.token) return
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = true
    error.value = ''
    try {
      const response = await getProjects(
        { q: q.value, pageNum: page.value, pageSize: 10, status: 'active' },
        current.signal,
      )
      if (current.signal.aborted) return
      projects.value = response.rows
      total.value = response.total
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '项目加载失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  function open() {
    if (!active || !auth.token || (!inline && !prompt.value.trim()) || saving.value) return
    dialog.value = true
    page.value = 1
    void load()
  }
  function search() {
    page.value = 1
    void load()
  }
  async function choose(project: Project) {
    if (!active || !auth.token || saving.value || (!inline && !prompt.value.trim())) return
    const ticket = epoch
    const kind = mode.value,
      text = prompt.value
    saving.value = true
    error.value = ''
    try {
      const brief = (await readBrief(project.id)).data
      if (ticket !== epoch) return
      if (!brief.allowedActions.includes('generation:create'))
        throw new Error('此项目没有创作权限或已不可编辑，请选择其他项目')
      if (inline) {
        selectedProject.value = project
        dialog.value = false
        return
      }
      const payload = JSON.stringify([project.id, kind, text])
      if (signature !== payload) {
        signature = payload
        key = crypto.randomUUID()
      }
      const body: DraftBody = {
        schemaVersion: 1,
        modelVersionId: null,
        parameters: {},
        prompt: {
          schemaVersion: 1,
          type: 'doc',
          content: [{ type: 'paragraph', content: [{ type: 'text', text }] }],
        },
      }
      const response = await saveCreationDraft(null, project.id, kind, body, key)
      if (ticket !== epoch) return
      navigating = true
      const failure = await router.push({
        name: 'project-detail',
        params: { id: project.id },
        query: { tab: 'creation', draft: response.data.id },
      })
      if (failure) throw new Error('草稿已保存，页面未切换；可重试打开，不会重复创建')
      if (ticket === epoch) {
        dialog.value = false
        signature = ''
        key = ''
      }
    } catch (cause) {
      if (ticket === epoch)
        error.value = cause instanceof Error ? cause.message : '保存草稿失败，请重试'
    } finally {
      if (ticket === epoch) {
        navigating = false
        saving.value = false
      }
    }
  }
  function close() {
    if (!saving.value) {
      dialog.value = false
      controller?.abort()
    }
  }
  function confirmLeave() {
    if (navigating || selectedProject.value) return true
    if (saving.value) return false
    if (!prompt.value.trim()) return true
    const ticket = epoch
    return ElMessageBox.confirm('创作描述尚未保存到项目。页面切换会在当前会话内暂存，刷新或退出登录会丢失。是否继续离开？', '未保存的创作描述', {
      confirmButtonText: '离开页面',
      cancelButtonText: '继续编辑',
      type: 'warning',
    }).then(() => ticket === epoch && !saving.value).catch(() => false)
  }
  function beforeUnload(event: BeforeUnloadEvent) {
    if (active && !selectedProject.value && !navigating && (saving.value || prompt.value.trim())) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onBeforeRouteLeave(confirmLeave)
  window.addEventListener('beforeunload', beforeUnload)
  onActivated(() => { active = true })
  onDeactivated(() => { active = false; controller?.abort() })
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', beforeUnload)
    epoch++
    controller?.abort()
  })
  watch(
    () => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions ?? [])],
    () => {
      epoch++
      controller?.abort()
      selectedProject.value = null
      projects.value = []
      prompt.value = ''
      dialog.value = false
      error.value = ''
      signature = ''
      key = ''
      total.value = 0
      q.value = ''
      page.value = 1
      saving.value = false
      loading.value = false
      navigating = false
    },
    { flush: 'sync' },
  )
  return {
    selectedProject,
    mode,
    prompt,
    dialog,
    projects,
    q,
    page,
    total,
    loading,
    saving,
    error,
    open,
    close,
    load,
    search,
    choose,
  }
}
