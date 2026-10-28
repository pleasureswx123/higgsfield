import { computed, onBeforeUnmount, onDeactivated, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import {
  listCredentials,
  getCredential,
  listCredentialVersions,
  listProviderAccounts,
  getProviderConnection,
  saveCredential,
} from '@/api/studio/credentials'

export function useCredentials() {
  const user = useUserStore()
  const allowed = (permission) =>
    user.permissions.includes('*:*:*') || user.permissions.includes(permission)
  const canCreate = computed(() => allowed('credential:write') && allowed('provider:read'))
  const canRotate = computed(() => allowed('credential:rotate') && allowed('provider:read'))
  const rows = ref([]),
    total = ref(0),
    page = ref(1),
    status = ref(''),
    loading = ref(false),
    error = ref('')
  const selected = ref(null),
    versions = ref([]),
    versionTotal = ref(0),
    versionPage = ref(1),
    versionsLoading = ref(false)
  const open = ref(false),
    pending = ref(false),
    preparing = ref(false),
    formRef = ref(),
    dialogError = ref('')
  const accounts = ref([]),
    accountTotal = ref(0),
    accountPage = ref(1),
    accountsLoading = ref(false)
  const connection = ref(null),
    rotating = ref(null)
  const form = reactive({
    name: '',
    accountId: '',
    ownerId: '',
    apiKey: '',
    validFrom: '',
    validUntil: '',
  })
  let alive = true,
    listTicket = 0,
    versionTicket = 0,
    accountTicket = 0,
    connectionTicket = 0
  let key = '',
    signature = '',
    dialogTicket = 0
  const message = (cause) => (cause instanceof Error ? cause.message : '操作失败，请重试')

  async function load() {
    const ticket = ++listTicket
    loading.value = true
    error.value = ''
    try {
      const result = await listCredentials({
        pageNum: page.value,
        pageSize: 20,
        status: status.value || undefined,
      })
      if (alive && ticket === listTicket) {
        rows.value = result.rows
        total.value = result.total
      }
    } catch (cause) {
      if (alive && ticket === listTicket) {
        rows.value = []
        error.value = message(cause)
      }
    } finally {
      if (alive && ticket === listTicket) loading.value = false
    }
  }
  async function loadVersions() {
    if (!selected.value) return
    const id = selected.value.id,
      ticket = ++versionTicket
    versionsLoading.value = true
    try {
      const result = await listCredentialVersions(id, { pageNum: versionPage.value, pageSize: 20 })
      if (alive && ticket === versionTicket) {
        versions.value = result.rows
        versionTotal.value = result.total
      }
    } catch (cause) {
      if (alive && ticket === versionTicket) {
        versions.value = []
        error.value = message(cause)
      }
    } finally {
      if (alive && ticket === versionTicket) versionsLoading.value = false
    }
  }
  function select(row) {
    selected.value = row
    versions.value = []
    versionTotal.value = 0
    versionPage.value = 1
    loadVersions()
  }
  async function loadAccounts() {
    const ticket = ++accountTicket
    accountsLoading.value = true
    try {
      const result = await listProviderAccounts({ pageNum: accountPage.value, pageSize: 20 })
      if (alive && ticket === accountTicket) {
        accounts.value = result.rows
        accountTotal.value = result.total
      }
    } catch (cause) {
      if (alive && ticket === accountTicket) dialogError.value = message(cause)
    } finally {
      if (alive && ticket === accountTicket) accountsLoading.value = false
    }
  }
  async function chooseAccount(account) {
    if (!account || account.status !== 'active' || pending.value) return
    form.accountId = account.id
    connection.value = null
    const ticket = ++connectionTicket
    preparing.value = true
    dialogError.value = ''
    try {
      const result = await getProviderConnection(account.connectionId)
      if (alive && ticket === connectionTicket && open.value) connection.value = result.data
    } catch (cause) {
      if (alive && ticket === connectionTicket) dialogError.value = message(cause)
    } finally {
      if (alive && ticket === connectionTicket) preparing.value = false
    }
  }
  async function start(row = null) {
    if (pending.value) return
    const ticket = ++dialogTicket
    rotating.value = row
    connection.value = null
    dialogError.value = ''
    key = ''
    signature = ''
    Object.assign(form, {
      name: row?.name || '',
      accountId: row?.accountId || '',
      ownerId: String(user.id),
      apiKey: '',
      validFrom: new Date().toISOString(),
      validUntil: '',
    })
    open.value = true
    accountPage.value = 1
    if (!row) await loadAccounts()
    if (row && alive && open.value && ticket === dialogTicket) {
      // 凭据只保存账号ID；轮换时按账号精确查询，不能依赖当前列表页。
      await prepareRotation(row, ticket)
    }
  }
  async function prepareRotation(row, ticket) {
    preparing.value = true
    try {
      const latest = await getCredential(row.id)
      if (!alive || !open.value || ticket !== dialogTicket) return
      rotating.value = latest.data
      const account = await listProviderAccounts({
        accountId: latest.data.accountId,
        pageNum: 1,
        pageSize: 1,
      })
      if (!alive || !open.value || ticket !== dialogTicket) return
      if (account.rows[0]?.id !== latest.data.accountId) throw new Error('无法定位凭据所属账号')
      await chooseAccount(account.rows[0])
    } catch (cause) {
      if (alive && open.value && ticket === dialogTicket) dialogError.value = message(cause)
    } finally {
      if (alive && ticket === dialogTicket) preparing.value = false
    }
  }
  function close() {
    if (pending.value) return
    open.value = false
    dialogTicket++
    form.apiKey = ''
    connectionTicket++
    accountTicket++
    preparing.value = false
  }
  async function submit() {
    if (
      pending.value ||
      preparing.value ||
      !connection.value?.currentVersion ||
      connection.value.status === 'disabled'
    )
      return
    if (!(await formRef.value?.validate().catch(() => false))) return
    pending.value = true
    dialogError.value = ''
    try {
      const data = {
        connectionVersionId: connection.value.currentVersion.id,
        apiKey: form.apiKey,
        validFrom: new Date(form.validFrom).toISOString(),
        validUntil: form.validUntil ? new Date(form.validUntil).toISOString() : null,
        ...(rotating.value
          ? { revision: rotating.value.revision }
          : { accountId: form.accountId, ownerId: form.ownerId, name: form.name.trim() }),
      }
      // 仅在内存保留摘要与幂等键，失败后重新输入相同内容仍使用原请求标识。
      const bytes = await crypto.subtle.digest(
        'SHA-256',
        new TextEncoder().encode(JSON.stringify(data))
      )
      const nextSignature = Array.from(new Uint8Array(bytes), (value) =>
        value.toString(16).padStart(2, '0')
      ).join('')
      if (nextSignature !== signature) {
        signature = nextSignature
        key = crypto.randomUUID()
      }
      await saveCredential(rotating.value?.id, data, key)
      if (!alive) return
      open.value = false
      await load()
      if (selected.value) await loadVersions()
    } catch (cause) {
      if (alive) dialogError.value = message(cause)
    } finally {
      form.apiKey = ''
      pending.value = false
    }
  }
  onBeforeRouteLeave(() => {
    if (pending.value || (open.value && !window.confirm('离开将清空未提交的凭据表单，是否继续？')))
      return false
    close()
    return true
  })
  onDeactivated(() => {
    form.apiKey = ''
    close()
  })
  const beforeUnload = (event) => {
    if (pending.value || (open.value && form.apiKey)) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => {
    load()
    window.addEventListener('beforeunload', beforeUnload)
  })
  onBeforeUnmount(() => {
    alive = false
    form.apiKey = ''
    key = ''
    signature = ''
    window.removeEventListener('beforeunload', beforeUnload)
  })
  return {
    canCreate,
    canRotate,
    rows,
    total,
    page,
    status,
    loading,
    error,
    selected,
    versions,
    versionTotal,
    versionPage,
    versionsLoading,
    open,
    pending,
    preparing,
    formRef,
    form,
    dialogError,
    accounts,
    accountTotal,
    accountPage,
    accountsLoading,
    connection,
    rotating,
    load,
    loadVersions,
    select,
    loadAccounts,
    chooseAccount,
    start,
    close,
    submit,
  }
}
