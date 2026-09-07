import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),   // 让 @ 指向 src
    },
  },
  server: {
    proxy: {
      '/api': {                                               // 前端 /api/xxx → 后端 8000
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})