import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  publicDir: '../../assets',
  plugins: [react()],
  server: {
    // When running with --host 0.0.0.0 the browser may hit any IP/hostname.
    // Proxy /api/* through to the backend so there are no cross-port CORS
    // or "Failed to fetch" issues for network users.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})