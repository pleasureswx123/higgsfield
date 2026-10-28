const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readdirSync, readFileSync } = require('node:fs')
const path = require('node:path')
const { parse, compileScript } = require('vue/compiler-sfc')

// 当前工程按组件导入 Element Plus，没有全局注册或自动导入插件。
test('制作端模板中的 Element Plus 组件编译为本地绑定，不遗留运行时解析', () => {
  const missing = []
  let checked = 0
  function inspect(directory) {
    for (const item of readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, item.name)
      if (item.isDirectory()) { inspect(file); continue }
      if (!file.endsWith('.vue')) continue
      const { descriptor } = parse(readFileSync(file, 'utf8'), { filename: file })
      if (!descriptor.template || !descriptor.scriptSetup) continue
      checked++
      const compiled = compileScript(descriptor, { id: file, inlineTemplate: true }).content
      for (const match of compiled.matchAll(/\b_resolveComponent\(["'](el-[^"']+|El[A-Z][^"']*)["']\)/g))
        missing.push(`${path.relative(path.join(__dirname, '../src'), file)}: ${match[1]}`)
    }
  }
  inspect(path.join(__dirname, '../src'))
  assert.ok(checked > 0)
  assert.deepEqual(missing, [], `缺少组件导入：\n${missing.join('\n')}`)
})
