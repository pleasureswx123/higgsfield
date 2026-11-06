const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(resolve => setImmediate(resolve))
class ApiError extends Error { constructor(code) { super('权限失效'); this.code = code } }
const row = (id, state = 'submitting', folderId = '9') => ({ id, projectId:'2', folderId, kind:'image', createTime:new Date().toISOString(), promptExcerpt:`图片${id}`, orchestrationState:state, upstreamState:'running', requestState:'awaiting_response', archiveSummary:{ready:state === 'finished' ? 1 : 0,pending:0,failed:0} })
function setup(read) {
  const hooks = {}, timers = new Map(), notifications = [], changed = [], calls = [], streams = [], listeners = {}
  const auth = vue.reactive({ token:'test', user:{ user:{userId:1}, permissions:[] } })
  const project = vue.ref('2'), accepted = vue.ref(), allowed = vue.ref(true)
  const document = {visibilityState:'visible', addEventListener(name, fn) {listeners[name]=fn}, removeEventListener(name) {delete listeners[name]}}
  let sequence = 0
  const modules = {}
  function load(name) {
    if (modules[name]) return modules[name]
    const exports = {}; modules[name]=exports
    const source = readFileSync(join(__dirname, '../src', name + '.ts'), 'utf8')
    runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText, {
      exports, AbortController, Date, document, window:document,
      setTimeout(fn, ms) {const id=++sequence; timers.set(id,{fn,ms}); return id}, clearTimeout(id){timers.delete(id)},
      require(id) {
        if (id==='vue') return {...vue,onMounted:fn=>hooks.mount=fn,onActivated:fn=>hooks.activate=fn,onDeactivated:fn=>hooks.deactivate=fn,onBeforeUnmount:fn=>hooks.unmount=fn}
        if (id==='@/stores/auth') return {useAuthStore:()=>auth}
        if (id==='@/api/client') return {ApiError}
        if (id==='./useProjectActivityEvents') return load('composables/useProjectActivityEvents')
        if (id==='@/api/generations') return {subscribeProjectActivity:(project,signal,receive)=>new Promise((resolve,reject)=>{streams.push({project,signal,receive,resolve,reject});signal.addEventListener('abort',resolve,{once:true})}),getGenerationActivity:(query,signal)=>{calls.push({query,signal}); return read(query,signal)}}
        if (id==='element-plus') return {ElNotification:value=>notifications.push(value)}
        if (id==='@/utils/generationFeedback') return load('utils/generationFeedback')
        throw Error(id)
      }
    })
    return exports
  }
  const scope = vue.effectScope()
  const activity = scope.run(()=>load('composables/useGenerationActivity').useGenerationActivity(()=>project.value,()=>allowed.value))
  const progress = scope.run(()=>load('composables/useCreationProgress').useCreationProgress(activity,()=>accepted.value, folders=>changed.push(folders)))
  hooks.mount()
  return {activity,progress,auth,project,accepted,allowed,hooks,timers,notifications,changed,calls,streams,document,listeners,close(){hooks.unmount();scope.stop()}}
}
module.exports={setup,tick,row,ApiError}
