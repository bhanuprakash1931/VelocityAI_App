import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  publicDir: 'assets',
  plugins: [react()],
  resolve: {
    alias: {
      // Allow apps to import from common/frontend without relative ../../..
      // e.g. import SettingsPanel from 'common/frontend/SettingsPanel'
      'common/frontend': path.resolve(__dirname, '../../../common/frontend'),
    },
  },
  server: {
    // Proxy /api/* to the backend so there are no cross-port CORS issues.
    // Set VITE_API_URL in .env only for production deployments on different origins.
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
