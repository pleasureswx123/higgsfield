import assert from 'node:assert/strict'
import test from 'node:test'
import { parseVariantDimension, variantPayload } from '../../src/utils/modelVariant.js'

test('精确规格保留枚举类型，布尔不作为数字，未知或超范围值不能提交', () => {
  assert.equal(parseVariantDimension({ type: 'string', enum: ['1'] }, '"1"'), '1')
  assert.equal(parseVariantDimension({ type: 'integer', enum: [1] }, '1'), 1)
  assert.equal(parseVariantDimension({ type: 'boolean' }, 'false'), false)
  assert.throws(() => parseVariantDimension({ type: 'integer' }, 'true'))
  assert.throws(() => parseVariantDimension({ type: 'integer' }, '9007199254740993'))
  assert.throws(() => parseVariantDimension({ type: 'integer' }, '1.5'))
  assert.throws(() => parseVariantDimension({ type: 'number' }, '1e999'))
  assert.throws(() => parseVariantDimension({ type: 'integer', minimum: 1, maximum: 4 }, '5'))
  assert.throws(() => parseVariantDimension({ type: 'string', enum: ['x'] }, '"y"'))
  assert.equal(parseVariantDimension({ type: 'string', maxLength: 1 }, '😀'), '😀')
  assert.throws(() => parseVariantDimension({ type: 'string', minLength: 1 }, ''))
})

test('完整规格只包含声明维度，空维度合法，缺失维度拒绝', () => {
  assert.deepEqual(variantPayload({}, { ignored: 'x' }), { dimensions: {} })
  const rules = { resolution: { type: 'string', enum: ['1080p'] }, audio: { type: 'boolean' } }
  assert.deepEqual(variantPayload(rules, { resolution: '"1080p"', audio: 'false', extra: 'ignored' }), { dimensions: { resolution: '1080p', audio: false } })
  assert.throws(() => variantPayload(rules, { resolution: '"1080p"' }))
})
