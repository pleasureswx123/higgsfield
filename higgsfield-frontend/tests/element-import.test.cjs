const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const { File } = require('node:buffer')
const ts = require('typescript')
const vue = require('vue')
class ApiError extends Error {
  constructor(message, code, errorCode) { super(message); this.code = code; this.errorCode = errorCode }
}
const fixture = () => ({
  id: '11',
  projectId: '9',
  revision: '2',
  status: 'validated',
  summary: { total: 1, valid: 1, invalid: 0 },
  errors: [],
})
const row = () => ({
  rowNo: 1,
  revision: '1',
  candidate: {
    schemaVersion: 1,
    name: '角色',
    alias: 'hero',
    category: 'character',
    description: '',
    propertyValues: [],
  },
  isSelected: true,
  issues: [],
  state: 'pending',
  sourceLocator: { line: 2 },
  elementId: null,
})
function setup(overrides = {}) {
  const visible = vue.ref(true)
  const permissions = vue.reactive({ canImport: true, canUpload: true, canCreate: true })
  const hooks = {},
    auth = vue.reactive({ token: 'one' })
  const api = {
    readElementImport: async () => ({ data: fixture() }),
    listElementImportRows: async () => ({ rows: [row()], total: 1 }),
    ...overrides,
  }
  const exports = {}
  const source = readFileSync(join(__dirname, '../src/composables/useElementImport.ts'), 'utf8')
  runInNewContext(
    ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
    {
      exports,
      Error,
      AbortController,
      File,
      crypto: { randomUUID },
      require(name) {
        if (name === 'vue')
          return {
            ...vue,
            onBeforeUnmount: (fn) => {
              hooks.unmount = fn
            },
            onDeactivated: (fn) => {
              hooks.deactivate = fn
            },
            onActivated: (fn) => {
              hooks.activate = fn
            },
          }
        if (name === 'vue-router')
          return {
            onBeforeRouteLeave: (fn) => {
              hooks.leave = fn
            },
            onBeforeRouteUpdate: (fn) => {
              hooks.update = fn
            },
          }
        if (name === '@/stores/auth') return { useAuthStore: () => auth }
        if (name === '@/api/client') return { ApiError }
        if (name === 'element-plus') return { ElMessageBox: { confirm: overrides.confirmDiscard || (async () => {}) } }
        return api
      },
    },
  )
  const scope = vue.effectScope()
  const state = scope.run(() =>
    exports.useElementImport(
      '9',
      () => {},
      () => permissions,
      () => visible.value,
    ),
  )
  state.form.value = { validate: async () => true, clearValidate() {} }
  return {
    visible,
    state,
    permissions,
    hooks,
    auth,
    close: () => {
      hooks.unmount()
      scope.stop()
    },
  }
}
test('编辑副本不修改列表；保存丢失响应后重试沿用键，成功后刷新所有诊断', async () => {
  const calls = []
  const { state: s, close } = setup({
    editElementImportRow: async (...args) => {
      calls.push(args)
      if (calls.length === 1) throw new Error('响应丢失')
      return { data: {} }
    },
  })
  s.batchId.value = '11'
  await s.refresh()
  s.edit(s.rows.value[0])
  s.editing.value.candidate.name = '修改'
  s.editing.value.isSelected = false
  assert.equal(s.rows.value[0].candidate.name, '角色')
  await s.save()
  assert.equal(s.editing.value.candidate.name, '修改')
  await s.save()
  assert.equal(s.editing.value, undefined)
  assert.equal(calls[0][2], calls[1][2])
  assert.equal(calls[0][1].revision, '1')
  assert.equal(calls[0][1].isSelected, false)
  close()
})
test('确认须显式复核且携带批次版本，响应丢失重试沿用幂等键', async () => {
  const calls = []
  const { state: s, close } = setup({
    confirmElementImport: async (...args) => {
      calls.push(args)
      if (calls.length === 1) throw new Error('响应丢失')
      return { data: { createdCount: 1 } }
    },
  })
  s.batchId.value = '11'
  await s.refresh()
  await s.confirm()
  assert.equal(calls.length, 0)
  s.confirmed.value = true
  await s.confirm()
  await s.confirm()
  assert.equal(calls.length, 1)
  assert.equal(s.needsRefresh.value, true)
  await s.refresh()
  s.confirmed.value = true
  await s.confirm()
  assert.equal(calls[0][1], '2')
  assert.equal(calls[0][2], calls[1][2])
  assert.match(s.result.value, /1/)
  assert.equal(s.confirmed.value, false)
  close()
})

