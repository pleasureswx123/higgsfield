const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const key = 'higgsfield.studio.session-token'
function setup(storage = new Map(), api = {}) {
  const exports = {}
  const code = ts.transpileModule(readFileSync('src/stores/auth.ts','utf8'), { compilerOptions:{ module:ts.ModuleKind.CommonJS } }).outputText
  runInNewContext(code, { exports, Error, sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}, require(id) {
    if(id==='vue') return vue
    if(id==='pinia') return {defineStore:(_id,fn)=>fn}
    if(id==='@/api/auth') return {getUserInfo:async()=>({user:{userId:1},permissions:['project:read']}),logout:async()=>{},...api}
    return {clearCommentRecovery(){},clearGenerationRecovery(){}}
  } })
  return exports.useAuthStore()
}
test('登录后刷新恢复令牌并重新读取权限，不保存密码或用户快照',async()=>{
 const storage = new Map()
 const first = setup(storage,{login:async()=>({token:'valid-token'})})
 await first.signIn({username:'user',password:'secret'})
 assert.equal(storage.size,1); assert.equal(storage.get(key),'valid-token')
 let reads=0
 const second=setup(storage,{getUserInfo:async()=>{reads++;return {user:{userId:1},permissions:['new-permission']}}})
 assert.equal(second.isAuthenticated.value,false)
 await second.restoreSession()
 assert.equal(reads,1);assert.equal(second.isAuthenticated.value,true)
 assert.equal(second.user.value.permissions[0],'new-permission')
})
test('并发恢复只请求一次，退出后迟到响应不能复活会话',async()=>{
 const storage=new Map([[key,'old']]);let resolve,calls=0
 const state=setup(storage,{getUserInfo:()=>{calls++;return new Promise(r=>resolve=r)}})
 const a=state.restoreSession(),b=state.restoreSession()
 assert.equal(calls,1);await state.signOut()
 resolve({user:{userId:1}});await Promise.all([a,b])
 assert.equal(state.isAuthenticated.value,false);assert.equal(storage.size,0)
})
test('过期401清理会话，临时故障保留凭据允许重试',async()=>{
 const expired=new Map([[key,'expired']])
 const a=setup(expired,{getUserInfo:async()=>{throw {code:401}}})
 await a.restoreSession();assert.equal(expired.size,0);assert.equal(a.token.value,'')
 const saved=new Map([[key,'valid']]);let fail=true
 const b=setup(saved,{getUserInfo:async()=>{if(fail)throw Error('network');return {user:{userId:1}}}})
 await b.restoreSession();assert.equal(saved.get(key),'valid');assert.ok(b.restoreError.value)
 fail=false;await b.restoreSession();assert.equal(b.isAuthenticated.value,true);assert.equal(b.restoreError.value,'')
})
test('新登录不会被旧恢复响应覆盖，退出失败也删除本地凭据',async()=>{
 const storage=new Map([[key,'old']]);let resolve,calls=0
 const state=setup(storage,{login:async()=>({token:'new'}),getUserInfo:()=>++calls===1?new Promise(r=>resolve=r):Promise.resolve({user:{userId:2}}),logout:async()=>{throw Error('offline')}})
 const restoring=state.restoreSession();await state.signIn({})
 resolve({user:{userId:1}});await restoring
 assert.equal(state.user.value.user.userId,2);assert.equal(storage.get(key),'new')
 await assert.rejects(state.signOut());assert.equal(storage.size,0);assert.equal(state.isAuthenticated.value,false)
})

test('刷新深层项目地址先等待会话恢复，失效时保留完整回跳地址',async()=>{
 let guard,finish
 const auth={isAuthenticated:false,restoreSession:()=>new Promise(resolve=>{finish=()=>{auth.isAuthenticated=true;resolve()}})}
 const router={beforeEach:fn=>guard=fn,afterEach(){}}
 const exports={}
 runInNewContext(ts.transpileModule(readFileSync('src/router/index.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,require(id){
  if(id==='vue-router')return {createRouter:()=>router,createWebHistory(){}}
  return {useAuthStore:()=>auth}
 }})
 const target={path:'/projects/2',fullPath:'/projects/2?tab=folders&folder=7',meta:{requiresAuth:true}}
 let completed=false
 const navigation=guard(target).then(value=>{completed=true;return value})
 await Promise.resolve();assert.equal(completed,false)
 finish();assert.equal(await navigation,undefined)
 auth.isAuthenticated=false;auth.restoreSession=async()=>{}
 const result=await guard(target)
 assert.equal(result.path,'/login');assert.equal(result.query.redirect,target.fullPath)
})
