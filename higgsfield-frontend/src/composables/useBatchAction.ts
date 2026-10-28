import { computed, onActivated, onDeactivated, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox } from 'element-plus'
export interface BatchItem { id: string; name: string }
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'

/** 批量操作逐项执行，保留失败项及其幂等键，已成功项不重复提交。 */
export function useBatchAction<T extends BatchItem>(rows: () => T[], allowed: () => boolean, refresh: () => Promise<void>, executeItem: (item: T, key: string) => Promise<unknown>, eligibleItem: (item: T) => boolean, label: string, verb: string, warning: string, selection?: Ref<string[]>, options: { confirm?: boolean; preserveSelection?: boolean } = {}) {
  const auth = useAuthStore(), selected = selection || ref<string[]>([]), pending = ref(false), message = ref('')
  const eligible = computed(() => rows().filter(eligibleItem))
  const allSelected = computed(() => eligible.value.length > 0 && eligible.value.every(item => selected.value.includes(item.id)))
  const intents = new Map<string, { item: T; key: string }>()
  let epoch = 0, interaction = 0, active = true
  function toggle(id: string, checked: boolean) {
    if (!active || pending.value || !allowed()) return
    if (checked && eligible.value.some(item => item.id === id)) selected.value = [...new Set([...selected.value, id])]
    else selected.value = selected.value.filter(value => value !== id)
  }
  function selectAll(checked: boolean) {
    if (!active || pending.value || !allowed()) return
    selected.value = checked ? eligible.value.map(item => item.id) : []
  }
  async function execute() {
    if (!active || !auth.token || !allowed() || pending.value) return
    const ticket = epoch, viewTicket = interaction
    const items = eligible.value.filter(item => selected.value.includes(item.id)).map(item => ({ ...item }))
    if (!items.length) return
    pending.value = true; message.value = ''
    try {
      try { if (options.confirm !== false) await ElMessageBox.confirm(`${verb}选中的 ${items.length} 个${label}？${warning}`, `批量${verb}${label}`, { confirmButtonText: `${verb}所选`, cancelButtonText: '取消' }) }
      catch { return }
      if (!active || ticket !== epoch || viewTicket !== interaction || !allowed()) return
      let success = 0
      const failures: string[] = []
      for (const item of items) {
        if (!active || ticket !== epoch || viewTicket !== interaction || !allowed()) break
        // 未确认结果的条目继续使用最初的修订和请求键，不重新覆盖并发修改。
        let intent = intents.get(item.id)
        if (!intent) { intent = { item, key: crypto.randomUUID() }; intents.set(item.id, intent) }
        try {
          await executeItem(intent.item, intent.key)
          if (ticket !== epoch) return
          success++; intents.delete(item.id)
          if (!options.preserveSelection) selected.value = selected.value.filter(id => id !== item.id)
        } catch (cause) {
          if (ticket !== epoch) return
          if (cause instanceof ApiError && ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))) intents.delete(item.id)
          failures.push(`${item.name}：${cause instanceof Error ? cause.message : `${verb}失败`}`)
        }
      }
      if (ticket !== epoch) return
      const remaining = items.length - success - failures.length
      message.value = `已${verb} ${success} 个${label}。${remaining ? `页面停用或权限变化，剩余 ${remaining} 项未执行。` : ''}${failures.length ? `失败 ${failures.length} 项：${failures.join('；')}` : ''}`
      try { if (active && allowed()) await refresh() }
      catch { if (ticket === epoch) message.value += '列表刷新失败，请手动刷新。' }
      if (ticket === epoch) selected.value = selected.value.filter(id => rows().some(item => item.id === id && (selection || eligibleItem(item))))
    } finally { if (ticket === epoch) pending.value = false }
  }
  watch(rows, values => { if (!pending.value) selected.value = selected.value.filter(id => values.some(item => item.id === id && (selection || eligibleItem(item)))) })
  function clear() { epoch++; selected.value = []; intents.clear(); pending.value = false; message.value = '' }
  watch(() => auth.token, clear, { flush: 'sync' })
  watch(allowed, value => { if (!value) interaction++ }, { flush: 'sync' })
  onDeactivated(() => { active = false; interaction++ })
  onActivated(() => { active = true })
  onBeforeRouteLeave(() => !pending.value)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || !pending.value)
  onBeforeUnmount(clear)
  return { selected, pending, message, allSelected, toggle, selectAll, execute }
}

