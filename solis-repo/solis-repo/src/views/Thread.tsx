import { useEffect, useRef, useState, type ReactNode } from 'react';
import { AvisosDepois, CartoesAprovacao, DobraEtapas, ListaEtapas } from '../components/EtapasResposta';
import { BotaoMicrofone } from '../components/BotaoMicrofone';
import { Botao } from '../components/Controles';
import { EscolhaClaude } from '../components/EscolhaClaude';
import { Icone } from '../components/icons';
import { SolisEstado } from '../components/SolisEstado';
import { SolisSimbolo } from '../components/SolisSimbolo';
import type { Turno } from '../conversa';
import { NOMES_CEREBRO, enviarAnexo, type Anexo } from '../servidor';
import { falaAutomatica, respostaFalada, useFala } from '../fala';
import { useVoz } from '../voz';


/** Conversa com thread em andamento — o outro estado da tela de Conversa.
 *  Referência: referencias/telas/18-conversa-thread.png.
 *
 *  A conversa vive numa COLUNA CENTRAL de até --th-coluna (768px), na
 *  proporção do Claude, e tudo se alinha a ela: a mensagem da pessoa à direita
 *  da coluna, a resposta ocupando a largura dela, o campo de digitar com a
 *  mesma largura. Antes a resposta ficava num teto de 540px encostada à
 *  esquerda e o balão ia pra borda direita da janela — numa janela larga
 *  sobrava um vazio no meio (pedido do Matheus, 08/11/2026).
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

/** Negrito em markdown (`**assim**`) vira <strong>, e `assim` vira código.
 *  Fragmento e não array: `Paragrafo` lê array como lista. */
