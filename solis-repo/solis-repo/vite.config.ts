import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Tauri serve o frontend a partir de uma porta fixa e falha se ela mudar.
  // O Vite não vigia o Rust nem o Python: o build do Tauri trava arquivos em
  // src-tauri/target, e vigiá-los derrubava o Vite (EBUSY) no meio do `tauri dev`.
  server: {
    port: 1420,
    strictPort: true,
    watch: { ignored: ['**/src-tauri/**', '**/backend/**'] },
  },
  build: { target: 'es2021', sourcemap: true },
});
