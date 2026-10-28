import { computed, ref, onDeactivated, onBeforeUnmount, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { getRouting, saveRouting } from '@/api/studio/routing'
import { validRoutingId, routingPayload } from '@/utils/routing'

export function useRouting() {
  const user = useUserStore()
  const allowed = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('provider:route')
  )
  const projectId = ref(''),
    revision = ref(''),
    routes = ref([]),
    loading = ref(false),
    pending = ref(false),
    error = ref(''),
    message = ref(''),
    formRef = ref()
  let controller,
    loadedId = '',
    signature = '',
    key = '',
    epoch = 0,
    alive = true
  function clear() {
    epoch++
    controller?.abort()
    controller = undefined
    loading.value = false
    revision.value = ''
    routes.value = []
    loadedId = ''
    error.value = ''
    message.value = ''
  }
  watch(projectId, clear, { flush: 'sync' })
  watch(allowed, (value) => {
    if (!value) clear()
  }, { flush: 'sync' })
  async function load() {
    if (pending.value || !allowed.value || !alive) return
    clear()
    if (!validRoutingId(projectId.value)) {
      error.value = '请输入有效的项目ID'
      return
    }
    const id = projectId.value,
      current = new AbortController()
    controller = current
    loading.value = true
    try {
      const response = await getRouting(id, current.signal)
      if (controller !== current || !alive) return
      loadedId = id
      revision.value = response.data.revision
      routes.value = response.data.routes
    } catch (cause) {
      if (controller === current && alive) error.value = cause?.message || '读取失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  async function save() {
    if (
      !alive ||
      pending.value ||
      loading.value ||
      !allowed.value ||
      loadedId !== projectId.value ||
      !revision.value
    )
      return
    pending.value = true
    const ticket = epoch, id = loadedId
    error.value = ''
    message.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (!alive || !allowed.value || ticket !== epoch || loadedId !== projectId.value) return
      const data = routingPayload(revision.value, routes.value)
      const next = JSON.stringify({ id, data })
      if (signature !== next) {
        signature = next
        key = crypto.randomUUID()
      }
      const response = await saveRouting(id, data, key)
      if (alive && allowed.value && ticket === epoch && loadedId === id) {
        revision.value = response.data.revision
        routes.value = response.data.routes
        message.value = '项目路由已保存'
      }
    } catch (cause) {
      if (alive && allowed.value && ticket === epoch && loadedId === id)
        error.value = cause?.message || '保存结果未确认，请核对后重试'
    } finally {
      if (alive) pending.value = false
    }
  }
  onBeforeRouteLeave(() => !pending.value)
  onDeactivated(clear)
  onBeforeUnmount(() => {
    alive = false
    clear()
  })
  return {
    allowed,
    projectId,
    revision,
    routes,
    loading,
    pending,
    error,
    message,
    formRef,
    load,
    save,
  }
}
