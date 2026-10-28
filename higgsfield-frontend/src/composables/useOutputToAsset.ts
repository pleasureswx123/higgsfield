import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import type { FormInstance } from 'element-plus'
import { outputToAsset, type Asset } from '@/api/assets'
import { getProjects, type Project } from '@/api/projects'
import { readBrief } from '@/api/projectWorkspace'
import { listFolders, type Folder } from '@/api/folders'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
import { readOutputAssetRecovery, saveOutputAssetRecovery, finishOutputAssetRecovery, clearOutputAssetRecovery } from '@/utils/outputAssetRecovery'

export function useOutputToAsset(outputId: string, initialProjectId: string) {
  const auth = useAuthStore(),
    form = ref<FormInstance>()
  const fields = reactive({
    projectId: initialProjectId,
    folderId: null as string | null,
    name: '生成作品素材',
  })
  const projects = ref<Project[]>([]),
    search = ref(''),
    page = ref(1),
    total = ref(0)
  const folders = ref<Folder[]>([]),
    trail = ref<Folder[]>([]),
    folderPage = ref(1),
    folderTotal = ref(0)
  const loading = ref(false),
    checking = ref(false),
    folderLoading = ref(false),
    saving = ref(false)
  const allowed = ref(false),
    error = ref(''),
    result = ref<Asset>(),
    uncertain = ref(false)
  const locked = computed(() => saving.value || uncertain.value)
  let active = true, alive = true
  const available = () => active && alive && !!auth.token
  const canClose = computed(() => !saving.value && (!uncertain.value || (!allowed.value && !checking.value)))
  let searchController: AbortController | undefined,
    checkController: AbortController | undefined,
    writer: AbortController | undefined
  let epoch = 0,
    validationEpoch = 0,
    folderEpoch = 0,
    key = '',
    signature = ''
  async function loadProjects() {
    searchController?.abort()
    projects.value = []; total.value = 0; loading.value = false
    if (!available()) return
    const current = new AbortController()
    searchController = current
    projects.value = []
    loading.value = true
    try {
      const response = await getProjects(
        { q: search.value, pageNum: page.value, pageSize: 10, status: 'active' },
        current.signal,
      )
      if (!current.signal.aborted) {
        projects.value = response.rows
        total.value = response.total
      }
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '项目加载失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  function filter() {
    if (page.value !== 1) page.value = 1
    else void loadProjects()
  }
  async function loadFolders() {
    const stamp = ++folderEpoch
    folders.value = []
    folderTotal.value = 0
    folderLoading.value = false
    if (!available() || !allowed.value) return
    folderLoading.value = true
    try {
      const response = await listFolders(fields.projectId, {
        parentId: fields.folderId,
        folderKind: 'media',
        pageNum: folderPage.value,
        pageSize: 20,
      })
      if (stamp === folderEpoch) {
        folders.value = response.rows
        folderTotal.value = response.total
      }
    } catch (cause) {
      if (stamp === folderEpoch)
        error.value = cause instanceof Error ? cause.message : '目录加载失败'
    } finally {
      if (stamp === folderEpoch) folderLoading.value = false
    }
  }
  function enter(folder?: Folder) {
    if (!available() || !allowed.value || locked.value) return
    if (folder) trail.value = [...trail.value, folder]
    else trail.value = trail.value.slice(0, -1)
    fields.folderId = trail.value.at(-1)?.id || null
    folderPage.value = 1
    void loadFolders()
  }
  async function checkTarget(preserveSelection = false) {
    validationEpoch++
    checkController?.abort()
    folderEpoch++
    allowed.value = false
    folders.value = []
    if (!preserveSelection) {
      trail.value = []
      fields.folderId = null
    }
    folderTotal.value = 0
    folderPage.value = 1
    folderLoading.value = false
    checking.value = false
    if (!available() || !fields.projectId) return
    const current = new AbortController()
    checkController = current
    checking.value = true
    try {
      const response = await readBrief(fields.projectId, current.signal)
      if (current.signal.aborted) return
      allowed.value = response.data.allowedActions.includes('asset:create')
      error.value = allowed.value ? '' : '目标项目没有素材创建权限或已不可编辑。'
      if (allowed.value) await loadFolders()
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '项目权限检查失败'
    } finally {
      if (!current.signal.aborted) checking.value = false
    }
  }
  async function submit() {
    if (!available() || saving.value || result.value || !allowed.value || checking.value) return
    const existing = readOutputAssetRecovery(auth.token, outputId)
    if (existing && existing.key !== key) { restore(); void checkTarget(true); return }
    const stamp = epoch, validation = validationEpoch,
      payload = { ...fields }, serialized = JSON.stringify(payload)
    if (!(await form.value?.validate().catch(() => false)) || stamp !== epoch ||
      validation !== validationEpoch || saving.value || result.value || !available() ||
      !allowed.value || checking.value || serialized !== JSON.stringify(fields))
      return
    const afterValidation = readOutputAssetRecovery(auth.token, outputId)
    if (afterValidation && afterValidation.key !== key) { restore(); void checkTarget(true); return }
    if (uncertain.value && signature !== serialized) return
    if (serialized !== signature) {
      signature = serialized
      key = crypto.randomUUID()
    }
    writer = new AbortController()
    saving.value = true
    error.value = ''
    const token = auth.token, requestKey = key
    saveOutputAssetRecovery(token, outputId, { key, data: payload })
    try {
      const response = await outputToAsset(outputId, payload, key, writer.signal)
      finishOutputAssetRecovery(token, outputId, requestKey)
      if (stamp !== epoch) return
      result.value = response.data
      uncertain.value = false
    } catch (cause) {
      if (stamp !== epoch) return
      uncertain.value =
        uncertain.value ||
        !(cause instanceof ApiError) ||
        cause.code === 0 ||
        cause.code === 408 ||
        cause.errorCode === 'IDEMPOTENCY_IN_PROGRESS' ||
        (cause.code >= 500 && cause.code < 600)
      if (!uncertain.value) finishOutputAssetRecovery(token, outputId, requestKey)
      error.value = cause instanceof Error ? cause.message : '入库失败'
    } finally {
      if (stamp === epoch) saving.value = false
    }
  }
  function restore() {
    if (!available()) return
    const saved = readOutputAssetRecovery(auth.token, outputId)
    if (!saved) return
    uncertain.value = true
    Object.assign(fields, saved.data)
    key = saved.key
    signature = JSON.stringify(saved.data)
    error.value = '存在尚未确认的入库操作，请恢复权限后核对原请求。'
  }
  function clear() {
    epoch++
    folderEpoch++
    searchController?.abort()
    checkController?.abort()
    writer?.abort()
    projects.value = []
    folders.value = []
    trail.value = []
    result.value = undefined
    allowed.value = false
    loading.value = false
    checking.value = false
    folderLoading.value = false
    saving.value = false
    uncertain.value = false
    fields.name = ''
    fields.projectId = ''
    fields.folderId = null
    error.value = ''
    total.value = 0
    folderTotal.value = 0
    key = ''
    signature = ''
  }
  watch(page, () => {
    if (!locked.value) void loadProjects()
  })
  watch(
    () => fields.projectId,
    () => {
      if (fields.projectId && !locked.value) void checkTarget()
    },
    { immediate: true },
  )
  watch(() => auth.token, () => { clearOutputAssetRecovery(); clear() }, { flush: 'sync' })
  watch(() => JSON.stringify(auth.user?.permissions || []), () => {
    // 权限重新核验不改写尚未确认的原目录、名称和幂等意图。
    void checkTarget(true)
    void loadProjects()
  }, { flush: 'sync' })
  onBeforeRouteLeave(() => canClose.value)
  onDeactivated(() => { active = false; clear() })
  onActivated(() => {
    if (!active && alive) { active = true; restore(); void loadProjects(); void checkTarget(uncertain.value) }
  })
  onBeforeUnmount(() => { alive = false; clear() })
  restore()
  if (uncertain.value) void checkTarget(true)
  void loadProjects()
  return {
    form,
    fields,
    projects,
    search,
    page,
    total,
    folders,
    trail,
    folderPage,
    folderTotal,
    loading,
    checking,
    folderLoading,
    saving,
    allowed,
    error,
    result,
    uncertain,
    locked,
    canClose,
    filter,
    loadFolders,
    enter,
    submit,
  }
}
