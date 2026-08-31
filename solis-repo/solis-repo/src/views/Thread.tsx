import type { ReactNode } from 'react';
import { Icone } from '../components/icons';
import { SolisSimbolo } from '../components/SolisSimbolo';

/** Conversa com thread em andamento — o outro estado da tela de Conversa.
 *  Referência: referencias/telas/18-conversa-thread.png.
 *
 *  A diferença entre quem fala é deliberadamente SUTIL, e não dois balões
 *  coloridos de aplicativo de mensagem:
 *
 *    - a pessoa vem à direita, num bloco com véu de fundo e teto de 66% da
 *      largura, porque o que ela escreve é curto e delimitado;
 *    - o Solis vem à esquerda, sem fundo nenhum, ocupando a largura toda, com o
 *      símbolo marcando quem fala. A resposta dele é texto longo, e enfiar texto
 *      longo dentro de um balão o transforma numa coluna estreita e cansativa.
 *
 *  Não há confirmação de leitura. Uma das gerações da referência trouxe os dois
 *  tiquinhos de "lida", e foi descartada: não existe entrega nem leitura aqui —
 *  o Solis roda na mesma máquina, não há rede entre as pontas e não há outra
 *  pessoa do outro lado. Ver referencias/telas/_variantes/LEIA-ME.md.
 *
 *  PROVISÓRIO: a thread é estática e o cursor não pisca de verdade contra um
 *  stream. Quando o Ollama entrar, `digitando` vira o estado real do stream. */

type Turno =
  | { de: 'pessoa'; hora: string; texto: string }
  | { de: 'solis'; hora: string; blocos: ReactNode[]; digitando?: boolean };

const THREAD: Turno[] = [
  { de: 'pessoa', hora: '10:32', texto: 'Me lembra o que a gente decidiu sobre o fundo da tela?' },
  {
    de: 'solis',
    hora: '10:33',
    blocos: [
      'Decidimos ancorar a foto de nascer do sol na parte de baixo da tela. Assim o texto e os controles ficam sempre sobre fundo liso, com contraste confiável em qualquer conteúdo.',
      'Se a foto ocupasse mais altura, o texto no topo perderia contraste contra o horizonte e as áreas claras da imagem.',
      'Cada tema usa uma foto diferente, sempre com a mesma âncora:',
      ['Espacial: tons quentes e atmosfera leve.', 'Dark: maior profundidade e foco no conteúdo.'],
      'A posição é fixa nos três temas, pra manter a hierarquia visual igual em todos.',
    ],
  },
  { de: 'pessoa', hora: '10:36', texto: 'E o contraste, ficou dentro do padrão?' },
  {
    de: 'solis',
    hora: '10:36',
    digitando: true,
    blocos: ['Sim. O contraste atende aos níveis AA do WCAG em todos os tem'],
  },
];

function Paragrafo({ bloco }: { bloco: ReactNode }) {
  if (Array.isArray(bloco)) {
    return (
      <ul style={{ marginTop: 'var(--th-par-gap)' }}>
        {bloco.map((li, i) => (
          <li key={i} className="text-text-secondary flex gap-md" style={{ marginTop: i ? 8 : 0 }}>
            <span aria-hidden className="text-accent">•</span>
            <span>{li}</span>
          </li>
        ))}
      </ul>
    );
  }
  return <p style={{ marginTop: 'var(--th-par-gap)' }}>{bloco}</p>;
}

export function Thread() {
  return (
    <main className="relative flex-1 flex flex-col overflow-hidden bg-canvas" style={{ zIndex: 1 }}>
      {/* A thread rola e a primeira mensagem entra cortada pela borda de cima —
          é o corte que diz que há histórico acima. */}
      <div
        className="flex-1 overflow-y-auto"
        style={{ paddingLeft: 'var(--mem-pad-l)', paddingRight: 'var(--mem-pad-r)', paddingTop: 'var(--th-turno-gap)' }}
      >
        {THREAD.map((t, i) =>
          t.de === 'pessoa' ? (
            <div key={i} className="flex items-start justify-end gap-lg" style={{ marginTop: 'var(--th-turno-gap)' }}>
              <span className="text-text-secondary shrink-0" style={{ fontSize: 'var(--th-hora)', paddingTop: 18 }}>
                {t.hora}
              </span>
              <div
                className="text-text-primary"
                style={{
                  maxWidth: 'var(--th-balao-max)',
                  background: 'var(--mem-hover)',
                  borderRadius: 'var(--th-balao-raio)',
                  padding: 'var(--th-balao-py) var(--th-balao-px)',
                  fontSize: 'var(--mem-item-texto)',
                  lineHeight: 'var(--mem-item-lh)',
                }}
              >
                {t.texto}
              </div>
            </div>
          ) : (
            <div key={i} className="flex items-start" style={{ marginTop: 'var(--th-turno-gap)', gap: 'var(--th-avatar-gap)' }}>
              {/* Só o símbolo, sem o wordmark: no tamanho de avatar a palavra
                  SOLIS vira borrão, e wordmark ilegível é pior que nenhum. */}
              <SolisSimbolo
                className="text-accent shrink-0"
                style={{ width: 'var(--th-avatar)', height: 'auto', marginTop: 6 }}
              />
              <div className="flex-1">
                <div className="text-text-secondary" style={{ fontSize: 'var(--th-hora)' }}>{t.hora}</div>
                <div
                  className="text-text-primary"
                  style={{ fontSize: 'var(--mem-item-texto)', lineHeight: 'var(--mem-item-lh)' }}
                >
                  {t.blocos.map((b, j) => (
                    <Paragrafo key={j} bloco={b} />
                  ))}
                  {t.digitando && (
                    <span
                      aria-label="Solis está respondendo"
                      className="inline-block bg-text-primary align-middle"
                      style={{ width: 2, height: 20, marginLeft: 3, transform: 'translateY(-2px)' }}
                    />
                  )}
                </div>
              </div>
            </div>
          ),
        )}
        <div style={{ height: 'var(--th-turno-gap)' }} />
      </div>

      <div
        className="shrink-0"
        style={{
          paddingLeft: 'var(--mem-pad-l)',
          paddingRight: 'var(--mem-pad-r)',
          paddingBottom: 'var(--th-composer-base)',
        }}
      >
        <form
          className="flex items-center border border-divider rounded-composer"
          style={{ height: 'var(--th-composer-h)' }}
          onSubmit={(e) => e.preventDefault()}
        >
          <input
            className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
            style={{ paddingLeft: 29, fontSize: 'var(--mem-item-texto)' }}
            placeholder="Fale com o Solis…"
            aria-label="Fale com o Solis"
          />
          <button type="button" className="text-text-secondary p-sm" aria-label="Falar">
            <Icone nome="microfone" tamanho={22} />
          </button>
          <button
            type="submit"
            className="bg-accent text-canvas flex items-center justify-center shrink-0"
            style={{ width: 52, height: 52, borderRadius: 999, marginLeft: 10, marginRight: 18 }}
            aria-label="Enviar"
          >
            <Icone nome="enviar" tamanho={22} />
          </button>
        </form>
      </div>
    </main>
  );
}
