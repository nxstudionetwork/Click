/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5177,
    // Same-origin in development so the httpOnly OS refresh cookie (path /api/v1/os/auth/) just works.
    proxy: {
      '/api': { target: process.env.CLICK_API_PROXY ?? 'http://localhost:4000', changeOrigin: false },
      '/media': { target: process.env.CLICK_API_PROXY ?? 'http://localhost:4000', changeOrigin: false },
    },
  },
  preview: { port: 4177 },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'], css: false },
});
