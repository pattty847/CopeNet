import { defineConfig } from 'vite';

export default defineConfig({ build: {
  ssr: 'src/sections/market/indicators/alertRunner.ts',
  emptyOutDir: false,
  rollupOptions: { output: { format: 'cjs', entryFileNames: 'indicator-alerts.cjs' } },
} });
