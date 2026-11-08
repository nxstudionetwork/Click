/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    // Same-origin in development so the httpOnly refresh cookie just works.
    proxy: { '/api': { target: process.env.CLICK_API_PROXY ?? 'http://localhost:8000', changeOrigin: false } },
  },
  preview: { port: 4174 },
  build: {
    rollupOptions: {
      output: {
        // Firebase is only needed on the sign-in path; keep it out of the startup bundle.
        manualChunks: (id) => (id.includes('node_modules/firebase') || id.includes('node_modules/@firebase') ? 'firebase' : undefined),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
