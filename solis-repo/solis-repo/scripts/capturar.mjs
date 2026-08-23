/* Captura a tela indicada rodando no dev server, no tamanho real da janela,
 * pra comparar lado a lado com a imagem de referência.
 *
 * Existe porque a Regra 2 exige medir, não olhar: "parecido" é reprovado igual
 * a "errado". Comparar um print do app com a referência é o único jeito de
 * afirmar que bate — e o único jeito de mostrar onde não bate.
 *
 * Uso:  node scripts/capturar.mjs /memoria saida.png
 *       (com `npm run dev` rodando em outro terminal)
 */
import { chromium } from "playwright";

const rota = process.argv[2] ?? "/";
const saida = process.argv[3] ?? "captura.png";

/* Medido das referências: a janela desenhada nos mockups tem ~1495x970 px de
 * mockup, e a largura-alvo do app é 1440 CSS px — fator ~0.9635. É esse fator
 * que converte qualquer medida tirada das imagens. */
export const ESCALA_MOCKUP = 0.9635;
const LARGURA = 1440;
const ALTURA = 936;

const navegador = await chromium.launch({
  // O Chromium do ambiente, quando existe. Local, cai no download padrão.
  executablePath: process.env.CHROMIUM_PATH || undefined,
});
const pagina = await navegador.newPage({
  viewport: { width: LARGURA, height: ALTURA },
});

const problemas = [];
pagina.on("pageerror", (e) => problemas.push(String(e)));
pagina.on("response", (r) => {
  if (r.status() >= 400) problemas.push(`${r.status()} ${r.url()}`);
});

await pagina.goto(`http://localhost:1420${rota}`, { waitUntil: "networkidle" });
await pagina.waitForTimeout(1200);
await pagina.screenshot({ path: saida });
await navegador.close();

console.log(`captura: ${saida}`);
console.log(problemas.length ? `problemas: ${problemas.join("\n")}` : "sem erros de console ou rede");
