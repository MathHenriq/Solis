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
 *  O `icone` de cada item foi resolvido contra a ampliação do glifo
 *  correspondente na referência — ver src/components/icons.tsx e a comparação
 *  em design/icones-validacao.png. "Modelos locais" saiu de
 *  referencias/telas/06-configuracoes.png, porque é o único item que não
 *  aparece nas 3 telas da Fase 2. */

import type { NomeIcone } from './components/icons';

export type ItemNav = {
  readonly id: string;
  readonly rotulo: string;
  readonly rota: string;
  readonly icone: NomeIcone;
};

export const ITENS_NAV: readonly ItemNav[] = [
  { id: 'conversa',      rotulo: 'Conversa',      rota: '/', icone: 'conversa' },
  { id: 'memoria',       rotulo: 'Memória',       rota: '/memoria', icone: 'memoria' },
  { id: 'modelos',       rotulo: 'Modelos locais', rota: '/modelos', icone: 'modelos' },
  { id: 'ferramentas',   rotulo: 'Ferramentas',   rota: '/ferramentas', icone: 'ferramentas' },
  { id: 'tarefas',       rotulo: 'Tarefas',       rota: '/tarefas', icone: 'tarefas' },
  { id: 'agenda',        rotulo: 'Agenda',        rota: '/agenda', icone: 'agenda' },
  { id: 'conhecimento',  rotulo: 'Conhecimento',  rota: '/conhecimento', icone: 'conhecimento' },
  { id: 'configuracoes', rotulo: 'Configurações', rota: '/configuracoes', icone: 'configuracoes' },
] as const;
