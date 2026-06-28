import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  // 安装版通过 file:// 加载页面，资源必须使用相对路径。
  base: './',
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5176,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
