import {
  computed,
  reactive,
  ref,
  watch,
  onMounted,
  onActivated,
  onDeactivated,
  onBeforeUnmount,
} from 'vue'
import useUserStore from '@/store/modules/user'
import {
  listPriceBooks,
  listPriceVersions,
  getPriceVersion,
  listPriceHistory,
} from '@/api/studio/prices'
import { validRoutingId } from '@/utils/routing'

export function usePrices() {
  const user = useUserStore()
  const allowed = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:read')
  )
  const filters = reactive({ modelVariantId: '', purpose: '', accountId: '', currency: '' })
  const section = () => reactive({ rows: [], total: 0, page: 1, loading: false, error: '' })
  const books = section(),
    versions = section(),
    history = section(),
    book = ref(),
    version = ref(),
    detailError = ref(''),
    detailLoading = ref(false)
  const controllers = new Map()
  let active = false
  function clear(name, state) {
    controllers.get(name)?.abort()
    controllers.delete(name)
    Object.assign(state, { rows: [], total: 0, page: 1, loading: false, error: '' })
  }
  function clearDetail() {
    controllers.get('detail')?.abort()
    controllers.delete('detail')
    version.value = undefined
    detailError.value = ''
    detailLoading.value = false
    clear('history', history)
  }
  function clearVersions() {
    clearDetail()
    clear('versions', versions)
    book.value = undefined
  }
  async function page(name, state, request) {
    if (!active || !allowed.value) return
    controllers.get(name)?.abort()
    const current = new AbortController()
    controllers.set(name, current)
    state.loading = true
    state.rows = []
    state.total = 0
    state.error = ''
    try {
      const result = await request(current.signal)
      if (controllers.get(name) === current) {
        state.rows = result.rows
        state.total = result.total
      }
    } catch (cause) {
      if (controllers.get(name) === current) state.error = cause?.message || '读取失败'
    } finally {
      if (controllers.get(name) === current) state.loading = false
    }
  }
  function loadBooks() {
    clearVersions()
    for (const name of ['modelVariantId', 'accountId']) {
      if (filters[name] && !validRoutingId(filters[name])) {
        clear('books', books)
        books.error = '请输入有效的规格或账号ID'
        return
      }
    }
    if (filters.currency && !/^[A-Z]{3}$/.test(filters.currency)) {
      clear('books', books)
      books.error = '币种须为三个大写字母'
      return
    }
    const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''))
    return page('books', books, (signal) =>
      listPriceBooks({ ...params, pageNum: books.page, pageSize: 20 }, signal)
    )
  }
  function search() {
    books.page = 1
    return loadBooks()
  }
  function loadVersions() {
    clearDetail()
    if (!book.value) return
    const id = book.value.id
    return page('versions', versions, (signal) =>
      listPriceVersions({ priceBookId: id, pageNum: versions.page, pageSize: 20 }, signal)
    )
  }
  function selectBook(row) {
    clearVersions()
    book.value = row
    return loadVersions()
  }
  function loadHistory() {
    if (!version.value) return
    const id = version.value.id
    return page('history', history, (signal) =>
      listPriceHistory(id, { pageNum: history.page, pageSize: 20 }, signal)
    )
  }
  async function selectVersion(row) {
    clearDetail()
    if (!active || !allowed.value) return
    const current = new AbortController()
    controllers.set('detail', current)
    detailLoading.value = true
    try {
      const result = await getPriceVersion(row.id, current.signal)
      if (controllers.get('detail') !== current) return
      version.value = result.data
      await loadHistory()
    } catch (cause) {
      if (controllers.get('detail') === current)
        detailError.value = cause?.message || '读取版本失败'
    } finally {
      if (controllers.get('detail') === current) detailLoading.value = false
    }
  }
  function reset() {
    clear('books', books)
    clearVersions()
  }
  watch(filters, reset, { flush: 'sync' })
  watch(
    allowed,
    (value) => {
      reset()
      if (value && active) loadBooks()
    },
    { flush: 'sync' }
  )
  function activate() {
    if (!active) {
      active = true
      loadBooks()
    }
  }
  function deactivate() {
    active = false
    reset()
  }
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  return {
    filters,
    books,
    versions,
    history,
    book,
    version,
    detailError,
    detailLoading,
    allowed,
    search,
    loadBooks,
    selectBook,
    loadVersions,
    selectVersion,
    loadHistory,
  }
}