test('保存成功后刷新失败时禁用旧候选和确认，刷新成功才能恢复', async () => {
  let failRead = false,
    confirms = 0
  const { state: s, close } = setup({
    editElementImportRow: async () => {
      failRead = true
      return { data: {} }
    },
    readElementImport: async () => {
      if (failRead) throw new Error('断网')
      return { data: fixture() }
    },
    confirmElementImport: async () => {
      confirms++
      return { data: { createdCount: 1 } }
    },
  })
  s.batchId.value = '11'
  await s.refresh()
  const old = s.rows.value[0]
  s.confirmed.value = true
  s.edit(old)
  await s.save()
  assert.equal(s.editing.value, undefined)
  assert.equal(s.needsRefresh.value, true)
  assert.equal(s.rows.value.length, 0)
  s.edit(old)
  assert.equal(s.editing.value, undefined)
  s.confirmed.value = true
  await s.confirm()
  assert.equal(confirms, 0)
  failRead = false
  await s.refresh()
  assert.equal(s.needsRefresh.value, false)
  assert.equal(s.confirmed.value, false)
  close()
})

test('确认成功后刷新失败仍显示已完成，不提供第二次创建', async () => {
  let failRead = false,
    confirms = 0
  const { state: s, close } = setup({
    readElementImport: async () => {
      if (failRead) throw new Error('断网')
      return { data: fixture() }
    },
    confirmElementImport: async () => {
      confirms++
      failRead = true
      return { data: { createdCount: 1 } }
    },
  })
  s.batchId.value = '11'
  await s.refresh()
  s.confirmed.value = true
  await s.confirm()
  assert.equal(s.batch.value.status, 'finished')
  assert.equal(s.needsRefresh.value, true)
  assert.match(s.result.value, /已创建/)
  s.confirmed.value = true
  await s.confirm()
  assert.equal(confirms, 1)
  close()
})

test('读取期间批次版本变化重读整页，持续变化不展示混合修订数据', async () => {
  let revision = 1,
    stable = false,
    reads = 0
  const { state: s, close } = setup({
    readElementImport: async () => ({
      data: { ...fixture(), revision: String(stable ? revision : revision++) },
    }),
    listElementImportRows: async () => {
      reads++
      return { rows: [row()], total: 1 }
    },
  })
  s.batchId.value = '11'
  await s.refresh()
  assert.equal(reads, 2)
  assert.equal(s.rows.value.length, 0)
  assert.equal(s.needsRefresh.value, true)
  assert.ok(s.error.value)
  stable = true
  await s.refresh()
  assert.equal(s.needsRefresh.value, false)
  assert.equal(s.rows.value.length, 1)
  close()
})
test('切换账号取消旧请求并清除候选，拒绝其他项目的批次', async () => {
  let resolve, signal
  const {
    state: s,
    auth,
    close,
  } = setup({
    readElementImport: (id, current) => {
      signal = current
      return new Promise((done) => {
        resolve = done
      })
    },
  })
  s.batchId.value = '11'
  const pending = s.refresh()
  auth.token = 'two'
  await vue.nextTick()
  assert.equal(signal.aborted, true)
  resolve({ data: fixture() })
  await pending
  assert.equal(s.batch.value, undefined)
  assert.equal(s.rows.value.length, 0)
  close()
  const other = setup({
    readElementImport: async () => ({ data: { ...fixture(), projectId: '88' } }),
  })
  other.state.batchId.value = '11'
  await other.state.refresh()
  assert.equal(other.state.batch.value, undefined)
  assert.ok(other.state.error.value)
  other.close()
})
test('上传重试固定前缀与幂等键，读取实时分片状态跳过已上传分片', async () => {
  const imports = [],
    parts = []
  const { state: s, close } = setup({
    hashBlob: async () => 'a'.repeat(64),
    createUpload: async () => ({ data: { id: '77' } }),
    readUpload: async () => ({
      data: { state: 'uploading', partSize: '2', partCount: 2, receivedParts: [1] },
    }),
    putUploadPart: async (id, part) => {
      parts.push(part)
    },
    completeUpload: async () => ({}),
    createElementImport: async (...args) => {
      imports.push(args)
      if (imports.length === 1) throw new Error('响应丢失')
      return { data: { id: '11' } }
    },
  })
  s.selectFile(new File(['1234'], 'elements.csv'))
  await s.upload()
  s.includeProjectName.value = false
  await s.upload()
  assert.equal(imports[0][2], true)
  assert.equal(imports[1][2], true)
  assert.equal(imports[0][3], imports[1][3])
  assert.deepEqual(parts, [2, 2])
  assert.equal(s.batch.value.id, '11')
  close()
})

