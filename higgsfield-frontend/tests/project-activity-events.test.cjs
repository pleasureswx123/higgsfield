const {test}=require('node:test')
const assert=require('node:assert/strict')
const {setup,tick,row,ApiError}=require('./generation-activity-harness.cjs')
const event=(name,projectId='2')=>({event:name,data:JSON.stringify({projectId})})
const response=rows=>({data:{projectActiveCount:rows.filter(r=>r.orchestrationState!=='finished').length,rows,hasNext:false}})

test('一个项目只开一条 SSE，正常心跳不查询，变化通知读取快照并停止常规轮询',async()=>{
 const c=setup(async()=>response([row('1')]))
 await tick();assert.equal(c.streams.length,1)
 await c.streams[0].receive(event('activity.sync'));await tick()
 assert.equal(c.activity.connected.value,true)
 const before=c.calls.length
 await c.streams[0].receive(event('activity.heartbeat'));await tick();assert.equal(c.calls.length,before)
 assert.equal([...c.timers.values()].filter(t=>t.ms<40000).length,0)
 await c.streams[0].receive(event('activity.changed'));await tick();assert.equal(c.calls.length,before+1)
 assert.equal(c.streams.length,1);c.close()
})

test('断线期间完成任务：轮询兜底与重连同步不漏终态、不重复通知',async()=>{
 let finished=false
 const c=setup(async query=>response(finished?query.trackedIds.split(',').filter(Boolean).map(id=>row(id,'finished')):[row('1')]))
 await tick();await c.streams[0].receive(event('activity.sync'));await tick()
 finished=true;c.streams[0].resolve();await tick()
 assert.equal(c.activity.connected.value,false);assert.equal(c.notifications.length,1)
 const [id,retry]=[...c.timers].find(([,timer])=>timer.ms<3000)
 c.timers.delete(id);retry.fn();await tick();assert.equal(c.streams.length,2)
 await c.streams[1].receive(event('activity.sync'));await tick()
 assert.equal(c.notifications.length,1);assert.equal(c.activity.connected.value,true);c.close()
})

test('撤权立即清空并停止推送、补查和自动重连，旧连接事件不可恢复数据',async()=>{
 const c=setup(async()=>response([row('1')]))
 await tick();await c.streams[0].receive(event('activity.sync'));await tick()
 c.accepted.value='1';await tick()
 await c.streams[0].receive({event:'access.revoked',data:'{}'});await tick()
 assert.equal(c.activity.rows.value.length,0);assert.equal(c.activity.count.value,undefined)
 assert.equal(c.progress.awaitingAccepted.value,false)
 assert.equal(c.streams[0].signal.aborted,true);assert.equal(c.timers.size,0)
 const before=c.calls.length;await c.streams[0].receive(event('activity.changed'));await tick();assert.equal(c.calls.length,before);c.close()
})

test('切换项目和后台标签关闭旧连接，迟到或错误项目事件不能触发跨项目读取',async()=>{
 const c=setup(async()=>response([]));await tick()
 const old=c.streams[0];c.project.value='3';await tick()
 assert.equal(old.signal.aborted,true);assert.equal(c.streams[1].project,'3')
 const before=c.calls.length;await old.receive(event('activity.changed'));assert.equal(c.calls.length,before)
 await assert.rejects(c.streams[1].receive(event('activity.changed','2')),/身份不匹配/)
 c.document.visibilityState='hidden';c.listeners.visibilitychange();assert.equal(c.streams[1].signal.aborted,true)
 c.document.visibilityState='visible';c.listeners.visibilitychange();await tick();assert.equal(c.streams.length,3);c.close()
})

test('半开连接超时退出实时模式，重新连接；明确拒绝订阅不自动重试',async()=>{
 const c=setup(async()=>response([]));await tick()
 await c.streams[0].receive(event('activity.sync'));await tick()
 const watchdog=[...c.timers.values()].find(t=>t.ms===45000)
 watchdog.fn();await tick();assert.equal(c.activity.connected.value,false);assert.equal(c.streams[0].signal.aborted,true)
 c.close()
 const denied=setup(async()=>response([]));await tick()
 denied.streams[0].reject(new ApiError(403));await tick();assert.equal(denied.timers.size,0);assert.equal(denied.activity.count.value,undefined);denied.close()
})
