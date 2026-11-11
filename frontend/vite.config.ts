import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

// Polling is needed for file watching on Windows / Docker bind mounts.
const usePolling = ['1', 'true', 'yes'].includes(
  (process.env.VITE_USE_POLLING || process.env.CHOKIDAR_USEPOLLING || '').toLowerCase(),
)

export default defineConfig({
  plugins: [
    vue({
      template: {
        // Absolute URLs (e.g. /favicon.svg) point to public/ and must stay as-is; transforming
        // them breaks SFC imports under Vitest on Windows (file:///favicon.svg).
        transformAssetUrls: { includeAbsolute: false },
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
  },
  build: {
    // maplibre-gl alone is ~1 MB minified; it is loaded lazily with the map view.
    chunkSizeWarningLimit: 1100,
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
  },
})
