const {test}=require('node:test')
const assert=require('node:assert/strict')
const {setup,tick,row}=require('./generation-activity-harness.cjs')
test('等待响应采用低频查询，终态空闲再降频；目录导航不重置通知跟踪',async()=>{
 let done=false
 const c=setup(async query=>({data:{projectActiveCount:done?0:1,rows:done?query.trackedIds.split(',').filter(Boolean).map(id=>row(id,'finished')):[row('1')],hasNext:false}}))
 await tick();assert.ok([...c.timers.values()].find(timer=>timer.ms<40000).ms>=5000);assert.ok([...c.timers.values()].find(timer=>timer.ms<40000).ms<5500)
 done=true;await c.activity.refresh();assert.ok([...c.timers.values()].find(timer=>timer.ms<40000).ms>=30000);assert.equal(c.changed.length,1);c.close()
})
test('首次状态未知不展示零，故障后继续退避恢复，不伪装成任务已完成',async()=>{
 const c=setup(async()=>{throw Error('离线')});await tick()
 assert.equal(c.activity.count.value,undefined);assert.equal(c.progress.rows.value.length,0);assert.match(c.progress.error.value,/暂未更新/)
 await c.activity.refresh();assert.ok([...c.timers.values()].find(timer=>timer.ms<40000).ms>=10000);assert.equal(c.changed.length,0);c.close()
})
