import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En dev, /api se proxya al gateway local
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3100,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
