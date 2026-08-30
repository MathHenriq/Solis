import { useState } from 'react';
import { Icone } from '../components/icons';

/** Tela de Memória — lista e busca.
 *
 *  Medidas de docs/solis-tokens.json → layout.memoria, tiradas de
 *  referencias/telas/09-memoria.png.
 *
 *  TODO O x DESTA TELA É MEDIDO A PARTIR DA DIVISÓRIA DA SIDEBAR, não da borda
 *  da janela: a referência veio com sidebar de 267px e a do app tem 200px, que
 *  é o valor das 3 telas de tema já aprovadas. Medir da borda deslocaria a tela
 *  inteira em 67px.
 *
 *  Da referência foi adotado o LAYOUT. A paleta dela (canvas #0D1216, divisória
 *  #232629, sidebar com superfície própria) NÃO foi: canvas e divisória estavam
 *  fechados desde as 3 telas de tema, o gerador recebeu os hexes exatos no
 *  prompt e não os respeitou. Ver layout.memoria._divergencias. */

type Memoria = {
  id: number;
  texto: string;
  origem: string;
  data: string;
};

/** PROVISÓRIO: dados de exemplo, os mesmos da referência, pra a tela poder ser
 *  medida contra ela. Sai quando o SQLite/FTS5 entrar. */
const EXEMPLO: Memoria[] = [
  {
    id: 1,
    texto: 'Prefere respostas diretas, sem introdução longa. Gosta que eu vá direto ao ponto e deixe o contexto pro final.',
    origem: 'Preferências de comunicação',
    data: 'há 3 dias',
  },
  { id: 2, texto: 'Trabalha melhor de manhã cedo, entre 6h e 10h.', origem: 'Rotina e produtividade', data: 'há 5 dias' },
  {
    id: 3,
    texto: 'Está construindo o Solis, um assistente pessoal local-first para desktop. Stack: Tauri, React, TypeScript, Python com FastAPI, SQLite e Ollama. Prioriza leveza e fluidez acima de tudo.',
    origem: 'Projeto Solis',
    data: '12 mar',
  },
  { id: 4, texto: 'Tem alergia a frutos do mar.', origem: 'Saúde e bem-estar', data: '10 mar' },
  {
    id: 5,
    texto: 'A referência visual do projeto é sempre a fonte da verdade. Nada é feito de memória ou por aproximação.',
    origem: 'Projeto Solis',
    data: '8 mar',
  },
  { id: 6, texto: 'Prefere ser chamado de Matheus, não de Mateus.', origem: 'Preferências pessoais', data: 'ontem' },
  { id: 7, texto: 'Gosta de estudar com música instrumental e fones over-ear.', origem: 'Rotina e produtividade', data: 'há 7 dias' },
];

/** PROVISÓRIO junto com EXEMPLO: o total não é o tamanho da lista carregada. A
 *  lista é paginada e o contador vem de um COUNT no banco — mostrar
 *  EXEMPLO.length aqui seria mentir sobre o que a tela conta. */
const TOTAL: number = 128;

export function Memoria() {
  const [busca, definirBusca] = useState('');
  const filtradas = busca
    ? EXEMPLO.filter((m) => (m.texto + m.origem).toLowerCase().includes(busca.toLowerCase()))
    : EXEMPLO;

  // bg-canvas, e não fundo transparente como a Conversa: esta lista sangra até a
  // base da janela, e sobre a foto do horizonte o texto perderia o contraste que
  // a ancoragem da cena devolveu. A referência mostra fundo liso. O Horizonte
  // continua montado no shell — a Camada 1 não remonta —, só não aparece por
  // baixo desta tela.
  return (
    <main className="relative flex-1 flex flex-col overflow-hidden bg-canvas" style={{ zIndex: 1 }}>
      <div
        className="shrink-0"
        style={{
          paddingLeft: 'var(--mem-pad-l)',
          paddingRight: 'var(--mem-pad-r)',
          paddingTop: 'var(--mem-titulo-top)',
        }}
      >
        {/* O título é a única serifada da tela, como a saudação da Conversa. */}
        <h1
          className="font-display text-text-primary leading-none"
          style={{ fontSize: 'var(--mem-titulo)' }}
        >
          Memória
        </h1>

        <p
          className="text-text-secondary"
          style={{
            fontSize: 'var(--mem-contagem)',
            marginTop: 'var(--mem-contagem-gap)',
          }}
        >
          {TOTAL === 0 ? 'Nenhuma memória ainda' : `${TOTAL} memórias`}
        </p>

        <div
          className="flex items-center border border-divider"
          style={{
            marginTop: 'var(--mem-busca-gap)',
            height: 'var(--mem-busca-h)',
            borderRadius: 'var(--mem-busca-raio)',
          }}
        >
          <span className="text-text-secondary shrink-0" style={{ paddingLeft: 22, paddingRight: 16 }}>
            <Icone nome="buscar" tamanho={19} />
          </span>
          <input
            className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
            style={{ fontSize: 'var(--mem-item-texto)', paddingRight: 22 }}
            placeholder="Buscar nas memórias…"
            aria-label="Buscar nas memórias"
            value={busca}
            onChange={(e) => definirBusca(e.target.value)}
          />
        </div>
      </div>

      {/* A lista rola sozinha e sangra até a base da janela: na referência o
          sétimo item aparece cortado pela borda, e é esse corte que diz que há
          mais coisa abaixo. Por isso a lista não tem padding inferior. */}
      <ul
        className="flex-1 overflow-y-auto"
        style={{
          marginTop: 'var(--mem-lista-gap)',
          paddingLeft: 'var(--mem-pad-l)',
          paddingRight: 'var(--mem-pad-r)',
        }}
      >
        {filtradas.map((m) => (
          <li
            key={m.id}
            className="border-b border-divider [&:hover]:bg-[var(--mem-hover)]"
            style={{
              paddingTop: 'var(--mem-item-pad-y)',
              paddingBottom: 'var(--mem-item-pad-y)',
            }}
          >
            {/* A data é ancorada na borda direita do bloco, não colada no fim
                do texto: na referência ela forma uma coluna própria, alinhada
                entre todos os itens, independente do tamanho de cada texto. */}
            <div className="flex items-start gap-lg">
              {/* O teto de largura é medido: sem ele o texto se espalha até a
                  coluna da data e o item que na referência ocupa 2 linhas passa
                  a caber em 1, mudando a altura de toda a lista. */}
              <p
                className="flex-1 text-text-primary"
                style={{
                  fontSize: 'var(--mem-item-texto)',
                  lineHeight: 'var(--mem-item-lh)',
                  maxWidth: 'var(--mem-texto-max)',
                }}
              >
                {m.texto}
              </p>
              <span
                className="text-text-secondary shrink-0 whitespace-nowrap ml-auto"
                style={{ fontSize: 'var(--mem-data)' }}
              >
                {m.data}
              </span>
            </div>
            <p
              className="text-text-secondary"
              style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}
            >
              de: {m.origem}
            </p>
          </li>
        ))}
      </ul>
    </main>
  );
}
