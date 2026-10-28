import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import { pdfAssets } from './build/pdfAssets'
export default defineConfig(({ mode }) => ({
  plugins: [vue(), tailwindcss(), pdfAssets()],
  optimizeDeps: { include: ['@noble/hashes/sha2.js'] },
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      '/dev-api': {
        target: loadEnv(mode, process.cwd()).VITE_API_TARGET || 'http://127.0.0.1:9099',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/dev-api/, ''),
      },
    },
  },
}))
