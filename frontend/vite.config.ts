import { defineConfig } from 'vite';

const proxy = {
  '/api': {
    target: 'http://127.0.0.1:8010',
    ws: true,
    rewrite: (p: string) => p.replace(/^\/api/, '')
  }
};

export default defineConfig({
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
  }
});
