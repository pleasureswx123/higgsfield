import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  reactive,
  ref,
  watch,
  type Ref,
} from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox, type FormInstance } from 'element-plus'
import {
  createElement,
  readElement,
  saveElement,
  listProperties,
  recycleElement,
  type ElementDetail,
  type ElementFields,
  type PropertyDefinition,
} from '@/api/elements'
import { listAssets, readMedia, type Asset, type LibraryEntry } from '@/api/assets'
import { readMembers, type Member } from '@/api/projectWorkspace'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value))
const message = (error: unknown) => (error instanceof Error ? error.message : '操作失败，请重试')
export function useElementEditor(
  projectId: string,
  id: string | null,
  actions: Ref<string[]>,
  completed: () => void,
  visible: () => boolean = () => true,
  initialAsset?: Asset,
) {
  const auth = useAuthStore()
  const active = ref(visible())
  let mountedActive = true
  let lifecycle = 0
  const uncertain = ref(false)
  const conflict = ref(false)
  const aliasManual = ref(false),
    aliasError = ref('')
  const form = ref<FormInstance>(),
    detail = ref<ElementDetail>(),
    loading = ref(true),
    ready = ref(false),
    saving = ref(false),
    error = ref('')
  const locked = computed(() => saving.value || uncertain.value)
  const aliasSuggestion = computed(() => {
    const normalize = (value: string) =>
      value
        .normalize('NFKC')
        .trim()
        .toLowerCase()
        .replace(/[^\p{L}\p{N}_-]+/gu, '_')
        .replace(/^_+|_+$/g, '')
    const name = normalize(fields.name)
    if (!name) return fields.name.trim() ? `element_${fields.category}` : ''
    const prefix = { character: 'char', scene: 'scene', prop: 'prop', other: 'element' }[
      fields.category
    ]
    const label = normalize(fields.label)
    return Array.from([prefix, name, label].filter(Boolean).join('_')).slice(0, 100).join('')
  })
  let saveIntent: { payload: ElementFields; key: string; revision?: string } | undefined
  let deleteIntent: { revision: string; key: string } | undefined
  const fields = reactive<ElementFields>({
    name: '',
    alias: '',
    category: 'character',
    workStatus: 'none',
    performerId: null,
    description: '',
    label: '',
    media: [],
    propertyValues: [],
  })
  const properties = ref<{ definition: PropertyDefinition; value: string | string[] | null }[]>([]),
    members = ref<Member[]>([])
  const newerDefinitions = ref<Record<string, PropertyDefinition>>({})
  const allowed = computed(() => (id ? detail.value?.element.allowedActions || [] : actions.value))
  const canEdit = computed(
    () =>
      active.value && ready.value && allowed.value.includes(id ? 'element:edit' : 'element:create'),
  )
  const canReview = computed(() => ready.value && allowed.value.includes('content:review'))
  function markAliasManual() {
    aliasManual.value = true
  }
  function resetAliasSuggestion() {
    if (id || !canEdit.value || locked.value) return
    aliasManual.value = false
    fields.alias = aliasSuggestion.value
  }
  watch(
    aliasSuggestion,
    (value) => {
      if (!id && !aliasManual.value && canEdit.value && !locked.value) fields.alias = value
    },
    { flush: 'sync' },
  )
  watch(
    () => fields.alias,
    () => {
      aliasError.value = ''
    },
    { flush: 'sync' },
  )
  const canRemove = computed(
    () => active.value && ready.value && !!id && allowed.value.includes('element:remove'),
  )
  const selectedVersion = ref(''),
    previewUrl = ref(''),
    previewKind = ref<'image' | 'video'>('image'),
    previewLoading = ref(false),
    previewError = ref('')
  const pickerKind = ref<'image' | 'video'>('image')
  const pickerOpen = ref(false),
    candidates = ref<LibraryEntry[]>([]),
    pickerSearch = ref(''),
    pickerPage = ref(1),
    pickerTotal = ref(0),
    pickerLoading = ref(false),
    pickerError = ref('')
  const loadController = new AbortController()
  let previewController: AbortController | undefined, pickerController: AbortController | undefined
  let baseline = ''
  const snapshot = () =>
    JSON.stringify({
      fields,
      properties: properties.value.map((item) => ({ id: item.definition.id, value: item.value })),
    })
  const dirty = computed(() => !loading.value && !!baseline && snapshot() !== baseline)
  async function initialize() {
    if (!active.value || loadController.signal.aborted) return
    const ticket = lifecycle
    loading.value = true
    properties.value = []
    members.value = []
    newerDefinitions.value = {}
    try {
      if (id) {
        const result = await readElement(id, loadController.signal)
        if (loadController.signal.aborted || ticket !== lifecycle) return
        if (result.data.element.projectId !== projectId)
          throw new Error('元素不属于当前项目，请从所属项目打开。')
        detail.value = result.data
        const { element, currentRevision } = result.data
        Object.assign(fields, {
          name: element.name,
          alias: element.alias,
          category: element.category,
          workStatus: element.workStatus,
          performerId: element.performerId,
          description: currentRevision.description,
          label: currentRevision.label,
          media: clone(currentRevision.media),
          propertyValues: clone(currentRevision.propertyValues),
        })
        properties.value = currentRevision.propertySnapshot.map((item) => ({
          definition: {
            id: item.definitionId,
            versionNo: item.definitionVersion,
            propertyKey: item.propertyKey,
            name: item.name,
            valueType: item.valueType,
            options: item.options,
          },
          value: clone(item.value),
        }))
      }
      let page = 1,
        more = true
      while (more && !loadController.signal.aborted) {
        const result = await listProperties(projectId, page++, loadController.signal)
        if (loadController.signal.aborted || ticket !== lifecycle) return
        for (const definition of result.rows) {
          const existing = properties.value.find(
            (item) => item.definition.propertyKey === definition.propertyKey,
          )
          if (!existing) properties.value.push({ definition, value: null })
          else if (existing.definition.id !== definition.id)
            newerDefinitions.value[existing.definition.id] = definition
        }
        more = result.hasNext
      }
      if (allowed.value.includes('member:read')) {
        let memberPage = 1,
          total = Infinity
        while (members.value.length < total && !loadController.signal.aborted) {
          const result = await readMembers(projectId, memberPage++, 'active')
          if (loadController.signal.aborted || ticket !== lifecycle) return
          members.value.push(...result.rows)
          total = result.total
          if (!result.rows.length) break
        }
      }
      if (loadController.signal.aborted || ticket !== lifecycle) return
      selectedVersion.value =
        fields.media.find((item) => item.isPrimary)?.assetVersionId ||
        fields.media[0]?.assetVersionId ||
        ''
      baseline = snapshot()
      ready.value = true
      if (!id && initialAsset && !fields.media.length && canEdit.value) {
        fields.name = initialAsset.name.replace(/\.[^.]+$/, '')
        addMedia(initialAsset)
      }
    } catch (cause) {
      if (!loadController.signal.aborted && ticket === lifecycle) error.value = message(cause)
    } finally {
      if (ticket === lifecycle) loading.value = false
    }
  }
  function releasePreview() {
    previewController?.abort()
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
    previewLoading.value = false
  }
  async function adoptDefinition(id: string) {
    if (!canEdit.value || locked.value) return
    const ticket = lifecycle
    const property = properties.value.find((item) => item.definition.id === id)
    const next = newerDefinitions.value[id]
    if (!property || !next) return
    try {
      await ElMessageBox.confirm(
        `将“${property.definition.name}”切换至定义版本 ${next.versionNo}。不兼容的当前值将清空，历史修订保持不变。`,
        '采用最新属性定义',
        { confirmButtonText: '切换定义', cancelButtonText: '保留原定义' },
      )
    } catch {
      return
    }
    if (loadController.signal.aborted || ticket !== lifecycle || !canEdit.value || locked.value)
      return
    const value = property.value
    const compatible =
      value === null ||
      (next.valueType === 'text' && typeof value === 'string') ||
      (next.valueType === 'single_select' &&
        typeof value === 'string' &&
        next.options.includes(value)) ||
      (next.valueType === 'multi_select' &&
        Array.isArray(value) &&
        value.every((option) => next.options.includes(option)))
    property.value = compatible ? value : null
    property.definition = next
    delete newerDefinitions.value[id]
  }
  async function loadPreview(version: string) {
    releasePreview()
    previewError.value = ''
    if (!version || !active.value || loadController.signal.aborted) return
    const controller = new AbortController()
    previewController = controller
    previewLoading.value = true
    try {
      const blob = await readMedia(version, false, controller.signal, () => {})
      if (!controller.signal.aborted) {
        previewKind.value = blob.type.startsWith('video/') ? 'video' : 'image'
        previewUrl.value = URL.createObjectURL(blob)
      }
    } catch (cause) {
      if (!controller.signal.aborted) previewError.value = message(cause)
    } finally {
      if (!controller.signal.aborted) previewLoading.value = false
    }
  }
  watch(selectedVersion, loadPreview)
  async function loadCandidates() {
    if (loadController.signal.aborted || !canEdit.value) return
    pickerController?.abort()
    const controller = new AbortController()
    pickerController = controller
    pickerLoading.value = true
    pickerError.value = ''
    try {
      const result = await listAssets(
        projectId,
        {
          folderId: null,
          includeDescendants: true,
          fileType: pickerKind.value,
          pageNum: pickerPage.value,
          q: pickerSearch.value,
        },
        controller.signal,
      )
      if (!controller.signal.aborted) {
        candidates.value = result.rows
        pickerTotal.value = result.total
      }
    } catch (cause) {
      if (!controller.signal.aborted) pickerError.value = message(cause)
    } finally {
      if (!controller.signal.aborted) pickerLoading.value = false
    }
  }
  function showPicker() {
    if (loadController.signal.aborted || !canEdit.value || locked.value) return
    pickerOpen.value = true
    void loadCandidates()
  }
  function searchCandidates() {
    if (pickerPage.value !== 1) pickerPage.value = 1
    else void loadCandidates()
  }
  watch(pickerKind, searchCandidates)
  watch(pickerPage, () => {
    void loadCandidates()
  })
  function addMedia(asset: Asset) {
    if (
      !['image', 'video'].includes(asset.mediaType) ||
      !canEdit.value ||
      locked.value ||
      fields.media.some((item) => item.assetVersionId === asset.currentVersionId)
    )
      return
    fields.media.push({
      assetVersionId: asset.currentVersionId,
      ordinal: fields.media.length,
      isPrimary: fields.media.length === 0,
    })
    selectedVersion.value = asset.currentVersionId
  }
  function primary(version: string) {
    if (canEdit.value && !locked.value)
      fields.media = fields.media.map((item) => ({
        ...item,
        isPrimary: item.assetVersionId === version,
      }))
  }
  function removeMedia(version: string) {
    if (!canEdit.value || locked.value) return
    fields.media = fields.media
      .filter((item) => item.assetVersionId !== version)
      .map((item, index) => ({ ...item, ordinal: index }))
    if (fields.media.length && !fields.media.some((item) => item.isPrimary))
      fields.media[0]!.isPrimary = true
    if (selectedVersion.value === version)
      selectedVersion.value = fields.media[0]?.assetVersionId || ''
  }
  function moveMedia(version: string, direction: number) {
    if (!canEdit.value || locked.value) return
    const index = fields.media.findIndex((item) => item.assetVersionId === version),
      target = index + direction
    if (index < 0 || target < 0 || target >= fields.media.length) return
    const next = [...fields.media]
    ;[next[index], next[target]] = [next[target]!, next[index]!]
    fields.media = next.map((item, ordinal) => ({ ...item, ordinal }))
  }
  async function save() {
    if (deleteIntent || conflict.value) return
    const ticket = lifecycle
    if (
      saving.value ||
      loading.value ||
      !baseline ||
      !canEdit.value ||
      (!saveIntent && !(await form.value?.validate().catch(() => false)))
    )
      return
    if (loadController.signal.aborted || ticket !== lifecycle || saving.value || !canEdit.value)
      return
    if (!saveIntent) {
      const existingDefinitions = new Set(
        detail.value?.currentRevision.propertySnapshot.map((item) => item.propertyKey) || [],
      )
      const payload: ElementFields = clone({
        ...fields,
        propertyValues: properties.value
          .filter(
            (item) => item.value !== null || existingDefinitions.has(item.definition.propertyKey),
          )
          .map((item) => ({
            definitionId: item.definition.id,
            definitionVersion: item.definition.versionNo,
            value: item.value,
          })),
      })
      saveIntent = { payload, key: crypto.randomUUID(), revision: detail.value?.element.revision }
    }
    const current = saveIntent
    saving.value = true
    uncertain.value = true
    error.value = ''
    try {
      if (id && current.revision)
        await saveElement(id, current.revision, current.payload, current.key)
      else await createElement(projectId, current.payload, current.key)
      if (loadController.signal.aborted || ticket !== lifecycle) return
      saveIntent = undefined
      uncertain.value = false
      baseline = snapshot()
      completed()
    } catch (cause) {
      if (ticket !== lifecycle) return
      if (
        !loadController.signal.aborted &&
        cause instanceof ApiError &&
        ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') ||
          (cause.code >= 400 && cause.code < 500))
      ) {
        saveIntent = undefined
        uncertain.value = false
        conflict.value = cause.errorCode === 'REVISION_CONFLICT'
        if (cause.errorCode === 'ALIAS_CONFLICT') {
          aliasManual.value = true
          aliasError.value = cause.message
        }
      }
      if (!loadController.signal.aborted) error.value = message(cause)
    } finally {
      if (ticket === lifecycle) saving.value = false
    }
  }
  async function remove() {
    const ticket = lifecycle
    if (!id || !detail.value || saving.value || saveIntent || conflict.value || !canRemove.value)
      return
    if (!deleteIntent) {
      try {
        await ElMessageBox.confirm(
          '删除后草稿引用将失效，历史修订保留，30天内可恢复。未保存修改不会提交。',
          '删除元素',
          { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
        )
      } catch {
        return
      }
      if (
        loadController.signal.aborted ||
        ticket !== lifecycle ||
        locked.value ||
        !canRemove.value ||
        !detail.value
      )
        return
      deleteIntent = { revision: detail.value.element.revision, key: crypto.randomUUID() }
    }
    const current = deleteIntent
    saving.value = true
    uncertain.value = true
    error.value = ''
    try {
      await recycleElement(id, current.revision, false, current.key)
      if (loadController.signal.aborted || ticket !== lifecycle) return
      deleteIntent = undefined
      uncertain.value = false
      baseline = snapshot()
      completed()
    } catch (cause) {
      if (ticket !== lifecycle) return
      if (
        !loadController.signal.aborted &&
        cause instanceof ApiError &&
        ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') ||
          (cause.code >= 400 && cause.code < 500))
      ) {
        deleteIntent = undefined
        uncertain.value = false
        conflict.value = cause.errorCode === 'REVISION_CONFLICT'
      }
      if (!loadController.signal.aborted) error.value = message(cause)
    } finally {
      if (ticket === lifecycle) saving.value = false
    }
  }
  function retry() {
    return deleteIntent ? remove() : save()
  }
  async function confirmClose() {
    const ticket = lifecycle
    if (locked.value) return false
    if (!dirty.value) return true
    try {
      await ElMessageBox.confirm('未保存的元素修改将被丢弃。', '关闭编辑', {
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
      })
      return ticket === lifecycle && !locked.value && !loadController.signal.aborted
    } catch {
      return false
    }
  }
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (active.value && (dirty.value || locked.value)) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  window.addEventListener('beforeunload', beforeUnload)
  onBeforeRouteLeave(confirmClose)
  onBeforeRouteUpdate((to, from) => (to.params.id === from.params.id ? true : confirmClose()))
  function suspend() {
    if (!active.value) return
    active.value = false
    lifecycle++
    saving.value = false
    loading.value = false
    pickerController?.abort()
    pickerLoading.value = false
    releasePreview()
  }
  function resume() {
    if (active.value || !mountedActive || !visible()) return
    active.value = true
    if (!ready.value && !loading.value && !loadController.signal.aborted) void initialize()
    else if (ready.value && selectedVersion.value && !previewUrl.value && !previewLoading.value)
      void loadPreview(selectedVersion.value)
  }
  onDeactivated(() => {
    mountedActive = false
    suspend()
  })
  onActivated(() => {
    mountedActive = true
    resume()
  })
  watch(visible, value => value ? resume() : suspend(), { flush: 'sync' })
  watch(
    () => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions ?? [])],
    () => {
      ready.value = false
      saving.value = false
      loadController.abort()
      pickerController?.abort()
      releasePreview()
      detail.value = undefined
      Object.assign(fields, {
        name: '',
        alias: '',
        category: 'character',
        workStatus: 'none',
        performerId: null,
        description: '',
        label: '',
        media: [],
        propertyValues: [],
      })
      properties.value = []
      members.value = []
      newerDefinitions.value = {}
      candidates.value = []
      pickerOpen.value = false
      pickerSearch.value = ''
      pickerPage.value = 1
      pickerTotal.value = 0
      pickerLoading.value = false
      pickerError.value = ''
      selectedVersion.value = ''
      previewError.value = ''
      baseline = ''
      saveIntent = undefined
      deleteIntent = undefined
      uncertain.value = false
      conflict.value = false
      aliasManual.value = false
      aliasError.value = ''
      error.value = '登录状态已改变，请关闭并重新打开元素'
    },
    { flush: 'sync' },
  )
  onBeforeUnmount(() => {
    loadController.abort()
    pickerController?.abort()
    releasePreview()
    window.removeEventListener('beforeunload', beforeUnload)
  })
  void initialize()
  return {
    active,
    newerDefinitions,
    adoptDefinition,
    form,
    fields,
    properties,
    members,
    detail,
    loading,
    saving,
    uncertain,
    conflict,
    aliasManual,
    aliasError,
    aliasSuggestion,
    markAliasManual,
    resetAliasSuggestion,
    locked,
    retry,
    error,
    dirty,
    canEdit,
    canReview,
    canRemove,
    allowed,
    selectedVersion,
    previewUrl,
    previewKind,
    pickerKind,
    previewLoading,
    previewError,
    pickerOpen,
    candidates,
    pickerPage,
    pickerTotal,
    pickerSearch,
    pickerLoading,
    pickerError,
    showPicker,
    searchCandidates,
    addMedia,
    primary,
    removeMedia,
    moveMedia,
    save,
    remove,
    confirmClose,
  }
}
