/** FONTE ÚNICA da navegação (CLAUDE.md, regra 4). A Sidebar e a IconBar
 *  consomem daqui — nunca hardcodar a lista em dois lugares, que é o que
 *  produziu telas com um item a mais/a menos entre si.
 *
 *  Os rótulos têm que bater exatamente com docs/solis-tokens.json →
 *  navigation.items. design/checar-regras.py falha se divergirem.
 *
 *  ATENÇÃO: as 3 telas da Fase 2 mostram só 7 itens, sem "Modelos locais".
 *  Confirmado com o Matheus como omissão do gerador de imagem, não decisão de
 *  produto — a lista oficial são os 8 abaixo.
 *
 *  Ícone ainda não entra aqui de propósito: o glifo de cada item se resolve
 *  contra a referência quando a Sidebar for construída (Regra 1), não de
 *  memória agora. */

export type ItemNav = {
  readonly id: string;
  readonly rotulo: string;
  readonly rota: string;
};

export const ITENS_NAV: readonly ItemNav[] = [
  { id: 'conversa',      rotulo: 'Conversa',      rota: '/' },
  { id: 'memoria',       rotulo: 'Memória',       rota: '/memoria' },
  { id: 'modelos',       rotulo: 'Modelos locais', rota: '/modelos' },
  { id: 'ferramentas',   rotulo: 'Ferramentas',   rota: '/ferramentas' },
  { id: 'tarefas',       rotulo: 'Tarefas',       rota: '/tarefas' },
  { id: 'agenda',        rotulo: 'Agenda',        rota: '/agenda' },
  { id: 'conhecimento',  rotulo: 'Conhecimento',  rota: '/conhecimento' },
  { id: 'configuracoes', rotulo: 'Configurações', rota: '/configuracoes' },
] as const;
