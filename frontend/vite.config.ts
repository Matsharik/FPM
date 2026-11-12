import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/FPM/', // ИМЯ ТВОЕГО РЕПОЗИТОРИЯ НА GITHUB
  plugins: [react()],
  build: {
    outDir: 'dist', // Меняем на dist
    emptyOutDir: true,
    chunkSizeWarningLimit: 2000,
  },
  // server: { ... }  <-- УДАЛЕНО ПОЛНОСТЬЮ
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});