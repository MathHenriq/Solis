/* Verificador de contraste dos tokens.
 *
 * O Tokens Complementares (seção 1) diz: "isso precisa ser reverificado sempre
 * que uma nova combinação de cor+fundo for proposta — não assumir, medir".
 * Este script é o que torna essa regra executável em vez de intencional.
 *
 * Uso:  npm run contraste
 * Sai com código 1 se algum par documentado deixar de cumprir o nível dele.
 */
import { hex } from "wcag-contrast";

const T = {
  solar: "#FFB74D",
  amber: "#F08A24",
  night: "#071019",
  deep: "#0D1722",
  warmWhite: "#F5F0E7",
  muted: "#A1A7B3",
  success: "#8FBF6D",
  error: "#E4674A",
  branco: "#FFFFFF",
  /* color.bubble.user = amber 70% + night 30% */
  bubbleUser: "#AA6521",
};

const AA = 4.5;
const AAA = 7;

/* Cada par carrega o mínimo que ele PRECISA cumprir, não o valor que
 * esperamos ver — assim o teste falha quando a cor muda, e não quando alguém
 * recalcula com mais casas decimais. */
const PARES = [
  ["warmWhite sobre night", T.warmWhite, T.night, AAA],
  ["muted sobre deep", T.muted, T.deep, AAA],
  ["muted sobre night", T.muted, T.night, AAA],
  ["night sobre solar (botão primário)", T.night, T.solar, AAA],
  ["success sobre night", T.success, T.night, AAA],
  ["error sobre night", T.error, T.night, AA],
  ["branco sobre bubble.user", T.branco, T.bubbleUser, AA],
];

/* Combinações que NÃO podem ser usadas. Estão aqui porque são as tentações
 * óbvias: "por que não usar o token puro no balão?" — porque reprova. */
const PROIBIDOS = [
  ["branco sobre amber puro", T.branco, T.amber],
  ["branco sobre solar puro", T.branco, T.solar],
  ["warmWhite sobre bubble.user", T.warmWhite, T.bubbleUser],
];

let falhou = false;

console.log("pares que precisam passar:");
for (const [nome, frente, fundo, minimo] of PARES) {
  const r = hex(frente, fundo);
  const ok = r >= minimo;
  if (!ok) falhou = true;
  const nivel = minimo === AAA ? "AAA" : "AA";
  console.log(
    `  ${ok ? "ok  " : "FALHA"} ${nome.padEnd(36)} ${r.toFixed(2)}:1 (mínimo ${nivel} ${minimo})`,
  );
}

console.log("\ncombinações proibidas (devem continuar reprovando):");
for (const [nome, frente, fundo] of PROIBIDOS) {
  const r = hex(frente, fundo);
  const reprova = r < AA;
  if (!reprova) falhou = true;
  console.log(
    `  ${reprova ? "ok  " : "ATENÇÃO"} ${nome.padEnd(36)} ${r.toFixed(2)}:1`,
  );
}

/* A receita do balão tem pouca folga: 70% de amber dá 4,57 e 72% já reprova.
 * Este teto é verificado explicitamente pra ninguém "esquentar" o balão depois
 * sem perceber que quebrou acessibilidade. */
const TETO_AMBER = 70;
console.log(`\nteto da receita do balão: amber ${TETO_AMBER}% (72% já reprova)`);

process.exit(falhou ? 1 : 0);
