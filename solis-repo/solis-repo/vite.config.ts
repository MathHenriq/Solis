import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tauri espera um servidor fixo em dev e não usa polling de rede externa.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  build: { target: "es2021", sourcemap: true },
});
