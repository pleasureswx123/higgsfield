import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import {
  listProviderConnections,
  getProviderConnection,
  listProviderAccounts,
  saveProviderConnection,
  createProviderAccount,
} from '@/api/studio/providers'

const initial = () => ({
  name: '',
  environment: 'test',
  baseUrl: '',
  adapterVersion: '',
  allowedHosts: '',
  connectTimeoutSeconds: 10,
  readTimeoutSeconds: 60,
  operationTimeoutSeconds: 120,
  taskTimeoutSeconds: 3600,
})

export function useProviders() {
  const user = useUserStore()
  const canWrite = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('provider:write')
  )
  const rows = ref([]),
    total = ref(0),
    page = ref(1),
    environment = ref(''),
    loading = ref(false),
    error = ref('')
  const selected = ref(null),
    accounts = ref([]),
    accountTotal = ref(0),
    accountPage = ref(1),
    accountsLoading = ref(false)
  const open = ref(false),
    accountOpen = ref(false),
    pending = ref(false),
    preparing = ref(false),
    dialogError = ref('')
  const editing = ref(null),
    formRef = ref(),
    accountFormRef = ref(),
    form = reactive(initial())
  const accountForm = reactive({ accountCode: '', region: '', upstreamProject: '' })
  let alive = true,
    listTicket = 0,
    accountTicket = 0,
    editTicket = 0,
    signature = '',
    key = ''
  const message = (cause) => (cause instanceof Error ? cause.message : '操作失败，请刷新后重试')

  async function load() {
    const ticket = ++listTicket
    loading.value = true
    error.value = ''
    try {
      const result = await listProviderConnections({
        pageNum: page.value,
        pageSize: 20,
        environment: environment.value || undefined,
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
  async function loadAccounts() {
    if (!selected.value) return
    const id = selected.value.id,
      ticket = ++accountTicket
    accountsLoading.value = true
    try {
      const result = await listProviderAccounts({
        connectionId: id,
        pageNum: accountPage.value,
        pageSize: 20,
      })
      if (alive && ticket === accountTicket) {
        accounts.value = result.rows
        accountTotal.value = result.total
      }
    } catch (cause) {
      if (alive && ticket === accountTicket) {
        accounts.value = []
        error.value = message(cause)
      }
    } finally {
      if (alive && ticket === accountTicket) accountsLoading.value = false
    }
  }
  function select(row) {
    if (pending.value || accountOpen.value) return
    selected.value = row
    accounts.value = []
    accountTotal.value = 0
    accountPage.value = 1
    loadAccounts()
  }
  async function start(row = null) {
    if (!alive || !canWrite.value || pending.value) return
    const ticket = ++editTicket
    preparing.value = false
    editing.value = row
    dialogError.value = ''
    signature = ''
    key = ''
    Object.assign(form, initial())
    open.value = true
    if (!row) return
    preparing.value = true
    try {
      const result = await getProviderConnection(row.id)
      if (!alive || !open.value || ticket !== editTicket) return
      editing.value = result.data
      const version = result.data.currentVersion
      if (!version) throw new Error('连接缺少配置版本，请联系管理员核查')
      Object.assign(form, {
        name: result.data.name,
        environment: result.data.environment,
        baseUrl: version.baseUrl,
        adapterVersion: version.adapterVersion,
        ...version.config,
        allowedHosts: version.config.allowedHosts.join('\n'),
      })
    } catch (cause) {
      if (alive && ticket === editTicket) {
        dialogError.value = message(cause)
        editing.value = null
        close()
        error.value = message(cause)
      }
    } finally {
      if (alive && ticket === editTicket) preparing.value = false
    }
  }
  function close() {
    if (!pending.value) {
      open.value = false
      accountOpen.value = false
      preparing.value = false
      editTicket++
    }
  }
  function startAccount() {
    if (!alive || !canWrite.value || !selected.value || selected.value.status === 'disabled' || pending.value) return
    dialogError.value = ''
    signature = ''
    key = ''
    Object.assign(accountForm, { accountCode: '', region: '', upstreamProject: '' })
    accountOpen.value = true
  }
  function idempotency(data, scope) {
    const next = JSON.stringify({ scope, data })
    if (next !== signature) {
      signature = next
      key = crypto.randomUUID()
    }
    return key
  }
  async function submit() {
    if (!alive || !canWrite.value || !open.value || pending.value || preparing.value)
      return
    pending.value = true
    dialogError.value = ''
    try {
      if (!(await formRef.value?.validate().catch(() => false))) return
      if (!alive || !canWrite.value || !open.value) return
      const data = {
        name: form.name.trim(),
        baseUrl: form.baseUrl,
        adapterVersion: form.adapterVersion,
        config: {
          allowedHosts: form.allowedHosts
            .split(/\r?\n/)
            .map((host) => host.trim())
            .filter(Boolean),
          bizId: 'op',
          connectTimeoutSeconds: form.connectTimeoutSeconds,
          readTimeoutSeconds: form.readTimeoutSeconds,
          operationTimeoutSeconds: form.operationTimeoutSeconds,
          taskTimeoutSeconds: form.taskTimeoutSeconds,
        },
        ...(editing.value
          ? { revision: editing.value.revision }
          : { environment: form.environment }),
      }
      const result = await saveProviderConnection(
        editing.value?.id,
        data,
        idempotency(data, editing.value?.id || 'create')
      )
      if (!alive) return
      open.value = false
      selected.value = result.data
      accountPage.value = 1
      await Promise.all([load(), loadAccounts()])
    } catch (cause) {
      if (alive) dialogError.value = message(cause)
    } finally {
      pending.value = false
    }
  }
  async function submitAccount() {
    if (
      !alive ||
      !canWrite.value ||
      !accountOpen.value ||
      pending.value ||
      !selected.value ||
      selected.value.status === 'disabled'
    )
      return
    pending.value = true
    dialogError.value = ''
    try {
      if (!(await accountFormRef.value?.validate().catch(() => false))) return
      if (!alive || !canWrite.value || !accountOpen.value) return
      const data = { connectionId: selected.value.id, ...accountForm }
      await createProviderAccount(data, idempotency(data, 'account'))
      if (!alive) return
      accountOpen.value = false
      accountPage.value = 1
      await loadAccounts()
    } catch (cause) {
      if (alive) dialogError.value = message(cause)
    } finally {
      pending.value = false
    }
  }
  onBeforeRouteLeave(() => {
    if (
      pending.value ||
      ((open.value || accountOpen.value) && !window.confirm('离开将丢弃未提交表单，是否继续？'))
    )
      return false
    close()
    return true
  })
  const beforeUnload = (event) => {
    if (pending.value || open.value || accountOpen.value) {
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
    window.removeEventListener('beforeunload', beforeUnload)
  })
  return {
    canWrite,
    rows,
    total,
    page,
    environment,
    loading,
    error,
    selected,
    accounts,
    accountTotal,
    accountPage,
    accountsLoading,
    open,
    accountOpen,
    pending,
    preparing,
    dialogError,
    editing,
    formRef,
    accountFormRef,
    form,
    accountForm,
    load,
    loadAccounts,
    select,
    start,
    close,
    startAccount,
    submit,
    submitAccount,
  }
}
