import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // The app calls a relative /api/v1; in dev we forward it to the local backend.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
