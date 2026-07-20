import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// Dev proxy: /api -> control plane at :8000 (spec 06 base path). Keeps SSE and
// REST same-origin in dev, mirroring Caddy's mapping on the VM in prod, so the
// client uses a relative /api base and needs no code change between environments.
// Override the target with VITE_PROXY_TARGET if the backend runs elsewhere.
export default defineConfig(() => {
  const target = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'
  return {
    plugins: [react()],
    server: {
      port: 5174,
      strictPort: true,
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          // SSE streams must not be buffered; http-proxy passes them through.
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              proxyReq.setHeader('accept-encoding', 'identity')
            })
          },
        },
      },
    },
  }
})
