import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/* Configuração do Vite sob o Tauri.
 *
 * `clearScreen: false` mantém as mensagens do Rust visíveis: sem isso o Vite
 * limpa a tela e some com o log da compilação, que é justamente onde os erros
 * do lado nativo aparecem.
 *
 * A porta é fixa e `strictPort` é true porque o Tauri aponta pra ela no
 * `devUrl` — se o Vite escolhesse outra porta ao encontrar a 1420 ocupada, a
 * janela abriria em branco sem dizer por quê.
 */
export default defineConfig({
  plugins: [react()],
  clearScreen: false,

  server: {
    port: 1420,
    strictPort: true,
    watch: {
      /* NÃO vigiar src-tauri.
       *
       * Durante `tauri dev` o Rust escreve centenas de arquivos em
       * src-tauri/target. No Windows, arquivo em escrita fica travado pelo SO,
       * e o vigia do Vite morre com EBUSY ao esbarrar num deles — o que derruba
       * o dev server e aborta o `tauri dev` inteiro.
       *
       * No Linux e no macOS isso não acontece, então a falta desta linha passa
       * despercebida até alguém rodar no Windows. Não remover. */
      ignored: ["**/src-tauri/**"],
    },
  },

  /* O Tauri publica as suas variáveis com este prefixo; sem declarar, elas não
   * chegam ao código do frontend. */
  envPrefix: ["VITE_", "TAURI_ENV_"],

  build: {
    /* O alvo acompanha o motor real de cada plataforma, em vez de um valor
     * único: o Windows usa WebView2 (base Chromium) e macOS/Linux usam WebKit.
     * Mirar no motor certo evita transpilar à toa ou gerar sintaxe que o
     * WebKit mais antigo não entende. */
    target:
      process.env.TAURI_ENV_PLATFORM === "windows" ? "chrome105" : "safari13",

    /* Em produção o bundle vai minificado e sem sourcemap. Antes o sourcemap
     * era gerado sempre, o que colocava ~800 kB de mapa dentro do instalador
     * sem nenhum uso — contraria a leveza que motivou escolher o Tauri
     * (PERFORMANCE.md, seção 6). Em debug os dois continuam ligados. */
    minify: !process.env.TAURI_ENV_DEBUG,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
  },
});
