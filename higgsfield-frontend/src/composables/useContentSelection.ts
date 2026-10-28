import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
/** 选择与具体批量动作独立，操作再依据自身权限筛选。 */
export function useContentSelection(rows: () => { id: string }[], locked: () => boolean) {
  const auth = useAuthStore(), selected = ref<string[]>([])
  const allSelected = computed(() => rows().length > 0 && rows().every(item => selected.value.includes(item.id)))
  function toggle(id: string, checked: boolean) {
    if (locked() || !auth.token) return
    if (checked && rows().some(item => item.id === id)) selected.value = [...new Set([...selected.value, id])]
    else selected.value = selected.value.filter(value => value !== id)
  }
  function selectAll(checked: boolean) {
    if (!locked() && auth.token) selected.value = checked ? [...new Set(rows().map(item => item.id))] : []
  }
  watch(rows, values => { if (!locked()) selected.value = selected.value.filter(id => values.some(item => item.id === id)) })
  watch(() => auth.token, () => { selected.value = [] }, { flush: 'sync' })
  onBeforeUnmount(() => { selected.value = [] })
  return { selected, allSelected, toggle, selectAll }
}
