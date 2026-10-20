import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Icone } from '../components/icons';
import { SolisSimbolo } from '../components/SolisSimbolo';
import type { Turno } from '../conversa';

/** Conversa com thread em andamento — o outro estado da tela de Conversa.
 *  Referência: referencias/telas/18-conversa-thread.png.
 *
 *  A diferença entre quem fala é deliberadamente SUTIL, e não dois balões
 *  coloridos de aplicativo de mensagem:
 *
 *    - a pessoa vem à direita, num bloco com véu de fundo e teto de 66% da
 *      largura, porque o que ela escreve é curto e delimitado;
 *    - o Solis vem à esquerda, sem fundo nenhum, com o símbolo marcando quem
 *      fala. A resposta dele é texto longo, e enfiar texto longo dentro de um
 *      balão o transforma numa coluna estreita e cansativa. Sem balão, mas com
 *      teto de leitura (--th-texto-max): a referência quebra a linha em ~70
 *      caracteres, e sem teto uma janela larga passava de 200.
 *
 *  Não há confirmação de leitura. Uma das gerações da referência trouxe os dois
 *  tiquinhos de "lida", e foi descartada: não existe entrega nem leitura aqui —
 *  o Solis roda na mesma máquina, não há rede entre as pontas e não há outra
 *  pessoa do outro lado. Ver referencias/telas/_variantes/LEIA-ME.md.
 *
 *  A resposta chega em pedaços e o cursor fica no fim enquanto ela chega. */

/** Negrito em markdown (`**assim**`) vira <strong>. Fragmento e não array:
 *  `Paragrafo` lê array como lista. */
function negrito(texto: string): ReactNode {
  const partes = texto.split(/\*\*(.+?)\*\*/g);
  return <>{partes.map((p, i) => (i % 2 ? <strong key={i}>{p}</strong> : p))}</>;
}

/** O texto do modelo vem em markdown. Daqui sai só o que a thread já sabe
 *  desenhar — parágrafo e lista com marcador —, mais o negrito. Título (`##`)
 *  vira parágrafo em negrito; o resto passa como texto. Um renderizador de
 *  markdown inteiro seria uma dependência pra três casos. */
function blocosDe(texto: string): ReactNode[] {
  const saida: ReactNode[] = [];
  let paragrafo: string[] = [];
  let lista: ReactNode[] = [];
  const fecharParagrafo = () => {
    if (paragrafo.length) saida.push(negrito(paragrafo.join('\n')));
    paragrafo = [];
  };
  const fecharLista = () => {
    if (lista.length) saida.push(lista);
    lista = [];
  };
  for (const linha of texto.split('\n')) {
    const item = /^\s*[-*•]\s+(.*)$/.exec(linha);
    const titulo = /^#{1,6}\s+(.*)$/.exec(linha);
    if (item) {
      fecharParagrafo();
      lista.push(negrito(item[1]));
    } else if (!linha.trim()) {
      fecharParagrafo();
      fecharLista();
    } else {
      fecharLista();
      paragrafo.push(titulo ? `**${titulo[1]}**` : linha);
    }
  }
  fecharParagrafo();
  fecharLista();
  return saida;
}

/** Cursor de "ainda escrevendo". Vai DENTRO do último parágrafo (ou item), no
 *  fim do texto — como na referência. Fora dele cairia numa linha própria. */
const CURSOR = (
  <span
    aria-label="Solis está respondendo"
    className="inline-block bg-text-primary align-middle"
    style={{ width: 2, height: 20, marginLeft: 3, transform: 'translateY(-2px)' }}
  />
);

function Paragrafo({ bloco, fim }: { bloco: ReactNode; fim?: ReactNode }) {
  if (Array.isArray(bloco)) {
    return (
      <ul style={{ marginTop: 'var(--th-par-gap)' }}>
        {bloco.map((li, i) => (
          <li key={i} className="text-text-secondary flex gap-md" style={{ marginTop: i ? 8 : 0 }}>
            <span aria-hidden className="text-accent">•</span>
            <span>
              {li}
              {i === bloco.length - 1 && fim}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  // pre-line: quebra simples dentro do parágrafo (um endereço, um passo a passo
  // numerado) continua quebrada.
  return (
    <p className="whitespace-pre-line" style={{ marginTop: 'var(--th-par-gap)' }}>
      {bloco}
      {fim}
    </p>
  );
}

export function Thread({
  turnos,
  respondendo,
  aoEnviar,
}: {
  turnos: Turno[];
  respondendo: boolean;
  aoEnviar: (texto: string) => void;
}) {
  const [rascunho, definirRascunho] = useState('');
  const rolagem = useRef<HTMLDivElement>(null);
  // A thread segue o texto que chega SÓ se a pessoa está no fim dela. Quem rolou
  // pra cima pra reler não pode ser puxado de volta a cada pedaço.
  const grudada = useRef(true);

  useEffect(() => {
    const el = rolagem.current;
    if (el && grudada.current) el.scrollTop = el.scrollHeight;
  }, [turnos]);

  return (
    <main className="relative flex-1 flex flex-col overflow-hidden bg-canvas" style={{ zIndex: 1 }}>
      {/* A thread rola e a primeira mensagem entra cortada pela borda de cima —
          é o corte que diz que há histórico acima. */}
      <div
        ref={rolagem}
        onScroll={(e) => {
          const el = e.currentTarget;
          grudada.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="flex-1 overflow-y-auto"
        style={{ paddingLeft: 'var(--mem-pad-l)', paddingRight: 'var(--mem-pad-r)', paddingTop: 'var(--th-turno-gap)' }}
      >
        {turnos.map((t, i) =>
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
                  {/* Aviso de erro em texto secundário: é o Solis falando do
                      sistema, não respondendo à pergunta. */}
                  <div
                    className={t.falha ? 'text-text-secondary' : undefined}
                    style={{ maxWidth: 'var(--th-texto-max)' }}
                  >
                    {/* Antes do primeiro pedaço não há bloco onde pôr o cursor:
                        ele ocupa um parágrafo vazio sozinho. */}
                    {(t.texto ? blocosDe(t.texto) : ['']).map((b, j, todos) => (
                      <Paragrafo key={j} bloco={b} fim={t.digitando && j === todos.length - 1 ? CURSOR : null} />
                    ))}
                  </div>
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
          style={{ height: 'var(--th-composer-h)', width: 'var(--composer-width)', maxWidth: '100%', marginInline: 'auto' }}
          onSubmit={(e) => {
            e.preventDefault();
            // O rascunho continua editável enquanto o Solis responde; só o
            // envio espera — duas perguntas cruzadas embaralhariam a thread.
            if (respondendo || !rascunho.trim()) return;
            grudada.current = true;
            aoEnviar(rascunho);
            definirRascunho('');
          }}
        >
          <input
            autoFocus
            value={rascunho}
            onChange={(e) => definirRascunho(e.target.value)}
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
            style={{
              width: 52,
              height: 52,
              borderRadius: 999,
              marginLeft: 10,
              marginRight: 18,
              opacity: respondendo ? 0.4 : 1,
            }}
            aria-label="Enviar"
            aria-disabled={respondendo}
          >
            <Icone nome="enviar" tamanho={22} />
          </button>
        </form>
      </div>
    </main>
  );
}
