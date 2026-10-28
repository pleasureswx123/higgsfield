import { onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import {
  listModels,
  listModelVersions,
  getModelVersion,
  listModelVariants,
} from '@/api/studio/models'

export function useModels() {
  const filters = reactive({ connectionId: '', kind: '' }),
    formRef = ref(),
    model = ref(),
    version = ref()
  const section = () => reactive({ rows: [], page: 1, total: 0, loading: false, error: '' })
  const models = section(),
    versions = section(),
    variants = section()
  const controllers = new Map()
  let active = false,
    detailController
  function clear(state) {
    controllers.get(state)?.abort()
    controllers.delete(state)
    state.rows = []
    state.total = 0
    state.loading = false
    state.error = ''
  }
  function clearVersion() {
    detailController?.abort()
    version.value = undefined
    clear(variants)
  }
  function clearModel() {
    model.value = undefined
    clear(versions)
    clearVersion()
  }
  function clearAll() {
    clear(models)
    clearModel()
  }
  async function read(state, fetcher) {
    clear(state)
    if (!active) return
    const controller = new AbortController()
    controllers.set(state, controller)
    state.loading = true
    try {
      const result = await fetcher({ pageNum: state.page, pageSize: 20 }, controller.signal)
      if (!controller.signal.aborted) {
        state.rows = result.rows
        state.total = result.total
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        state.error = cause instanceof Error ? cause.message : '模型读取失败'
    } finally {
      if (controllers.get(state) === controller) state.loading = false
    }
  }
  async function load() {
    clearModel()
    await read(models, (params, signal) =>
      listModels(
        {
          ...params,
          connectionId: filters.connectionId || undefined,
          kind: filters.kind || undefined,
        },
        signal
      )
    )
  }
  async function search() {
    clearAll()
    if (!(await formRef.value?.validate().catch(() => false))) return
    models.page = 1
    await load()
  }
  async function loadVersions() {
    clearVersion()
    const id = model.value?.id
    if (id) await read(versions, (params, signal) => listModelVersions(id, params, signal))
  }
  async function selectModel(row) {
    clearModel()
    model.value = row
    versions.page = 1
    await loadVersions()
  }
  async function loadVariants() {
    const id = version.value?.id
    if (id) await read(variants, (params, signal) => listModelVariants(id, params, signal))
  }
  async function selectVersion(row) {
    clearVersion()
    if (!active) return
    const controller = new AbortController()
    detailController = controller
    variants.loading = true
    try {
      const result = await getModelVersion(row.id, controller.signal)
      if (controller.signal.aborted) return
      version.value = result.data
      variants.page = 1
      await loadVariants()
    } catch (cause) {
      if (!controller.signal.aborted)
        variants.error = cause instanceof Error ? cause.message : '能力详情读取失败'
    } finally {
      if (detailController === controller) variants.loading = false
    }
  }
  function activate() {
    if (!active) {
      active = true
      void load()
    }
  }
  function deactivate() {
    active = false
    clearAll()
  }
  watch(filters, clearAll, { flush: 'sync' })
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  return {
    filters,
    formRef,
    model,
    version,
    models,
    versions,
    variants,
    search,
    load,
    loadVersions,
    selectModel,
    selectVersion,
    loadVariants,
  }
}
