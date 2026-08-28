/** Ícones da interface.
 *
 *  Grid 24×24, traço 2, cap e join redondos — a especificação de `icon` em
 *  docs/solis-tokens.json. Cada glifo foi desenhado contra a ampliação do
 *  correspondente em referencias/telas/tema-dark.png (Regra 1: nada de
 *  memória), e a comparação lado a lado está em
 *  design/icones-validacao.png.
 *
 *  `configuracoes` não é desenhado à mão: a roseta de 8 lóbulos é calculada
 *  (raios 9,5/7,6 interpolados por Catmull-Rom) porque acertar 16 pontos de
 *  controle no olho não dá o mesmo resultado. Ver design/gerar-engrenagem.py.
 *
 *  A cor NUNCA é fixada aqui — `stroke="currentColor"` faz o ícone herdar a
 *  cor do contexto, que é o que permite o mesmo componente servir os 3 temas
 *  e o estado ativo (acento) sem variante. */

import type { SVGProps } from 'react';

const CAMINHOS = {
  // Redesenhado contra o mapa de pixels da referência a 19px: corpo de 19x16
  // (não 19x13 como estava), rabo de 3px de base descendo 4 abaixo do corpo e
  // deslocado 2px à esquerda do centro. IoU contra a referência, no app: 0,27 -> 0,64.
  'conversa':
    'M4 1H20A2.4 2.4 0 0 1 22.4 3.4V16.8A2.4 2.4 0 0 1 20 19.2H10.7L8.2 23 7.8 19.2H4A2.4 2.4 0 0 1 1.6 16.8V3.4A2.4 2.4 0 0 1 4 1Z M6.6 8.4H16.2 M9 11.6H12.6',
  'memoria':
    'M12 11.2a3.6 3.6 0 1 0 0-7.2 3.6 3.6 0 0 0 0 7.2z M4.8 20.4a7.2 7.2 0 0 1 14.4 0z',
  'modelos':
    'M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z M3.3 7 12 12l8.7-5 M12 22V12',
  'ferramentas':
    'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z',
  'tarefas':
    'M6 3h12a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3z M7.8 12.2l2.9 2.9 5.5-5.9',
  'agenda':
    'M4.5 5.6h15a1.5 1.5 0 0 1 1.5 1.5v12.4a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 19.5V7.1a1.5 1.5 0 0 1 1.5-1.5z M8.2 2.7v5 M15.8 2.7v5 M3 10.6h18',
  'conhecimento':
    'M11.3 6.6a3.4 3.4 0 0 0-3.4-2.4H4.4a1.4 1.4 0 0 0-1.4 1.4v12.1a1.4 1.4 0 0 0 1.4 1.4h6.9z M12.7 6.6a3.4 3.4 0 0 1 3.4-2.4h3.5A1.4 1.4 0 0 1 21 5.6v12.1a1.4 1.4 0 0 1-1.4 1.4h-6.9z',
  'configuracoes':
    'M12.00 2.50C10.49 2.50 10.84 4.26 9.09 4.98C7.35 5.70 6.35 4.21 5.28 5.28C4.21 6.35 5.70 7.35 4.98 9.09C4.26 10.84 2.50 10.49 2.50 12.00C2.50 13.51 4.26 13.16 4.98 14.91C5.70 16.65 4.21 17.65 5.28 18.72C6.35 19.79 7.35 18.30 9.09 19.02C10.84 19.74 10.49 21.50 12.00 21.50C13.51 21.50 13.16 19.74 14.91 19.02C16.65 18.30 17.65 19.79 18.72 18.72C19.79 17.65 18.30 16.65 19.02 14.91C19.74 13.16 21.50 13.51 21.50 12.00C21.50 10.49 19.74 10.84 19.02 9.09C18.30 7.35 19.79 6.35 18.72 5.28C17.65 4.21 16.65 5.70 14.91 4.98C13.16 4.26 13.51 2.50 12.00 2.50Z M12 14.8a2.8 2.8 0 1 0 0-5.6 2.8 2.8 0 0 0 0 5.6z',
  'nova-tarefa':
    'M6 3h12a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3z M7.8 12.2l2.9 2.9 5.5-5.9',
  'buscar':
    'M10.8 18.6a7.8 7.8 0 1 0 0-15.6 7.8 7.8 0 0 0 0 15.6z M21 21l-4.7-4.7',
  'resumir':
    'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z M14 3v5h5 M8.6 13h6.8 M8.6 16.6h4.6',
  'analisar':
    'M3.5 18.5 9 13l3.5 3.5L21 8 M16 8h5v5',
  'microfone':
    'M12 15.2a3.2 3.2 0 0 0 3.2-3.2V6.2a3.2 3.2 0 0 0-6.4 0V12a3.2 3.2 0 0 0 3.2 3.2z M19 11.4V12a7 7 0 0 1-14 0v-.6 M12 19v3',
  'enviar':
    'M21.5 2.5 11 13 M21.5 2.5 14.8 21.5l-3.8-8.5-8.5-3.8z',
  'chevron':
    'M6 9l6 6 6-6',
} as const;

export type NomeIcone = keyof typeof CAMINHOS;

type Props = Omit<SVGProps<SVGSVGElement>, 'name'> & {
  nome: NomeIcone;
  /** Número em px ou qualquer comprimento CSS — quem chama passa a custom
   *  property do contexto (ex.: 'var(--sidebar-icon)') pra que o tamanho venha
   *  do token e não de um default escondido aqui dentro. */
  tamanho?: number | string;
};

export function Icone({ nome, tamanho = 'var(--icon-xs)', style, ...resto }: Props) {
  // O tamanho vai por `style`, nunca pelos atributos width/height: atributo de
  // SVG é XML e não aceita var() — passar a custom property por ali faz o
  // navegador descartar o valor e o ícone estoura pra 100% do contêiner.
  return (
    <svg
      style={{ width: tamanho, height: tamanho, ...style }}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...resto}
    >
      <path d={CAMINHOS[nome]} />
    </svg>
  );
}
