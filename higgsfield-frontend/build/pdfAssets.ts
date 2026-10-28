/** 将PDF字体、字符映射和解码器随站点发布，避免运行时依赖外部CDN。 */
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { readFileSync, readdirSync } from 'node:fs'
import type { Plugin } from 'vite'

export function pdfAssets(): Plugin {
  const root = dirname(createRequire(import.meta.url).resolve('pdfjs-dist/package.json'))
  const files = new Map<string, string>()
  for (const folder of ['cmaps', 'standard_fonts', 'wasm', 'iccs']) {
    for (const item of readdirSync(join(root, folder), { withFileTypes: true })) {
      if (item.isFile()) files.set(`pdf-assets/${folder}/${item.name}`, join(root, folder, item.name))
    }
  }
  return {
    name: 'higgsfield-pdf-assets',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const key = (req.url || '').split('?')[0]?.replace(/^\//, '') || ''
        const path = files.get(key)
        if (!path) return next()
        res.setHeader('Content-Type', key.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream')
        res.end(readFileSync(path))
      })
    },
    generateBundle() {
      for (const [fileName, path] of files) this.emitFile({ type: 'asset', fileName, source: readFileSync(path) })
    },
  }
}
