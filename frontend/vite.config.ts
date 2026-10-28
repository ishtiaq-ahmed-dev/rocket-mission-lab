import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

const proxy = {
  '/api': {
    target: 'http://127.0.0.1:8010',
    ws: true,
    rewrite: (p: string) => p.replace(/^\/api/, '')
  }
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0', // Listens on both 127.0.0.1 and [::1] (localhost)
    port: 5180,
    strictPort: true,
    proxy
  },
  preview: {
    host: '0.0.0.0',
    port: 5180,
    strictPort: true,
    proxy
  },
  build: {
    chunkSizeWarningLimit: 1400,
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        lab: fileURLToPath(new URL('./lab/index.html', import.meta.url)),
        replay: fileURLToPath(new URL('./replay/index.html', import.meta.url))
      },
      output: {
        manualChunks: {
          'vendor-three': ['three', '@react-three/fiber', '@react-three/drei'],
          'vendor-charts': ['recharts'],
          'vendor-react': ['react', 'react-dom', 'zustand', 'lucide-react']
        }
      }
    }
  }
});
