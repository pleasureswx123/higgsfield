import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
const source = await readFile(new URL('../../src/utils/routing.js', import.meta.url), 'utf8')
const { validRoutingId, routingPayload } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
)
const route = () => ({
  modelId: '9223372036854775807',
  accountId: '2',
  priority: 0,
  enabled: true,
  credentials: [{ credentialId: '3', priority: 100, maxConcurrency: 1 }],
})
test('路由保留大整数ID，生成独立白名单载荷并允许显式清空', () => {
  const input = route(),
    output = routingPayload('1', [input])
  assert.equal(output.routes[0].modelId, '9223372036854775807')
  input.credentials[0].maxConcurrency = 7
  assert.equal(output.routes[0].credentials[0].maxConcurrency, 1)
  assert.deepEqual(routingPayload('1', []), { revision: '1', routes: [] })
  assert.equal(validRoutingId('9223372036854775808'), false)
  assert.equal(validRoutingId(123), false)
})
test('拒绝重复路由、重复凭据、无凭据启用与非法并发', () => {
  assert.throws(() => routingPayload('1', [route(), route()]), /组合不能重复/)
  const duplicate = route()
  duplicate.credentials.push({ ...duplicate.credentials[0] })
  assert.throws(() => routingPayload('1', [duplicate]), /重复/)
  assert.throws(() => routingPayload('1', [{ ...route(), credentials: [] }]), /候选凭据/)
  for (const value of [0, -1, 1.1, '2', NaN, 2147483648]) {
    const input = route()
    input.credentials[0].maxConcurrency = value
    assert.throws(() => routingPayload('1', [input]), /并发上限/)
  }
})
