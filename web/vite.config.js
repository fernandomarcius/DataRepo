import process from 'node:process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  // `/` na raiz de um host (padrao). O plataforma publica o app sob
  // /workloads/{tenant}/{servico}/ e o gateway tira o prefixo antes do nginx:
  // la o build usa VITE_BASE=./ e o nginx reescreve os caminhos do index.html
  // pela profundidade da URL. Ver src/prefixo.js.
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    watch: {
      usePolling: true
    },
    proxy: {
      // Em dev a API vem do nginx da stack local (deploy/ do DataRepo),
      // publicado em :5000 — o mesmo endereco do antigo backend monolitico.
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://localhost:5000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})
