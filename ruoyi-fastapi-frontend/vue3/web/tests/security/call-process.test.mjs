import test from 'node:test'
import assert from 'node:assert/strict'
import { groupCallProcess, callTaskState, executionDuration } from '../../src/utils/callProcess.js'

test('连续轮询折叠但不跨越提交，并保留所有调用', () => {
  const rows = ['video_submit', 'video_poll', 'video_poll', 'video_submit', 'video_poll'].map((operation, i) => ({ id: String(i), operation }))
  const groups = groupCallProcess(rows)
  assert.deepEqual(groups.map(group => group.calls.length), [1, 2, 1, 1])
  assert.deepEqual(groups.flatMap(group => group.calls), rows)
  assert.deepEqual(groupCallProcess([]), [])
})

test('生成状态不以调用完成推断，耗时取任务起止时间', () => {
  assert.equal(callTaskState({ orchestrationState: '5', upstreamState: '4' }), '生成失败')
  assert.equal(callTaskState({ orchestrationState: '3', upstreamState: '6' }), '受理或结果待核查')
  assert.equal(callTaskState({ orchestrationState: '5', upstreamState: '3' }), '供应商生成成功')
  assert.equal(executionDuration({ createdAt: '2026-11-09T07:30:00Z', finishedAt: '2026-11-09T07:36:10Z' }), '6 分 10 秒')
  assert.equal(executionDuration({}), '尚未结束')
  assert.equal(executionDuration({ createdAt: 'invalid', finishedAt: 'invalid' }), '未记录')
})