test('TXT、MD和DOCX按扩展名统一声明类型，浏览器空MIME不影响上传', async () => {
  for (const [extension, mime] of [
    ['txt', 'text/plain'],
    ['md', 'text/markdown'],
    ['docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    ['pdf', 'application/pdf'],
  ]) {
    let uploaded
    const { state: s, close } = setup({
      hashBlob: async () => 'a'.repeat(64),
      createUpload: async (project, file) => {
        uploaded = file
        return { data: { id: '77' } }
      },
      readUpload: async () => ({ data: { state: 'ready' } }),
      createElementImport: async () => ({ data: { id: '11' } }),
    })
    s.selectFile(new File(['角色：记者'], `script.${extension}`))
    await s.upload()
    assert.equal(uploaded.type, mime)
    assert.equal(await uploaded.text(), '角色：记者')
    assert.equal(s.batch.value.id, '11')
    close()
  }
})

const flush = () => new Promise((resolve) => setImmediate(resolve))
function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}

test('上传会话迟到响应不能污染新账号，新账号可立即选择新文件', async () => {
  const pending = deferred(),
    creates = [],
    reads = []
  const h = setup({
    hashBlob: async () => 'hash',
    createUpload: async (...args) => {
      creates.push(args)
      return creates.length === 1 ? pending.promise : { data: { id: 'new' } }
    },
    readUpload: async (id) => {
      reads.push(id)
      return { data: { state: 'ready' } }
    },
    createElementImport: async () => ({ data: { id: '11' } }),
  })
  h.state.selectFile(new File(['a'], 'old.csv'))
  const old = h.state.upload()
  await flush()
  h.auth.token = 'two'
  assert.equal(h.state.started.value, false)
  assert.equal(h.state.busy.value, false)
  h.state.selectFile(new File(['b'], 'new.csv'))
  const current = h.state.upload()
  await current
  pending.resolve({ data: { id: 'old' } })
  await old
  assert.equal(reads.join(','), 'new')
  assert.equal(h.state.fileName.value, 'new.csv')
  assert.equal(h.state.batch.value.id, '11')
  h.close()
})

test('停用时取消导入分片后续发送，恢复后继续原文件且重新读取分片', async () => {
  const part = deferred()
  let sends = 0,
    completes = 0,
    reads = 0
  const h = setup({
    hashBlob: async () => 'hash',
    createUpload: async () => ({ data: { id: 'up' } }),
    readUpload: async () => {
      reads++
      return {
        data: {
          state: 'uploading',
          partSize: '1',
          partCount: 2,
          receivedParts: reads === 1 ? [] : [1],
        },
      }
    },
    putUploadPart: async () => {
      sends++
      if (sends === 1) await part.promise
    },
    completeUpload: async () => {
      completes++
    },
    createElementImport: async () => ({ data: { id: '11' } }),
  })
  h.state.selectFile(new File(['ab'], 'parts.csv'))
  const first = h.state.upload()
  await flush()
  assert.equal(sends, 1)
  h.hooks.deactivate()
  part.resolve()
  await first
  assert.equal(sends, 1)
  assert.equal(completes, 0)
  assert.equal(h.state.active.value, false)
  await h.state.upload()
  assert.equal(reads, 1)
  h.hooks.activate()
  await h.state.upload()
  assert.equal(reads, 2)
  assert.equal(sends, 2)
  assert.equal(completes, 1)
  h.close()
})

