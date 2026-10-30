const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
function setup(enabled = true, reject = false) {
 const events = new Map(), exported = {}; let cleanup
 const document = { fullscreenEnabled:enabled, fullscreenElement:null, addEventListener:(k,v)=>events.set(k,v),removeEventListener:k=>events.delete(k),async exitFullscreen(){this.fullscreenElement=null;events.get('fullscreenchange')?.()} }
 const element = { async requestFullscreen(){if(reject)throw Error('unsupported');document.fullscreenElement=element;events.get('fullscreenchange')?.()} }
 runInNewContext(ts.transpileModule(readFileSync('src/composables/usePreviewFullscreen.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports:exported,document,require:()=>({...vue,onMounted:fn=>fn(),onBeforeUnmount:fn=>cleanup=fn})})
 return {api:exported.usePreviewFullscreen(()=>element),document,events,cleanup:()=>cleanup()}
}
test('进入全屏、浏览器退出与再次还原同步页面状态',async()=>{
 const {api,document,cleanup}=setup();await api.toggle();assert.equal(api.expanded.value,true);assert.ok(document.fullscreenElement)
 await document.exitFullscreen();assert.equal(api.expanded.value,false)
 await api.toggle();await api.toggle();assert.equal(api.expanded.value,false);assert.equal(document.fullscreenElement,null);cleanup()
})
test('不支持或拒绝全屏时保留页面最大化，Esc可还原',async()=>{
 for(const args of [[false,false],[true,true]]) {const {api,events,cleanup}=setup(...args);await api.toggle();assert.equal(api.expanded.value,true);events.get('keydown')({key:'Escape',preventDefault(){},stopImmediatePropagation(){}});assert.equal(api.expanded.value,false);cleanup();assert.equal(events.size,0)}
})
