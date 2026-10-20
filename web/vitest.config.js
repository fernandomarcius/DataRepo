import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config.js';

// Testes de componente (jsdom).
// a cobertura (lcov) entra no diff-cover das linhas alteradas.
export default mergeConfig(viteConfig, defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['lcov', 'text-summary'],
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/**/*.test.{js,jsx}', 'src/main.jsx'],
    },
  },
}));
