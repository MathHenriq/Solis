/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Endereço do servidor local (backend/). Padrão: http://127.0.0.1:8765. */
  readonly VITE_SOLIS_SERVIDOR?: string;
}
