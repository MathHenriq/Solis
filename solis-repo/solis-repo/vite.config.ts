import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Tauri serve o frontend a partir de uma porta fixa e falha se ela mudar.
  server: { port: 1420, strictPort: true },
  build: { target: 'es2021', sourcemap: true },
});
