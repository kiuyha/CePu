import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env from current directory and project root so one root .env works everywhere
  const rootEnv = loadEnv(mode, '../', '')
  const localEnv = loadEnv(mode, process.cwd(), '')
  const env = { ...rootEnv, ...localEnv }
  const backendTarget = env.VITE_API_URL || env.BACKEND_URL || 'http://127.0.0.1:5687'

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        '/v1': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/healthz': {
          target: backendTarget,
          changeOrigin: true,
        }
      }
    }
  }
})
