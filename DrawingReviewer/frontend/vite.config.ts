import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  publicDir: 'assets',
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})