function negrito(texto: string): ReactNode {
  // O código entre crases (`pytest`) também: aparecia cru, com as crases.
  const partes = texto.split(/(\*\*.+?\*\*|`[^`\n]+`)/g);
  return (
    <>
      {partes.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**') && p.length > 4) return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (p.startsWith('`') && p.endsWith('`') && p.length > 2)
          return (
            <code
              key={i}
              className="font-mono"
              style={{ fontSize: '0.9em', background: 'var(--mem-hover-forte)', padding: '1px 5px', borderRadius: 4 }}
            >
              {p.slice(1, -1)}
            </code>
          );
        return p;
      })}
    </>
  );
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
          <li key={i} className="flex gap-md" style={{ marginTop: i ? 8 : 0 }}>
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

/** Uma resposta do Solis. Enquanto não há texto, o símbolo pensa (glow no
 *  estado real) e as etapas aparecem embaixo do cabeçalho; quando o texto
 *  começa, elas recolhem numa linha acima dele, e o que veio depois da resposta
 *  (memória guardada) aparece embaixo do texto. Ref. 20-conversa-etapas.png. */
/** Ouvir a resposta. Desenho próprio, aprovado pelo Matheus em 09/11/2026
 *  (design/fala-validacao.png): o alto-falante no
 *  fim da linha da hora, que aparece no hover (como as ações da Memória) e fica
 *  à vista enquanto fala; falando, vira o quadrado de parar em accent. */
function BotaoOuvir({
  falando,
  preparando,
  falhou,
  aoOuvir,
  aoParar,
}: {
  falando: boolean;
  preparando: boolean;
  falhou: boolean;
  aoOuvir: () => void;
  aoParar: () => void;
}) {
  return (
    <>
      <button
        type="button"
        onClick={falando ? aoParar : aoOuvir}
        title={falando ? 'Parar' : 'Ouvir'}
        aria-label={falando ? 'Parar de falar' : 'Ouvir a resposta'}
        aria-pressed={falando}
        className={`inline-flex items-center justify-center align-middle transition-opacity
                    ${falando ? 'text-accent opacity-100' : 'text-text-secondary hover:text-text-primary opacity-0 group-hover:opacity-100 focus:opacity-100'}
                    ${preparando ? 'solis-ouvindo' : ''}`}
        style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', borderRadius: 'var(--mac-botao-raio)', marginLeft: 4, marginTop: -4, marginBottom: -4 }}
      >
        <Icone nome={falando ? 'parar' : 'fala'} tamanho="var(--mac-icone)" />
      </button>
      {falhou && <span className="text-[var(--erro)]"> · não consegui falar</span>}
    </>
  );
}

/** Ação pequena embaixo de uma fala (copiar, refazer, editar), no desenho do
 *  Ouvir: aparece no hover da fala, some fora dele. PROVISÓRIO — desenho
 *  próprio (11/11/2026), base no Claude: as ações discretas ao lado da hora. */
function BotaoAcao({
  icone,
  rotulo,
  aoClicar,
  feito = false,
}: {
  icone: 'copiar' | 'refazer' | 'lapis' | 'feito';
  rotulo: string;
  aoClicar: () => void;
  feito?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={aoClicar}
      title={rotulo}
      aria-label={rotulo}
      className={`inline-flex items-center justify-center align-middle transition-opacity
                  ${feito ? 'text-accent opacity-100' : 'text-text-secondary hover:text-text-primary opacity-0 group-hover:opacity-100 focus:opacity-100'}`}
      style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', borderRadius: 'var(--mac-botao-raio)', marginLeft: 4, marginTop: -4, marginBottom: -4 }}
    >
      <Icone nome={feito ? 'feito' : icone} tamanho="var(--mac-icone)" />
    </button>
  );
}

function BotaoCopiar({ texto }: { texto: string }) {
  const [copiado, definirCopiado] = useState(false);
  return (
    <BotaoAcao
      icone="copiar"
      rotulo={copiado ? 'Copiado' : 'Copiar a resposta'}
      feito={copiado}
      aoClicar={async () => {
        try {
          await navigator.clipboard.writeText(texto);
          definirCopiado(true);
          setTimeout(() => definirCopiado(false), 1500);
        } catch {
          /* sem permissão de área de transferência: o botão só não confirma */
        }
      }}
    />
  );
}

/** A fala do Matheus, com o editar no hover: a fala vira um campo; Enviar
 *  manda o texto novo no lugar dela (o que vinha depois sai), Esc cancela.
 *  PROVISÓRIO — desenho próprio, base no Claude. */
/** Um arquivo que vai (ou foi) junto com a fala. PROVISÓRIO — desenho
 *  próprio, base no Claude: a ficha do arquivo acima do texto, no tamanho dos
 *  chips da resposta (--et-chip-*), com a borda neutra. */
function FichaAnexo({ nome, estado, aoRemover }: { nome: string; estado?: 'enviando' | 'falhou'; aoRemover?: () => void }) {
  return (
    <span
      title={nome}
      className={`inline-flex items-center border border-divider ${estado === 'falhou' ? 'text-[var(--erro)]' : 'text-text-primary'}`}
      style={{
        maxWidth: 260,
        height: 'var(--et-chip-h)',
        padding: '0 var(--et-chip-px)',
        gap: 8,
        fontSize: 'var(--et-chip-texto)',
        borderRadius: 'var(--et-chip-raio)',
        opacity: estado === 'enviando' ? 0.6 : 1,
      }}
    >
      <Icone nome="documento" tamanho={14} className="text-text-secondary shrink-0" />
      <span className="truncate">{estado === 'falhou' ? `${nome} — não foi` : nome}</span>
      {aoRemover && (
        <button
          type="button"
          onClick={aoRemover}
          aria-label={`Tirar ${nome}`}
          className="text-text-secondary hover:text-text-primary shrink-0"
          style={{ marginRight: -4 }}
        >
          <Icone nome="adicionar" tamanho={14} style={{ transform: 'rotate(45deg)' }} />
        </button>
      )}
    </span>
  );
}

function FalaPessoa({ t, aoEditar }: { t: Turno; aoEditar?: (texto: string) => void }) {
  const [editando, definirEditando] = useState(false);
  const [texto, definirTexto] = useState(t.texto);
  const caixa = {
    maxWidth: 'var(--th-balao-max)',
    background: 'var(--mem-hover)',
    borderRadius: 'var(--th-balao-raio)',
    padding: 'var(--th-balao-py) var(--th-balao-px)',
    fontSize: 'var(--mem-item-texto)',
    lineHeight: 'var(--mem-item-lh)',
  } as const;
  if (editando && aoEditar) {
    const mandar = () => {
      if (!texto.trim()) return;
      definirEditando(false);
      aoEditar(texto);
    };
    return (
      <div className="flex flex-col items-end" style={{ marginTop: 'var(--th-turno-gap)' }}>
        <textarea
          autoFocus
          value={texto}
          onChange={(e) => definirTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') definirEditando(false);
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              mandar();
            }
          }}
          aria-label="Editar a mensagem"
          rows={Math.min(8, Math.max(2, texto.split('\n').length))}
          className="text-text-primary bg-transparent outline-none resize-none w-full"
          style={{ ...caixa, maxWidth: 'var(--th-balao-max)', border: '1px solid var(--divider)' }}
        />
        <div className="flex" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
          <Botao onClick={() => definirEditando(false)}>Cancelar</Botao>
          <Botao tipo="destaque" onClick={mandar} disabled={!texto.trim()}>
            Enviar
          </Botao>
        </div>
      </div>
    );
  }
  return (
    <div style={{ marginTop: 'var(--th-turno-gap)' }}>
      {t.anexos && (
        <div className="flex flex-wrap justify-end" style={{ gap: 8, marginBottom: 8 }}>
          {t.anexos.map((a) => (
            <FichaAnexo key={a.caminho} nome={a.nome} />
          ))}
        </div>
      )}
      <div className="group flex items-start justify-end gap-lg">
        <span className="text-text-secondary shrink-0 flex items-center" style={{ fontSize: 'var(--th-hora)', paddingTop: 18 }}>
          {aoEditar && (
            <BotaoAcao
              icone="lapis"
              rotulo="Editar a mensagem"
              aoClicar={() => {
                definirTexto(t.texto);
                definirEditando(true);
              }}
            />
          )}
          <span style={{ marginLeft: aoEditar ? 6 : 0 }}>{t.hora}</span>
        </span>
        <div className="text-text-primary whitespace-pre-wrap" style={caixa}>
          {t.texto}
        </div>
      </div>
    </div>
  );
}

function RespostaSolis({
  t,
  ouvir,
  aoRefazer,
}: {
  t: Turno;
  ouvir?: { falando: boolean; preparando: boolean; falhou: boolean; aoOuvir: () => void; aoParar: () => void };
  /** Só na última resposta, e fora de uma resposta em andamento. */
  aoRefazer?: () => void;
}) {
  const [aberta, definirAberta] = useState(false);
  const etapas = t.etapas ?? [];
  const vivo = !!t.digitando;
  const pensando = vivo && !t.texto;
  // Fora disto, a coluna do texto: avatar + respiro, a mesma da resposta.
  const coluna = 'calc(var(--th-avatar) + var(--th-avatar-gap))';
  return (
    <div className="group" style={{ marginTop: 'var(--th-turno-gap)' }}>
      {!pensando && etapas.length > 0 && (
        <div style={{ paddingLeft: coluna }}>
          <DobraEtapas etapas={etapas} vivo={vivo} aberta={aberta} aoAlternar={() => definirAberta((a) => !a)} />
          {aberta && <ListaEtapas etapas={etapas} vivo={vivo} />}
        </div>
      )}
      <div className="flex items-start" style={{ gap: 'var(--th-avatar-gap)' }}>
        {/* Só o símbolo, sem o wordmark: no tamanho de avatar a palavra SOLIS
            vira borrão, e wordmark ilegível é pior que nenhum. Ao vivo, o
            símbolo com glow no estado real (pensando, respondendo); pronto,
            o símbolo parado — na cor validada da thread (accent), e não no
            creme da referência 20. */}
        {vivo ? (
          <SolisEstado
            estado={pensando ? 'thinking' : 'responding'}
            halo="avatar"
            className="shrink-0 [&_.solis-arte]:text-accent"
            style={{ width: 'var(--th-avatar)', marginTop: 6 }}
          />
        ) : (
          <SolisSimbolo className="text-accent shrink-0" style={{ width: 'var(--th-avatar)', height: 'auto', marginTop: 6 }} />
        )}
        <div className="flex-1">
          {/* Quem respondeu, quando foi um modelo de nuvem: o que foi dito saiu
              da máquina, e o Matheus precisa saber disso. O local é o padrão
              silencioso — não precisa de etiqueta. */}
          <div className="text-text-secondary" style={{ fontSize: 'var(--th-hora)' }}>
            {t.hora}
            {/* Só quem não é o local: o local é o normal, não precisa de nome. */}
            {t.cerebro && t.cerebro !== 'local' && NOMES_CEREBRO[t.cerebro] && ` · ${NOMES_CEREBRO[t.cerebro]}`}
            {ouvir && !vivo && !t.falha && t.texto && <BotaoOuvir {...ouvir} />}
            {!vivo && !t.falha && t.texto && <BotaoCopiar texto={t.texto} />}
            {!vivo && aoRefazer && <BotaoAcao icone="refazer" rotulo="Refazer a resposta" aoClicar={aoRefazer} />}
          </div>
          {pensando ? (
            <div style={{ marginTop: 'var(--et-cabecalho)' }}>
              <ListaEtapas etapas={etapas} vivo />
            </div>
          ) : (
            <div className="text-text-primary" style={{ fontSize: 'var(--mem-item-texto)', lineHeight: 'var(--mem-item-lh)' }}>
              {/* Aviso de erro em texto secundário: é o Solis falando do
                  sistema, não respondendo à pergunta. */}
              <div className={t.falha ? 'text-text-secondary' : undefined} style={{ maxWidth: 'var(--th-texto-max)' }}>
                {(t.texto ? blocosDe(t.texto) : ['']).map((b, j, todos) => (
                  <Paragrafo key={j} bloco={b} fim={t.digitando && j === todos.length - 1 ? CURSOR : null} />
                ))}
              </div>
            </div>
          )}
          {vivo && <CartoesAprovacao etapas={etapas} />}
          <AvisosDepois etapas={etapas} />
        </div>
      </div>
    </div>
  );
}

export function Thread({
  turnos,
  respondendo,
  aoEnviar,
  conversa = null,
  ouvindo = false,
  aoParar,
  aoRefazer,
}: {
  turnos: Turno[];
  respondendo: boolean;
  /** `desde`: editar — a fala com esse id no banco sai, e o que vinha depois. */
  aoEnviar: (texto: string, desde?: number, anexos?: Anexo[]) => void;
  /** Para a resposta em andamento. */
  aoParar?: () => void;
  /** Refaz a última resposta. */
  aoRefazer?: () => void;
  conversa?: number | null;
  /** A palavra "Solis" foi ouvida e o que vem depois está sendo escutado. */
  ouvindo?: boolean;
}) {
  const [rascunho, definirRascunho] = useState('');
  // Os arquivos que vão com a próxima mensagem: sobem assim que escolhidos
  // (como no Claude), e a mensagem só sai quando todos subiram.
  const [pendentes, definirPendentes] = useState<{ id: number; nome: string; estado: 'enviando' | 'pronto' | 'falhou'; anexo?: Anexo }[]>([]);
  const seletor = useRef<HTMLInputElement>(null);
  const anexar = (arquivos: FileList | File[]) => {
    for (const arquivo of Array.from(arquivos)) {
      const id = Math.random();
      const nome = arquivo.name || 'colado.png';
      definirPendentes((ps) => [...ps, { id, nome, estado: 'enviando' }]);
      void enviarAnexo(arquivo).then((anexo) =>
        definirPendentes((ps) => ps.map((p) => (p.id === id ? { ...p, estado: anexo ? 'pronto' : 'falhou', anexo: anexo ?? undefined } : p))),
      );
    }
  };
  const subindo = pendentes.some((p) => p.estado === 'enviando');
  const campo = useRef<HTMLInputElement>(null);
  // O rascunho veio da voz: a resposta desta mensagem é falada sozinha.
  const ditado = useRef(false);
  const voz = useVoz((texto) => {
    definirRascunho((r) => (r.trim() ? `${r.trimEnd()} ${texto}` : texto));
    ditado.current = true;
    campo.current?.focus();
  });
  const fala = useFala(conversa);
  // Falou, ouve: quando a resposta de uma mensagem ditada termina de chegar,
  // ela é lida em voz alta.
  const ultima = turnos[turnos.length - 1];
  useEffect(() => {
    if (!ultima || ultima.de !== 'solis' || ultima.digitando || ultima.falha || !ultima.texto) return;
    if (!respostaFalada.proxima) return;
    respostaFalada.proxima = false;
    fala.ouvir(ultima.id, ultima.texto);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ultima?.id, ultima?.digitando]);
  const rolagem = useRef<HTMLDivElement>(null);
  // A thread segue o texto que chega SÓ se a pessoa está no fim dela. Quem rolou
  // pra cima pra reler não pode ser puxado de volta a cada pedaço.
  const grudada = useRef(true);

  useEffect(() => {
    const el = rolagem.current;
    if (el && grudada.current) el.scrollTop = el.scrollHeight;
  }, [turnos]);

  return (
    <main
      className="relative flex-1 flex flex-col overflow-hidden bg-canvas"
      style={{ zIndex: 1 }}
      // Arrastar arquivo pra conversa anexa, como no Claude.
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes('Files')) e.preventDefault();
      }}
      onDrop={(e) => {
        if (!e.dataTransfer.files.length) return;
        e.preventDefault();
        anexar(e.dataTransfer.files);
      }}
    >
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
        <div style={{ maxWidth: 'var(--th-coluna)', marginInline: 'auto' }}>
          {turnos.map((t, i) =>
            t.de === 'pessoa' ? (
              <FalaPessoa
                key={t.id}
                t={t}
                aoEditar={!respondendo && t.mensagem !== undefined ? (texto) => aoEnviar(texto, t.mensagem, t.anexos) : undefined}
              />
            ) : (
              <RespostaSolis
                key={t.id}
                t={t}
                aoRefazer={
                  !respondendo && i === turnos.length - 1 && turnos[i - 1]?.mensagem !== undefined ? aoRefazer : undefined
                }
                ouvir={{
                  falando: fala.falando === t.id,
                  preparando: fala.falando === t.id && fala.preparando,
                  falhou: fala.falhou === t.id,
                  aoOuvir: () => fala.ouvir(t.id, t.texto),
                  aoParar: fala.parar,
                }}
              />
            ),
          )}
          <div style={{ height: 'var(--th-turno-gap)' }} />
        </div>
      </div>

      <div
        className="shrink-0"
        style={{
          paddingLeft: 'var(--mem-pad-l)',
          paddingRight: 'var(--mem-pad-r)',
          paddingBottom: 'var(--th-composer-base)',
        }}
      >
        {pendentes.length > 0 && (
          <div
            className="flex flex-wrap"
            style={{ gap: 8, marginBottom: 8, width: '100%', maxWidth: 'var(--th-coluna)', marginInline: 'auto' }}
          >
            {pendentes.map((p) => (
              <FichaAnexo
                key={p.id}
                nome={p.nome}
                estado={p.estado === 'pronto' ? undefined : p.estado}
                aoRemover={() => definirPendentes((ps) => ps.filter((x) => x.id !== p.id))}
              />
            ))}
          </div>
        )}
        <form
          className="flex items-center border border-divider rounded-composer"
          style={{ height: 'var(--th-composer-h)', width: '100%', maxWidth: 'var(--th-coluna)', marginInline: 'auto' }}
          onSubmit={(e) => {
            e.preventDefault();
            // O rascunho continua editável enquanto o Solis responde; só o
            // envio espera — duas perguntas cruzadas embaralhariam a thread.
            const prontos = pendentes.flatMap((p) => (p.anexo ? [p.anexo] : []));
            if (respondendo || subindo || (!rascunho.trim() && !prontos.length)) return;
            grudada.current = true;
            respostaFalada.proxima = ditado.current && falaAutomatica();
            ditado.current = false;
            aoEnviar(rascunho, undefined, prontos);
            definirRascunho('');
            definirPendentes([]);
          }}
        >
          <input
            ref={campo}
            autoFocus
            value={rascunho}
            onChange={(e) => definirRascunho(e.target.value)}
            // Colar imagem (um print) anexa, como no Claude.
            onPaste={(e) => {
              if (!e.clipboardData.files.length) return;
              e.preventDefault();
              anexar(e.clipboardData.files);
            }}
            className={`flex-1 bg-transparent outline-none text-text-primary ${voz.erro ? 'placeholder:text-[var(--erro)]' : 'placeholder:text-text-placeholder'}`}
            style={{ paddingLeft: 29, fontSize: 'var(--mem-item-texto)' }}
            placeholder={ouvindo ? 'Ouvindo… pode falar' : voz.dica ?? 'Fale com o Solis…'}
            aria-label="Fale com o Solis"
          />
          <input
            ref={seletor}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files) anexar(e.target.files);
              e.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => seletor.current?.click()}
            aria-label="Anexar arquivo"
            title="Anexar arquivo (ou arraste, ou cole uma imagem)"
            className="flex items-center justify-center text-text-secondary hover:text-text-primary shrink-0"
            style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', borderRadius: 'var(--mac-botao-raio)' }}
          >
            <Icone nome="adicionar" tamanho={22} />
          </button>
          <EscolhaClaude />
          <BotaoMicrofone estado={ouvindo ? 'ouvindo' : voz.estado} aoClicar={voz.alternar} tamanho={22} />
          {/* Respondendo, o enviar vira o parar (como no Claude): o mesmo
              círculo, o quadrado no lugar do avião. */}
          <button
            type={respondendo && aoParar ? 'button' : 'submit'}
            onClick={respondendo && aoParar ? aoParar : undefined}
            className="bg-accent text-canvas flex items-center justify-center shrink-0"
            style={{
              width: 52,
              height: 52,
              borderRadius: 999,
              marginLeft: 10,
              marginRight: 18,
              opacity: respondendo && !aoParar ? 0.4 : 1,
            }}
            aria-label={respondendo && aoParar ? 'Parar a resposta' : 'Enviar'}
            aria-disabled={respondendo && !aoParar}
          >
            <Icone nome={respondendo && aoParar ? 'parar' : 'enviar'} tamanho={22} />
          </button>
        </form>
      </div>
    </main>
  );
}
