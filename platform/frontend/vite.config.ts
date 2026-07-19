import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  publicDir: '../../assets',
  plugins: [react()],
  server: {
    port: 5170,
    proxy: {
      // All /api/platform/* requests go to the platform backend
      '/api/platform': {
        target: 'http://localhost:7000',
        changeOrigin: true,
      },
    },
  },
})