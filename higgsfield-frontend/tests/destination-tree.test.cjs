const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), ts = require('typescript'), vue = require('vue'), vm = require('node:vm')
function harness(api) {
 const exports = {}, selected = []; let dispose
 vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/composables/useDestinationTree.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports,AbortController,Error,require:n=>n==='vue'?{...vue,onBeforeUnmount:fn=>dispose=fn}:api})
 return { s:exports.useDestinationTree('2','media',()=> '9',()=>false,p=>selected.push(p)),selected,close:()=>dispose() }
}
const folder=(id,parentId=null)=>({id,parentId,name:id,projectId:'2',folderKind:'media',hasChildren:true})

test('新建子目录后清除旧叶节点缓存，展开完整路径并重新读取分支',async()=>{
 const parent={...folder('20'),hasChildren:false},child={...folder('21','20'),hasChildren:false}
 const h=harness({listFolders:async()=>({rows:[child],hasNext:false})})
 h.s.query.value='旧搜索';h.s.searching.value=true
 h.s.reveal([parent,child])
 assert.equal(h.s.query.value,'');assert.equal(h.s.searching.value,false)
 assert.deepEqual(Array.from(h.s.expanded.value),['root','20','21']);assert.equal(h.s.treeKey.value,1)
 let rows
 await h.s.load({level:2,data:{id:'20',path:[parent]}},value=>rows=value,()=>assert.fail())
 assert.equal(rows[0].id,'21');assert.equal(rows[0].path.length,2);h.close()
})

test('刷新目标分支后，旧搜索和旧懒加载响应不能覆盖新目录树',async()=>{
 const pending=[]
 const h=harness({listFolders:(_project,_params,signal)=>new Promise(resolve=>pending.push({resolve,signal}))})
 let applied=false
 const loading=h.s.load({level:1,data:{id:'root',path:[]}},()=>applied=true,()=>assert.fail())
 h.s.query.value='旧搜索';const searching=h.s.search()
 h.s.reveal([folder('20')])
 assert.ok(pending.every(request=>request.signal.aborted))
 pending.forEach(request=>request.resolve({rows:[],hasNext:false}))
 await Promise.all([loading,searching])
 assert.equal(applied,false);assert.equal(h.s.searching.value,false);assert.equal(h.s.busy.value,false)
 assert.deepEqual(Array.from(h.s.expanded.value),['root','20']);h.close()
})
test('展开读取所有分页，源目录不可选择；展开本身不选择目标',async()=>{
 let calls=0; const h=harness({listFolders:async()=>({rows:[folder(String(++calls))],hasNext:calls===1})});let rows
 await h.s.load({level:1,data:{id:'root',path:[]}},x=>rows=x,()=>assert.fail())
 assert.equal(rows.length,2); assert.equal(h.selected.length,0)
 await h.s.choose({disabled:true,id:'9'});assert.equal(h.selected.length,0);h.close()
})
test('搜索保留祖先路径，清空后恢复普通树；自身子目录不能提交',async()=>{
 const parent=folder('9'),child=folder('10','9')
 const h=harness({listFolders:async()=>({rows:[child],hasNext:false}),readFolder:async()=>({data:{folder:child,ancestors:[parent]}})})
 h.s.query.value='10';await h.s.search();assert.equal(h.s.results.value[0].children[0].children[0].disabled,true)
 await h.s.choose({id:'10',disabled:false});assert.equal(h.selected.length,0);assert.ok(h.s.error.value)
 h.s.query.value='';await h.s.search();assert.equal(h.s.searching.value,false);h.close()
})
test('读取失败可重试，不将失败作为空目录；卸载后不应用结果',async()=>{
 let finish;const h=harness({listFolders:()=>new Promise(r=>finish=r)});let applied=false
 const pending=h.s.load({level:1,data:{id:'root',path:[]}},()=>applied=true,()=>{});h.close();finish({rows:[],hasNext:false});await pending;assert.equal(applied,false)
 const broken=harness({listFolders:async()=>{throw new Error('断网')}});let rejected=false
 await broken.s.load({level:1,data:{id:'root',path:[]}},()=>assert.fail(),()=>rejected=true);assert.equal(rejected,true);assert.equal(broken.s.error.value,'断网');broken.close()
})

test('首次搜索失败后重新加载保留关键词并重试搜索',async()=>{
 let calls=0
 const h=harness({listFolders:async(_project,params)=>{assert.equal(params.q,'目标');if(++calls===1)throw new Error('断网');return {rows:[folder('3')],hasNext:false}},readFolder:async()=>({data:{folder:folder('3'),ancestors:[]}})})
 h.s.query.value='目标';await h.s.search();assert.equal(h.s.searching.value,false);assert.equal(h.s.error.value,'断网')
 await h.s.reload();assert.equal(calls,2);assert.equal(h.s.searching.value,true);assert.equal(h.s.results.value[0].children[0].id,'3');assert.equal(h.s.error.value,'');h.close()
})
