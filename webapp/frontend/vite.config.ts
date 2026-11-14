import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 개발 중에는 FastAPI(8080)로 API와 파일 요청을 넘긴다.
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // 디자인 시스템 토큰은 저장소 루트의 design-system/ 을 그대로 쓴다.
      '@design': fileURLToPath(new URL('../../design-system', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    fs: { allow: ['..', '../..'] },
    proxy: {
      '/api': { target: backend, changeOrigin: false },
      '/healthz': { target: backend, changeOrigin: false },
    },
  },
})
