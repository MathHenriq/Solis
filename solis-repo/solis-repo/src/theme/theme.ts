/** Sistema de temas. Fonte dos valores: docs/solis-tokens.json → themes,
 *  traduzido pra CSS em src/styles/tokens.css (gerado). Aqui só vive a
 *  IDENTIDADE do tema — nenhuma cor passa por JavaScript. */

export const TEMAS = ['espacial', 'claro', 'dark'] as const;
export type Tema = (typeof TEMAS)[number];

/** Decidido com o Matheus: dark não carrega asset fotográfico no primeiro
 *  paint e é o único tema em que o ciclo do dia roda. */
export const TEMA_PADRAO: Tema = 'dark';

/** Duplicados no bootstrap inline do index.html, que roda antes do bundle e
 *  não pode importar daqui. design/checar-regras.py falha se divergirem. */
export const CHAVE_TEMA = 'solis.appearance.theme';
export const CHAVE_CENA = 'solis.appearance.scene';

export function ehTema(v: unknown): v is Tema {
  return typeof v === 'string' && (TEMAS as readonly string[]).includes(v);
}

/** Troca o tema mexendo num atributo, nunca distribuindo cor por Context.
 *  A Camada 1 do SOLIS_SIGNATURE.md é montada uma vez no shell e não pode
 *  remontar na troca de tema — um atributo só repinta, um valor de Context
 *  re-renderiza a árvore inteira e arrisca remontar a cena. */
export function aplicarTema(tema: Tema): void {
  document.documentElement.dataset.theme = tema;
}

export function aplicarCena(ligada: boolean): void {
  // "Exibir imagem de fundo" desligado cai na versão sólida da paleta do
  // mesmo tema — a cena é uma camada sobre --canvas, não o fundo em si.
  document.documentElement.dataset.scene = ligada ? 'on' : 'off';
}
