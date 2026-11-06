const {test}=require('node:test')
const assert=require('node:assert/strict')
const {setup,tick,row,ApiError}=require('./generation-activity-harness.cjs')
const response=(count,rows=[])=>({data:{projectActiveCount:count,rows,hasNext:false}})
test('共享状态一次读取同时驱动数量与个人进度，失败保留最后成功值并自动恢复',async()=>{
 let fail=false
 const c=setup(async()=>{if(fail)throw Error('断网');return response(25,[row('1')])})
 await tick();assert.equal(c.calls.length,1);assert.equal(c.activity.count.value,25);assert.equal(c.progress.running.value.id,'1')
 fail=true;await c.activity.refresh();assert.equal(c.activity.count.value,25);assert.equal(c.progress.rows.value.length,1);assert.match(c.activity.error.value,/暂未更新/)
 fail=false;await c.activity.refresh();assert.equal(c.activity.error.value,'');assert.equal([...c.timers.values()].filter(timer=>timer.ms<40000).length,1);c.close()
})
test('退出和切换项目中止请求，迟到响应不能恢复旧项目状态',async()=>{
 const requests=[];const c=setup((query,signal)=>new Promise(resolve=>requests.push({query,signal,resolve})))
 c.project.value='3';assert.equal(requests[0].signal.aborted,true)
 requests[1].resolve(response(2));await tick();requests[0].resolve(response(99));await tick();assert.equal(c.activity.count.value,2)
 c.auth.token='';assert.equal(c.activity.count.value,undefined);assert.equal(c.progress.rows.value.length,0);assert.equal(c.timers.size,0);c.close()
})
test('后台标签暂停查询，恢复可见补查；权限失败清除旧结果',async()=>{
 let fail=false;const c=setup(async()=>{if(fail)throw new ApiError(403);return response(4,[row('1')])})
 await tick();c.document.visibilityState='hidden';c.listeners.visibilitychange();assert.equal(c.timers.size,0)
 await c.activity.refresh();assert.equal(c.calls.length,1)
 c.document.visibilityState='visible';c.listeners.visibilitychange();await tick();assert.equal(c.calls.length,2)
 fail=true;await c.activity.refresh();assert.equal(c.activity.count.value,undefined);assert.equal(c.progress.rows.value.length,0);c.close()
})
test('并发刷新只保留一个在途读取，新提交在本次完成后补查而不丢失',async()=>{
 const requests=[];const c=setup((query,signal)=>new Promise(resolve=>requests.push({query,signal,resolve})))
 c.accepted.value='10';c.activity.refresh();c.activity.refresh();assert.equal(requests.length,1)
 requests[0].resolve(response(0));await tick();assert.equal(requests.length,2);assert.equal(requests[1].query.trackedIds,'10')
 requests[1].resolve(response(1,[row('10')]));await tick();assert.equal(c.progress.awaitingAccepted.value,false);assert.equal([...c.timers.values()].filter(timer=>timer.ms<40000).length,1);c.close()
})
test('个人任务多页与超过一百个跟踪编号分批读取并去重',async()=>{
 let phase=0
 const c=setup(async query=>phase===0?{data:{projectActiveCount:120,rows:Array.from({length:query.pageNum===1?100:20},(_,i)=>row(String((query.pageNum-1)*100+i+1))),hasNext:query.pageNum===1}}:response(0,query.trackedIds.split(',').filter(Boolean).map(id=>row(id,'finished'))))
 await tick();assert.equal(c.activity.rows.value.length,120);assert.equal(c.calls.length,2)
 phase=1;await c.activity.refresh();assert.equal(c.activity.rows.value.length,120);assert.equal(c.calls.length,4);assert.ok(c.calls.slice(2).every(call=>call.query.trackedIds.split(',').length<=100));c.close()
})
