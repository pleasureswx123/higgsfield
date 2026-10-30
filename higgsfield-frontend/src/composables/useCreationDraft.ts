import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { modelTransition } from '@/utils/modelTransition'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import type { FormInstance } from 'element-plus'
import { promptText, type PromptDocument } from '@/utils/promptDocument'
import {
  getModelCatalog,
  getCreationDrafts,
  getCreationDraft,
  saveCreationDraft,
  type CreationDraft,
  type DraftBody,
  type ModelCapability,
  type Scalar,
  type DraftReference,
  type DraftSummary,
} from '@/api/creation'

export function useCreationDraft(projectId: string, defaultFolder: () => string | null = () => null, initial?: { prompt?: string; kind?: 'image' | 'video'; autoSave?: boolean; pauseAutoSave?: () => boolean }) {
  const folderId = ref<string | null>(defaultFolder())
  const modelParameters = new Map<string, Record<string, Scalar>>()
  const auth = useAuthStore()
  let active = true,
    epoch = 0,
    viewEpoch = 0
  const readable = () => alive && active && Boolean(auth.token)
  const kind = ref<'image' | 'video'>(initial?.kind ?? 'image'),
    prompt = ref(''),
    models = ref<ModelCapability[]>([])
  const selected = ref<ModelCapability | null>(null),
    parameters = ref<Record<string, Scalar>>({})
  const q = ref(''),
    page = ref(1),
    total = ref(0),
    loading = ref(false),
    saving = ref(false),
    error = ref(''),
    notice = ref('')
  const uncertain = ref(false)
  const locked = computed(() => saving.value || uncertain.value)
  let intent:
    | {
        draft: CreationDraft | null
        kind: 'image' | 'video'
        body: DraftBody
        references: DraftReference[]
        key: string
        signature: string
      }
    | undefined
  const draft = ref<CreationDraft | null>(null),
    formRef = ref<FormInstance>()
  const drafts = ref<DraftSummary[]>([]),
    draftPage = ref(1),
    draftTotal = ref(0),
    draftsLoading = ref(false),
    opening = ref(false)
  const references = ref<DraftReference[]>([]),
    preservedBody = ref<DraftBody | null>(null),
    originalPrompt = ref(''),
    selectedVersion = ref<string | null>(null)
  const richPrompt = computed(
    () =>
      !!preservedBody.value?.prompt.content.some((paragraph) =>
        paragraph.content.some((node) => node.type === 'mention' || (node.marks?.length || 0) > 0),
      ),
  )
  const missingModel = computed(() => !!selectedVersion.value && !selected.value)
  const form = computed(() => ({ prompt: prompt.value }))
  const body = computed<DraftBody>(() => ({
    ...preservedBody.value,
    schemaVersion: 1,
    folderId: folderId.value,
    prompt:
      preservedBody.value && prompt.value === originalPrompt.value
        ? preservedBody.value.prompt
        : {
            schemaVersion: 1,
            type: 'doc',
            content: [
              {
                type: 'paragraph',
                content: (prompt.value.match(/[\s\S]{1,20000}/gu) || ['']).map((text) => ({
                  type: 'text',
                  text,
                })),
              },
            ],
          },
    modelVersionId: selectedVersion.value,
    parameters: parameters.value,
  }))
  const saved = ref('')
  const promptDocument = computed<PromptDocument>({
    get: () => body.value.prompt,
    set: (value) => {
      if (locked.value || opening.value) return
      preservedBody.value = { ...body.value, prompt: value }
      prompt.value = promptText(value)
      originalPrompt.value = prompt.value
      notice.value = ''
    },
  })
  const protectedReferenceKeys = computed(() =>
    body.value.prompt.content.flatMap((paragraph) =>
      paragraph.content.flatMap((node) => (node.type === 'mention' ? [node.referenceKey] : [])),
    ),
  )
  let sequence = 0,
    alive = true,
    abort: AbortController | null = null
  const signature = computed(() =>
    JSON.stringify({ kind: kind.value, body: body.value, references: references.value }),
  )
  saved.value = signature.value
  prompt.value = initial?.prompt ?? ''
  type ModeState = {
    folderId: string | null; prompt: string; originalPrompt: string
    selected: ModelCapability | null; selectedVersion: string | null
    parameters: Record<string, Scalar>; draft: CreationDraft | null
    preservedBody: DraftBody | null; references: DraftReference[]
    saved: string; signature: string; modelParameters: [string, Record<string, Scalar>][]
  }
  const modeStates = ref<Partial<Record<'image' | 'video', ModeState>>>({})
  const currentDirty = computed(() => signature.value !== saved.value)
  const dirty = computed(() => currentDirty.value || Object.entries(modeStates.value)
    .some(([mode, state]) => mode !== kind.value && state.signature !== state.saved))
  function rememberMode() {
    modeStates.value[kind.value] = JSON.parse(JSON.stringify({
      folderId: folderId.value, prompt: prompt.value, originalPrompt: originalPrompt.value,
      selected: selected.value, selectedVersion: selectedVersion.value, parameters: parameters.value,
      draft: draft.value, preservedBody: preservedBody.value, references: references.value,
      saved: saved.value, signature: signature.value, modelParameters: [...modelParameters],
    }))
  }
  // 空白创作随当前目录移动；已有草稿或未保存内容始终保留原归属。
  watch(defaultFolder, (value) => {
    if (draft.value || dirty.value || locked.value || opening.value) return
    folderId.value = value
    saved.value = signature.value
  })
  watch(defaultFolder, value => {
    // 空白新草稿跟随浏览位置；已有内容和保存过的草稿保持发起目录。
    if (draft.value || dirty.value || locked.value || opening.value) return
    folderId.value = value
    saved.value = signature.value
  }, { flush: 'sync' })
  let draftSequence = 0
  async function loadDrafts() {
    if (!readable()) return
    const ticket = ++draftSequence
    draftsLoading.value = true
    try {
      const result = await getCreationDrafts({ projectId, pageNum: draftPage.value, pageSize: 10 })
      if (!alive || ticket !== draftSequence) return
      drafts.value = result.rows
      draftTotal.value = result.total
    } catch (cause) {
      if (alive && ticket === draftSequence)
        error.value = cause instanceof Error ? cause.message : '读取草稿列表失败'
    } finally {
      if (alive && ticket === draftSequence) draftsLoading.value = false
    }
  }
  async function openDraft(id: string) {
    if (!readable()) return
    const session = epoch,
      view = viewEpoch
    if (
      locked.value ||
      opening.value ||
      (dirty.value && !window.confirm('打开其他草稿将丢弃当前未保存修改，是否继续？'))
    )
      return
    opening.value = true
    error.value = ''
    notice.value = ''
    try {
      const result = await getCreationDraft(id)
      if (!readable() || session !== epoch || view !== viewEpoch) return
      if (result.data.projectId !== projectId) throw new Error('该草稿不属于当前项目')
      const loaded = result.data
      let model: ModelCapability | null = null
      let modelWarning = ''
      if (loaded.body.modelVersionId) {
        try {
          const catalog = await getModelCatalog({
            projectId,
            kind: loaded.kind,
            versionId: loaded.body.modelVersionId,
            pageNum: 1,
            pageSize: 1,
          })
          model = catalog.rows.find((item) => item.versionId === loaded.body.modelVersionId) || null
        } catch {
          modelWarning = '暂时无法读取此草稿的模型配置，原参数仍保留。'
        }
      }
      if (!readable() || session !== epoch || view !== viewEpoch) return
      if (loaded.kind !== kind.value) rememberMode()
      delete modeStates.value[loaded.kind]
      modelParameters.clear()
      kind.value = loaded.kind
      draft.value = loaded
      folderId.value = loaded.body.folderId ?? null
      preservedBody.value = loaded.body
      references.value = loaded.references || []
      prompt.value = loaded.body.prompt.content
        .map((paragraph) =>
          paragraph.content.map((node) => (node.type === 'text' ? node.text : '[引用]')).join(''),
        )
        .join('\n')
      originalPrompt.value = prompt.value
      selectedVersion.value = loaded.body.modelVersionId
      selected.value = model
      parameters.value = { ...loaded.body.parameters }
      page.value = 1
      q.value = ''
      saved.value = signature.value
      notice.value = modelWarning
      await load()
    } catch (cause) {
      if (readable() && session === epoch && view === viewEpoch)
        error.value = cause instanceof Error ? cause.message : '读取草稿失败'
    } finally {
      if (session === epoch && view === viewEpoch) opening.value = false
    }
  }
  function newDraft() {
    if (!readable()) return
    if (
      locked.value ||
      opening.value ||
      (dirty.value && !window.confirm('开始新草稿将丢弃当前未保存修改，是否继续？'))
    )
      return
    draft.value = null
    modelParameters.clear()
    folderId.value = defaultFolder()
    preservedBody.value = null
    references.value = []
    prompt.value = ''
    originalPrompt.value = ''
    selected.value = null
    selectedVersion.value = null
    parameters.value = {}
    notice.value = ''
    saved.value = signature.value
  }
  async function load() {
    if (!readable()) return
    abort?.abort()
    abort = new AbortController()
    const ticket = ++sequence
    loading.value = true
    error.value = ''
    try {
      const response = await getModelCatalog(
        { projectId, kind: kind.value, q: q.value, pageNum: page.value, pageSize: 20 },
        abort.signal,
      )
      if (!alive || ticket !== sequence) return
      models.value = response.rows
      total.value = response.total
    } catch (cause) {
      if (alive && ticket === sequence) {
        models.value = []
        error.value = cause instanceof Error ? cause.message : '读取模型失败'
      }
    } finally {
      if (alive && ticket === sequence) loading.value = false
    }
  }
  function choose(versionId: string) {
    if (!readable()) return
    if (locked.value || opening.value) return
    const model = models.value.find((item) => item.versionId === versionId) || null
    if (selected.value && selectedVersion.value === (model?.versionId || null)) return
    const transition = modelTransition(model, parameters.value, references.value)
    if (transition.warnings.length && !window.confirm(
      `${transition.warnings.join('\n')}\n提示词和引用会保留，请调整后重新预检；切回原模型可恢复本次编辑参数。是否继续？`,
    )) return
    if (selectedVersion.value) modelParameters.set(selectedVersion.value, { ...parameters.value })
    selected.value = model
    selectedVersion.value = model?.versionId || null
    const remembered = model && modelParameters.get(model.versionId)
    parameters.value = remembered ? modelTransition(model, remembered, references.value).parameters : transition.parameters
    notice.value = transition.warnings.length ? '已保留提示词和引用，请检查不兼容项并重新预检。' : ''
  }
  function setParameter(name: string, value: Scalar | undefined | null) {
    if (!readable()) return
    if (locked.value || opening.value) return
    const next = { ...parameters.value }
    if (value === undefined || value === null || value === '') delete next[name]
    else next[name] = value
    parameters.value = next
  }
  function changeKind(value: 'image' | 'video') {
    if (!readable()) return
    if (locked.value || opening.value || value === kind.value) return
    rememberMode()
    const previous = modeStates.value[value]
    kind.value = value
    modelParameters.clear()
    for (const [id, values] of previous?.modelParameters ?? []) modelParameters.set(id, { ...values })
    folderId.value = previous ? previous.folderId : defaultFolder()
    prompt.value = previous?.prompt ?? ''
    originalPrompt.value = previous?.originalPrompt ?? ''
    selected.value = previous?.selected ?? null
    selectedVersion.value = previous?.selectedVersion ?? null
    parameters.value = { ...(previous?.parameters ?? {}) }
    draft.value = previous?.draft ?? null
    preservedBody.value = previous?.preservedBody ?? null
    references.value = previous?.references ?? []
    page.value = 1
    q.value = ''
    models.value = []
    total.value = 0
    error.value = ''
    notice.value = ''
    saved.value = previous?.saved ?? signature.value
    load()
  }
  function search() {
    page.value = 1
    load()
  }
  const autoSaveError = ref('')
  let autoTimer: ReturnType<typeof setTimeout> | undefined
  function stopAutoSave() { clearTimeout(autoTimer); autoTimer = undefined }
  function scheduleAutoSave() {
    stopAutoSave()
    if (!initial?.autoSave || initial.pauseAutoSave?.() || !readable() || !dirty.value || locked.value || opening.value || autoSaveError.value) return
    autoTimer = setTimeout(() => { void save(true) }, 900)
  }
  async function save(automatic: boolean | Event = false) {
    if (!readable()) return
    const session = epoch,
      view = viewEpoch,
      before = signature.value
    if (saving.value || opening.value) return
    if (!intent && automatic === true && !currentDirty.value) {
      const entry = Object.entries(modeStates.value).find(([mode, state]) => mode !== kind.value && state.signature !== state.saved)
      if (entry) {
        const [mode, state] = entry
        const snapshot = JSON.parse(state.signature)
        intent = { draft: state.draft, kind: mode as 'image' | 'video', body: snapshot.body, references: snapshot.references, key: crypto.randomUUID(), signature: state.signature }
      }
    }
    if (!intent) {
      if (!(await formRef.value?.validate().catch(() => false))) {
        if (automatic === true) autoSaveError.value = '草稿校验未通过，请检查描述后重试'
        return
      }
      if (
        !readable() ||
        session !== epoch ||
        view !== viewEpoch ||
        saving.value ||
        opening.value ||
        before !== signature.value
      )
        return
      intent = JSON.parse(
        JSON.stringify({
          draft: draft.value,
          kind: kind.value,
          body: body.value,
          references: references.value,
          key: crypto.randomUUID(),
          signature: before,
        }),
      )
    }
    const pending = intent!
    stopAutoSave()
    autoSaveError.value = ''
    saving.value = true
    error.value = ''
    notice.value = ''
    try {
      const response = await saveCreationDraft(
        pending.draft,
        projectId,
        pending.kind,
        pending.body,
        pending.key,
        pending.references,
      )
      if (!alive || session !== epoch) return
      if (pending.kind === kind.value) {
        draft.value = response.data
        saved.value = pending.signature
      } else {
        const cached = modeStates.value[pending.kind]
        if (cached) { cached.draft = response.data; cached.saved = pending.signature }
      }
      intent = undefined
      uncertain.value = false
      notice.value = '草稿已保存。本次保存不会发起生成或产生调用费用。'
      await loadDrafts()
    } catch (cause) {
      if (alive && session === epoch) {
        const code = (cause as { code?: number }).code
        uncertain.value =
          code === undefined ||
          code === 0 ||
          code === 408 ||
          (code >= 500 && code !== 601) ||
          (cause as { errorCode?: string }).errorCode === 'IDEMPOTENCY_IN_PROGRESS'
        if (!uncertain.value) intent = undefined
        error.value = cause instanceof Error ? cause.message : '草稿保存失败，请重试'
        autoSaveError.value = error.value
      }
    } finally {
      if (session === epoch) { saving.value = false; scheduleAutoSave() }
    }
  }
  const leave = () =>
    !locked.value &&
    !opening.value &&
    (!dirty.value || window.confirm('还有未保存的创作草稿，确定离开？'))
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (dirty.value || locked.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onBeforeRouteLeave(leave)
  onBeforeRouteUpdate((to, from) => {
    // 同项目内目录与筛选导航复用创作实例，不会丢弃草稿或原保存意图。
    if (to.path === from.path && to.params.id === projectId && from.params.id === projectId)
      return true
    return to.fullPath === from.fullPath || leave()
  })
  function stopReads() {
    stopAutoSave()
    sequence++
    draftSequence++
    viewEpoch++
    abort?.abort()
    models.value = []
    drafts.value = []
    total.value = 0
    draftTotal.value = 0
    loading.value = false
    draftsLoading.value = false
    opening.value = false
  }
  watch(
    () => auth.token,
    () => {
      epoch++
      stopReads()
      saving.value = false
      uncertain.value = false
      intent = undefined
      autoSaveError.value = ''
      modeStates.value = {}
      modelParameters.clear()
      draft.value = null
      preservedBody.value = null
      folderId.value = defaultFolder()
      references.value = []
      prompt.value = ''
      originalPrompt.value = ''
      selected.value = null
      selectedVersion.value = null
      parameters.value = {}
      kind.value = 'image'
      error.value = ''
      notice.value = ''
      saved.value = signature.value
      if (readable()) {
        void load()
        void loadDrafts()
      }
    },
    { flush: 'sync' },
  )
  watch(
    () => JSON.stringify(auth.user?.permissions || []),
    () => {
      stopReads()
      for (const state of Object.values(modeStates.value)) state.selected = null
      selected.value = null
      if (readable()) {
        void load()
        void loadDrafts()
      }
    },
    { flush: 'sync' },
  )
  onDeactivated(() => {
    active = false
    stopReads()
  })
  onActivated(() => {
    if (!active) {
      active = true
      scheduleAutoSave()
      void load()
      void loadDrafts()
    }
  })
  window.addEventListener('beforeunload', beforeUnload)
  onBeforeUnmount(() => {
    stopAutoSave()
    alive = false
    sequence++
    abort?.abort()
    window.removeEventListener('beforeunload', beforeUnload)
  })
  watch(prompt, () => {
    notice.value = ''
  })
  watch([signature, () => JSON.stringify(modeStates.value), opening, () => initial?.pauseAutoSave?.()], scheduleAutoSave)
  load()
  loadDrafts()
  scheduleAutoSave()
  return {
    autoSaveError,
    body,
    kind,
    drafts,
    draftPage,
    draftTotal,
    draftsLoading,
    opening,
    richPrompt,
    protectedReferenceKeys,
    missingModel,
    references,
    loadDrafts,
    openDraft,
    newDraft,
    prompt,
    promptDocument,
    models,
    selected,
    parameters,
    q,
    page,
    total,
    loading,
    saving,
    uncertain,
    locked,
    error,
    notice,
    draft,
    formRef,
    form,
    dirty,
    load,
    search,
    choose,
    setParameter,
    changeKind,
    save,
  }
}
