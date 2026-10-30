const {test}=require('node:test')
const assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{runInNewContext}=require('node:vm'),ts=require('typescript')
const exportsObject={}
runInNewContext(ts.transpileModule(readFileSync('src/utils/commentThreads.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:exportsObject,Map,Date})
const group=exportsObject.groupCommentThreads
const rows=[{id:'2',threadId:'a',body:'回复内容',createTime:'2026-10-30T02:00:00Z'}, {id:'1',threadId:'a',body:'原评论',createTime:'2026-10-30T01:00:00Z'}, {id:'3',threadId:'b',body:'另一条讨论',createTime:'2026-10-30T03:00:00Z'}]
test('回复归入所属讨论并按时间排序，不改变原数组',()=>{const result=group(rows);assert.equal(result.length,2);assert.equal(result[0].comments[0].id,'1');assert.equal(result[0].comments[1].id,'2');assert.equal(rows[0].id,'2')})
test('搜索回复保留讨论上下文，删除根评论保留有效回复',()=>{assert.equal(group(rows,'回复内容')[0].comments.length,2);const result=group(rows.map(row=>({...row,deleted:row.id==='1'})));assert.equal(result[0].comments.length,1);assert.equal(result[0].comments[0].id,'2')})


test('视频讨论按数值时间排序，同时间按发表顺序，回复不拆散，无时间排最后',()=>{
 const data=[
  {id:'1',threadId:'late',videoTime:'10.1',createTime:'2026-10-30T01:00:00Z'},
  {id:'2',threadId:'first',videoTime:'5.578',createTime:'2026-10-30T02:00:00Z'},
  {id:'3',threadId:'general',videoTime:null,createTime:'2026-10-30T00:00:00Z'},
  {id:'4',threadId:'same',videoTime:'5.578',createTime:'2026-10-30T03:00:00Z'},
  {id:'5',threadId:'first',parentId:'2',body:'回复',createTime:'2026-10-30T04:00:00Z'},
  {id:'6',threadId:'zero',videoTime:'0',createTime:'2026-10-30T05:00:00Z'},
 ]
 assert.equal(group(data,'',true).map(item=>item.id).join(','),'zero,first,same,late,general')
 assert.equal(group(data,'',true)[1].comments.map(item=>item.id).join(','),'2,5')
 assert.equal(group(data).map(item=>item.id).join(','),'late,first,general,same,zero')
 assert.equal(data[0].id,'1')
 assert.equal(group(data,'回复',true)[0].comments.length,2)
})
