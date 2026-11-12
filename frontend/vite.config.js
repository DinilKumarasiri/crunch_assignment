import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,            // listen on 0.0.0.0 so the browser can reach the container
    port: 5173,
    watch: {
      usePolling: true,    // detect file changes made on Windows/Mac inside Docker
    },
    proxy: {
      // Any request starting with /api is forwarded to the Django container.
      '/api': { target: 'http://backend:8000' },
    },
  },
})