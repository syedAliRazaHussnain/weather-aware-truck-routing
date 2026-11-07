import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, /api goes to the local Django server, so no CORS setup is needed.
// In production, VITE_API_URL points the app at the hosted API instead.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
