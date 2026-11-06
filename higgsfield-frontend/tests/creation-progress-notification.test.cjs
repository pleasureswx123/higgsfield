const {test}=require('node:test')
const assert=require('node:assert/strict')
const {setup,tick,row}=require('./generation-activity-harness.cjs')
test('多个任务终态合并读取且分别通知，刷新不重复通知，同目录只刷新一次',async()=>{
 let done=false
 const c=setup(async query=>({data:{projectActiveCount:done?0:2,rows:done?query.trackedIds.split(',').filter(Boolean).map(id=>row(id,'finished')):[row('1'),row('2')],hasNext:false}}))
 await tick();assert.equal(c.notifications.length,0)
 done=true;await c.activity.refresh();assert.equal(c.notifications.length,2);assert.equal(c.changed.length,1);assert.deepEqual([...c.changed[0]],['9'])
 await c.activity.refresh();assert.equal(c.notifications.length,2);assert.equal(c.changed.length,1);c.close()
})
test('快速完成的刚受理任务仍通知，并只刷新其真实归档目录',async()=>{
 const c=setup(async query=>({data:{projectActiveCount:0,rows:query.trackedIds?query.trackedIds.split(',').map(id=>row(id,'finished','15')):[],hasNext:false}}))
 await tick();c.accepted.value='10';await tick();assert.equal(c.notifications.length,1);assert.deepEqual([...c.changed[0]],['15']);assert.equal(c.progress.awaitingAccepted.value,false)
 await c.activity.refresh();assert.equal(c.notifications.length,1);assert.equal(c.changed.length,1);c.close()
})