test('撤销上传权限停止后续分片，恢复权限后沿用原会话继续', async () => {
  const part = deferred()
  let sends = 0,
    complete = 0,
    reads = 0
  const h = setup({
    hashBlob: async () => 'hash',
    createUpload: async () => ({ data: { id: 'up' } }),
    readUpload: async () => ({
      data: {
        state: 'uploading',
        partSize: '1',
        partCount: 2,
        receivedParts: ++reads === 1 ? [] : [1],
      },
    }),
    putUploadPart: async () => {
      if (++sends === 1) await part.promise
    },
    completeUpload: async () => {
      complete++
    },
    createElementImport: async () => ({ data: { id: '11' } }),
  })
  h.state.selectFile(new File(['ab'], 'roles.csv'))
  const run = h.state.upload()
  await flush()
  h.permissions.canUpload = false
  part.resolve()
  await run
  assert.equal(sends, 1)
  assert.equal(complete, 0)
  await h.state.upload()
  assert.equal(reads, 1)
  h.permissions.canUpload = true
  await h.state.upload()
  assert.equal(sends, 2)
  assert.equal(complete, 1)
  h.close()
})

test('撤销导入权限清除复核内容并阻止读取写入，创建权限单独约束确认', async () => {
  let reads = 0,
    confirms = 0,
    saves = 0
  const h = setup({
    readElementImport: async () => {
      reads++
      return { data: fixture() }
    },
    confirmElementImport: async () => {
      confirms++
      return { data: { createdCount: 1 } }
    },
    editElementImportRow: async () => {
      saves++
      return { data: {} }
    },
  })
  h.state.batchId.value = '11'
  await h.state.refresh()
  h.state.edit(h.state.rows.value[0])
  h.permissions.canImport = false
  assert.equal(h.state.batch.value, undefined)
  assert.equal(h.state.editing.value, undefined)
  assert.equal(h.state.rows.value.length, 0)
  const prior = reads
  await h.state.refresh()
  await h.state.save()
  await h.state.confirm()
  assert.equal(reads, prior)
  assert.equal(saves, 0)
  assert.equal(confirms, 0)
  h.permissions.canImport = true
  await h.state.refresh()
  h.permissions.canCreate = false
  await h.state.refresh()
  h.state.confirmed.value = true
  await h.state.confirm()
  assert.equal(confirms, 0)
  h.permissions.canCreate = true
  await h.state.refresh()
  h.state.confirmed.value = true
  await h.state.confirm()
  assert.equal(confirms, 1)
  h.close()
})

test('候选保存未知时冻结正文选择与修订，隐藏返回后仍确认原请求', async () => {
  const calls = []
  const c = setup({ editElementImportRow: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('中断'); return { data: {} } } })
  c.state.batchId.value = '11'; await c.state.refresh(); c.state.edit(c.state.rows.value[0])
  c.state.editing.value.candidate.name = '原候选'; c.state.editing.value.isSelected = false
  await c.state.save(); assert.equal(c.state.editUncertain.value, true)
  c.hooks.deactivate(); c.hooks.activate()
  c.state.editing.value.candidate.name = '意外修改'; c.state.editing.value.revision = '99'; c.state.editing.value.isSelected = true
  await c.state.save()
  assert.equal(calls[1][1].candidate.name, '原候选'); assert.equal(calls[1][1].revision, '1')
  assert.equal(calls[1][1].isSelected, false); assert.equal(calls[1][2], calls[0][2])
  assert.equal(c.state.editUncertain.value, false); c.close()
})

test('候选明确拒绝允许修正，处理中和超时维持原请求锁定', async () => {
  for (const [code, errorCode, uncertain] of [[601, 'REVISION_CONFLICT', false], [601, 'IDEMPOTENCY_IN_PROGRESS', true], [408, '', true]]) {
    const c = setup({ editElementImportRow: async () => { throw new ApiError('拒绝', code, errorCode) } })
    c.state.batchId.value = '11'; await c.state.refresh(); c.state.edit(c.state.rows.value[0])
    c.state.editing.value.candidate.name = '保留候选'; await c.state.save()
    assert.equal(c.state.editUncertain.value, uncertain)
    assert.equal(c.state.editing.value.candidate.name, '保留候选')
    c.auth.token = 'two'; assert.equal(c.state.editUncertain.value, false); assert.equal(c.state.editing.value, undefined)
    c.close()
  }
})

test('候选放弃确认取消保留输入，确认后退出编辑而不修改列表', async () => {
  let accepted = false
  const c = setup({ confirmDiscard: async () => { if (!accepted) throw new Error('取消') } })
  c.state.batchId.value = '11'; await c.state.refresh(); c.state.edit(c.state.rows.value[0])
  assert.equal(await c.state.confirmClose(), true)
  c.state.editing.value.candidate.name = '未保存'
  await c.state.discardEdit(); assert.equal(c.state.editing.value.candidate.name, '未保存')
  assert.equal(await c.hooks.leave(), false)
  accepted = true; await c.state.discardEdit()
  assert.equal(c.state.editing.value, undefined); assert.equal(c.state.rows.value[0].candidate.name, '角色')
  c.close()
})

test('候选校验期间放弃或隐藏不提交，旧确认不丢弃返回后的修改', async () => {
  let validate, confirm, writes = 0
  const c = setup({ editElementImportRow: async () => { writes++; return { data: {} } }, confirmDiscard: () => new Promise(done => { confirm = done }) })
  c.state.batchId.value = '11'; await c.state.refresh(); c.state.edit(c.state.rows.value[0])
  c.state.form.value.validate = () => new Promise(done => { validate = done })
  const saving = c.state.save(); await c.state.discardEdit(); validate(true); await saving
  assert.equal(writes, 0)
  c.state.edit(c.state.rows.value[0]); c.state.editing.value.candidate.name = '保留'
  const discarding = c.state.discardEdit(); c.hooks.deactivate(); c.hooks.activate(); confirm(); await discarding
  assert.equal(c.state.editing.value.candidate.name, '保留')
  const late = c.state.save(); c.auth.token = 'two'; validate(true); await late
  assert.equal(writes, 0); c.close()
})

test('导入页签显隐取消当前读取，保留批次与候选草稿并隔离旧校验',async()=>{
 const reads=[],writes=[]
 const h=setup({readElementImport:(id,signal)=>new Promise(resolve=>reads.push({id,signal,resolve})),editElementImportRow:async(...args)=>writes.push(args)})
 h.state.batchId.value='11';const reading=h.state.refresh()
 h.visible.value=false;assert.equal(reads[0].signal.aborted,true)
 reads[0].resolve({data:fixture()});await reading
 assert.equal(h.state.batchId.value,'11');assert.equal(h.state.batch.value,undefined)
 await h.state.refresh();assert.equal(reads.length,1)
 h.visible.value=true;h.state.batch.value=fixture();h.state.needsRefresh.value=false;h.state.edit(row())
 h.state.editing.value.candidate.name='未保存候选';let validate
 h.state.form.value={validate:()=>new Promise(resolve=>{validate=resolve})}
 const save=h.state.save();h.visible.value=false;h.visible.value=true;validate(true);await save
 assert.equal(writes.length,0);assert.equal(h.state.editing.value.candidate.name,'未保存候选')
 h.hooks.deactivate();h.visible.value=false;h.visible.value=true
 assert.equal(h.state.active.value,false);h.hooks.activate();assert.equal(h.state.active.value,true)
 assert.equal(h.state.batchId.value,'11');assert.equal(h.state.needsRefresh.value,true)
 h.close()
})

test('候选表单校验期间修改内容不提交，重新校验后保存新内容',async()=>{
 const writes=[];const h=setup({editElementImportRow:async(...args)=>{writes.push(args);return {data:{}}}})
 h.state.batchId.value='11';await h.state.refresh();h.state.edit(h.state.rows.value[0]);let validate
 h.state.form.value={validate:()=>new Promise(resolve=>validate=resolve)}
 const operation=h.state.save();h.state.editing.value.candidate.alias='changed';validate(true);await operation
 assert.equal(writes.length,0);assert.equal(h.state.editing.value.candidate.alias,'changed')
 h.state.form.value={validate:async()=>true};await h.state.save();assert.equal(writes.length,1);assert.equal(writes[0][1].candidate.alias,'changed');h.close()
})

test('放弃确认期间继续修改候选，旧确认不得丢弃新内容',async()=>{
 let confirm;const h=setup({confirmDiscard:()=>new Promise(resolve=>confirm=resolve)})
 h.state.batchId.value='11';await h.state.refresh();h.state.edit(h.state.rows.value[0]);h.state.editing.value.candidate.name='第一次'
 const operation=h.state.discardEdit();h.state.editing.value.candidate.name='继续修改';confirm();await operation
 assert.equal(h.state.editing.value.candidate.name,'继续修改');h.close()
})
