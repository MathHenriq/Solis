import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  aprovacoesPendentes,
  comandosRodando,
  conectorDe,
  depois,
  duracao,
  passos,
  segundos,
  type EtapaRecebida,
  type Passo,
} from '../etapas';
import { abrirArquivo, responderAprovacao, type Etapa } from '../servidor';
import { Botao } from './Controles';
import { Icone } from './icons';

/** O que o Solis está fazendo enquanto responde, e o que fez depois.
 *  Referência: referencias/telas/20-conversa-etapas.png; medidas em
 *  layout.thread.etapas (solis-tokens.json).
 *
 *  Três peças, cada uma num lugar da thread:
 *    - `ListaEtapas`: as etapas com check, a atual com ponto e as futuras com
 *      anel — embaixo do cabeçalho, enquanto ainda não há texto;
 *    - `DobraEtapas`: a linha recolhida "4 etapas · 3,1 s" ACIMA do cabeçalho,
 *      depois que o texto começou; abre a lista;
 *    - `AvisosDepois`: os chips de "Memória guardada" embaixo da resposta;
 *    - `CartoesAprovacao`: o que o Claude quer fazer e precisa do Matheus. */

/** O relógio da etapa atual anda de segundo em segundo enquanto há etapa viva.
 *  É estado, não animação: um re-render por segundo, nada em loop no CSS. */
function useAgora(ativo: boolean) {
  const [agora, definir] = useState(Date.now());
  useEffect(() => {
    if (!ativo) return;
    const id = setInterval(() => definir(Date.now()), 1000);
    return () => clearInterval(id);
  }, [ativo]);
  return agora;
}

function Marca({ estado }: { estado: Passo['estado'] }) {
  // Caixa de 16px a 3px da coluna: o check ocupa ela inteira, ponto e anel
  // ficam no centro dela (x 391,5 da referência, os três alinhados).
  return (
    <span className="shrink-0 flex items-center justify-center" style={{ width: 'var(--et-icone)', marginLeft: 3 }}>
      {estado === 'feita' && <Icone nome="feito" tamanho="var(--et-icone)" className="text-accent" />}
      {estado === 'atual' && (
        <span className="bg-accent" style={{ width: 'var(--et-ponto)', height: 'var(--et-ponto)', borderRadius: 999 }} />
      )}
      {(estado === 'futura' || estado === 'falhou') && (
        <span
          style={{
            width: 'var(--et-anel)',
            height: 'var(--et-anel)',
            borderRadius: 999,
            border: '1.5px solid var(--text-secondary)',
            opacity: 'var(--et-futura)',
          }}
        />
      )}
    </span>
  );
}

const COR: Record<Passo['estado'], string> = {
  feita: 'text-text-secondary',
  atual: 'text-text-primary',
  futura: 'text-text-secondary',
  // PROVISÓRIO: a referência não mostra cérebro que falhou. Anel de futura e
  // texto secundário: aconteceu, mas não com check — não deu certo.
  falhou: 'text-text-secondary',
};

/** A saída de um comando, como um terminal pequeno: o fim dela, rolado pro
 *  fim. Aprovado pelo Matheus em 13/11/2026 — desenho próprio (12/11/2026), base no Claude Code: a
 *  caixa do bloco de código (--cod-*) e do diff, com a letra mono dele. */
export function SaidaTerminal({ texto, rotulo, recuo = 0 }: { texto: string; rotulo: string; recuo?: number | string }) {
  const caixa = useRef<HTMLPreElement>(null);
  // O que chega por último é o que importa: a caixa fica no fim, como um terminal.
  useLayoutEffect(() => {
    if (caixa.current) caixa.current.scrollTop = caixa.current.scrollHeight;
  }, [texto]);
  return (
    <pre
      ref={caixa}
      aria-label={rotulo}
      className="font-mono text-text-primary overflow-y-auto"
      style={{
        fontSize: 'var(--cod-texto)',
        lineHeight: 1.55,
        maxHeight: 'var(--term-max)',
        marginLeft: recuo,
        padding: 'var(--term-py) var(--cod-px)',
        borderRadius: 'var(--cod-raio)',
        background: 'var(--mem-hover-forte)',
        whiteSpace: 'pre-wrap',
        overflowWrap: 'anywhere',
      }}
    >
      {texto.replace(/\n+$/, '')}
    </pre>
  );
}

/** Os comandos rodando agora, cada um com a saída chegando — embaixo do texto,
 *  como os cartões: a lista de etapas pode estar recolhida. */
export function TerminaisAoVivo({ etapas }: { etapas: EtapaRecebida[] }) {
  const rodando = comandosRodando(etapas);
  if (!rodando.length) return null;
  return (
    <div className="flex flex-col" style={{ marginTop: 'var(--et-chip-top)', gap: 8, maxWidth: 'var(--th-texto-max)' }}>
      {rodando.map((r) => (
        <div key={r.id}>
          <div
            title={r.comando}
            className="flex items-center text-text-secondary"
            style={{ fontSize: 'var(--et-dobra-texto)', gap: 8, marginBottom: 6 }}
          >
            <span className="bg-accent shrink-0" style={{ width: 'var(--et-ponto)', height: 'var(--et-ponto)', borderRadius: 999 }} />
            <span className="truncate min-w-0">
              Rodando no terminal: <span className="font-mono">{r.comando}</span>
            </span>
          </div>
          <SaidaTerminal texto={r.saida ?? ''} rotulo="Saída do comando, ao vivo" />
        </div>
      ))}
    </div>
  );
}

export function ListaEtapas({ etapas, vivo }: { etapas: EtapaRecebida[]; vivo: boolean }) {
  // O tique só provoca o re-render; a conta usa a hora de agora, porque uma
  // etapa que chegou entre dois tiques é mais nova que o último tique.
  useAgora(vivo);
  // As linhas de comando abertas (a saída dele embaixo), pelo índice.
  const [abertas, definirAbertas] = useState<Set<number>>(new Set());
  const alternar = (i: number) =>
    definirAbertas((a) => {
      const n = new Set(a);
      if (!n.delete(i)) n.add(i);
      return n;
    });
  return (
    <ol aria-label="Etapas da resposta" aria-live="polite">
      {passos(etapas, vivo, Date.now()).map((p, i) => {
        const texto = (
          // Uma linha só, com reticências: um caminho ou comando longo
          // quebrava a linha e passava por cima da etapa de baixo (a
          // altura do passo é fixa). O texto inteiro fica no title.
          <span
            title={p.titulo ?? p.texto}
            className="truncate min-w-0"
            style={{
              marginLeft: 'calc(var(--et-recuo) - var(--et-icone) - 3px)',
              opacity: p.estado === 'futura' ? 'var(--et-futura)' : undefined,
            }}
          >
            {p.texto}
          </span>
        );
        return (
          <Fragment key={i}>
            <li className={`flex items-center ${COR[p.estado]}`} style={{ height: 'var(--et-passo)', fontSize: 'var(--et-texto)' }}>
              <Marca estado={p.estado} />
              {p.saida ? (
                // Um comando: a linha abre a saída dele, como no Claude Code.
                <button
                  type="button"
                  onClick={() => alternar(i)}
                  aria-expanded={abertas.has(i)}
                  className="flex items-center min-w-0 hover:text-text-primary"
                >
                  {texto}
                  <Icone
                    nome="chevron"
                    tamanho={14}
                    className="shrink-0"
                    style={{ marginLeft: 6, transform: abertas.has(i) ? 'rotate(180deg)' : undefined }}
                  />
                </button>
              ) : (
                texto
              )}
            </li>
            {p.saida && abertas.has(i) && (
              <li style={{ marginBottom: 8 }}>
                <SaidaTerminal texto={p.saida} rotulo="Saída do comando" recuo="var(--et-recuo)" />
              </li>
            )}
          </Fragment>
        );
      })}
    </ol>
  );
}

export function DobraEtapas({
  etapas,
  vivo,
  aberta,
  aoAlternar,
}: {
  etapas: EtapaRecebida[];
  vivo: boolean;
  aberta: boolean;
  aoAlternar: () => void;
}) {
  const feitas = passos(etapas, false).length;
  return (
    <button
      type="button"
      onClick={aoAlternar}
      aria-expanded={aberta}
      // Alinhada pelo topo, numa caixa da altura do passo até o cabeçalho: o
      // topo dos números fica a 29px do topo da caixa alta da hora, como os
      // 40px da imagem. Centralizada, sobravam 24.
      className="relative flex items-start text-text-secondary"
      style={{ height: 'var(--et-dobra-gap)', fontSize: 'var(--et-dobra-texto)', paddingLeft: 'var(--et-dobra-recuo)' }}
    >
      {/* O chevron de 16px tem 3px de folga no grid; recuado 3px, a tinta
          encosta na coluna como na referência. O meio da tinta dele cai no
          meio dos números. Aberta, aponta pra cima. */}
      <Icone
        nome="chevron"
        tamanho={16}
        className="absolute"
        style={{ left: -3, top: 0, transform: aberta ? 'rotate(180deg)' : undefined }}
      />
      {feitas} {feitas === 1 ? 'etapa' : 'etapas'} · {segundos(duracao(etapas))}
      {vivo && '…'}
    </button>
  );
}

/** Os documentos que o Claude criou na resposta (Word, Excel, PDF...), com o
 *  Abrir (no programa do Windows) e o Mostrar na pasta — como o arquivo que o
 *  Claude Desktop entrega embaixo da resposta.
 *
 *  Aprovado pelo Matheus em 13/11/2026 — desenho próprio: a ficha do anexo (borda neutra,
 *  --et-chip-*) com as duas ações em texto à direita
 *  (layout.thread.etapas._files no solis-tokens.json). */
/** Um artefato (página ou imagem vetorial) abre no painel ao lado da conversa. */
export const ehArtefato = (caminho: string) => /\.(html?|svg)$/i.test(caminho);

export function ArquivosCriados({ etapas, aoVer }: { etapas: EtapaRecebida[]; aoVer?: (caminho: string) => void }) {
  const lista = etapas.find((e) => e.etapa === 'arquivos')?.lista ?? [];
  const [falhou, definirFalhou] = useState<string | null>(null);
  if (!lista.length) return null;
  const acao = async (caminho: string, pasta: boolean) => {
    definirFalhou((await abrirArquivo(caminho, pasta)) ? null : caminho);
  };
  return (
    <div className="flex flex-col items-start" style={{ marginTop: 'var(--et-chip-top)', gap: 8 }}>
      {lista.map((c) => (
        <div
          key={c}
          title={c}
          className="inline-flex items-center border border-divider text-text-primary"
          style={{
            maxWidth: 'var(--th-texto-max)',
            height: 'var(--et-chip-h)',
            padding: '0 var(--et-chip-px)',
            gap: 'var(--et-chip-icone-gap)',
            fontSize: 'var(--et-chip-texto)',
            borderRadius: 'var(--et-chip-raio)',
          }}
        >
          <Icone nome="documento" tamanho={14} className="text-text-secondary shrink-0" />
          <span className="truncate min-w-0">{c.split(/[\\/]/).pop()}</span>
          {aoVer && ehArtefato(c) && (
            <button type="button" onClick={() => aoVer(c)} className="text-accent hover:underline shrink-0" style={{ marginLeft: 8 }}>
              Ver aqui
            </button>
          )}
          <button
            type="button"
            onClick={() => acao(c, false)}
            className={`${aoVer && ehArtefato(c) ? 'text-text-secondary hover:text-text-primary' : 'text-accent'} hover:underline shrink-0`}
            style={{ marginLeft: aoVer && ehArtefato(c) ? 0 : 8 }}
          >
            Abrir
          </button>
          <button type="button" onClick={() => acao(c, true)} className="text-text-secondary hover:text-text-primary hover:underline shrink-0">
            Mostrar na pasta
          </button>
          {falhou === c && <span className="text-[var(--erro)] shrink-0">não abriu</span>}
        </div>
      ))}
    </div>
  );
}

export function AvisosDepois({ etapas }: { etapas: EtapaRecebida[] }) {
  const avisos = depois(etapas);
  if (!avisos.length) return null;
  return (
    <div className="flex flex-col items-start" style={{ marginTop: 'var(--et-chip-top)', gap: 8 }}>
      {avisos.map((a) => (
        <span
          key={a}
          title={a}
          className="inline-flex items-center text-text-primary"
          style={{
            // Uma memória longa (o pedido cru, quando o modelo não extraiu) não
            // passa da coluna de leitura: corta com reticências, e o texto
            // inteiro fica no title e na tela de Memória.
            maxWidth: 'var(--th-texto-max)',
            height: 'var(--et-chip-h)',
            padding: '0 var(--et-chip-px)',
            gap: 'var(--et-chip-icone-gap)',
            fontSize: 'var(--et-chip-texto)',
            borderRadius: 'var(--et-chip-raio)',
            border: '1px solid color-mix(in srgb, var(--accent) var(--et-chip-borda), transparent)',
            background: 'color-mix(in srgb, var(--accent) var(--et-chip-fundo), transparent)',
          }}
        >
          <Icone nome="feito" tamanho={14} className="text-accent shrink-0" />
          <span className="truncate">{a}</span>
        </span>
      ))}
    </div>
  );
}

/** O que o Claude quer fazer, dito pelo Matheus — o título do cartão. */
const QUER: Record<string, string> = {
  Write: 'O Claude quer criar ou reescrever um arquivo',
  Edit: 'O Claude quer editar um arquivo',
  MultiEdit: 'O Claude quer editar um arquivo',
  NotebookEdit: 'O Claude quer editar um notebook',
  Bash: 'O Claude quer rodar um comando no terminal',
  PowerShell: 'O Claude quer rodar um comando no terminal',
  Read: 'O Claude quer ler fora das pastas autorizadas',
  Glob: 'O Claude quer procurar fora das pastas autorizadas',
  Grep: 'O Claude quer procurar fora das pastas autorizadas',
  LS: 'O Claude quer olhar fora das pastas autorizadas',
  ExitPlanMode: 'O Claude quer seguir com este plano',
};

/** PROVISÓRIO — desenho próprio, sem referência (layout.thread.etapas._approval
 *  no solis-tokens.json): precisa do aval do Matheus nos 3 temas e 2 navs.
 *  Um cartão por pedido; some quando a resposta chega do servidor (a etapa
 *  `aprovacao_resposta`), e o que foi respondido vira um passo da lista. */
/** O que muda numa edição, antes de aprovar: as linhas que saem em vermelho,
 *  as que entram em verde (as cores do código e do erro de cada tema). */
export function Diff({ texto }: { texto: string }) {
  return (
    <pre
      aria-label="O que muda"
      className="font-mono overflow-auto"
      style={{
        fontSize: 'var(--cod-texto)',
        lineHeight: 1.55,
        marginTop: 10,
        maxHeight: 300,
        padding: '8px 0',
        borderRadius: 'var(--cod-raio)',
        background: 'var(--mem-hover-forte)',
      }}
    >
      {texto.split('\n').map((l, i) => {
        const tipo = l.startsWith('+') ? 'mais' : l.startsWith('-') ? 'menos' : l.startsWith('@@') || l.startsWith('…') ? 'meta' : 'igual';
        return (
          <div
            key={i}
            style={{
              padding: '0 var(--cod-px)',
              color: tipo === 'mais' ? 'var(--code-string)' : tipo === 'menos' ? 'var(--erro)' : tipo === 'meta' ? 'var(--text-secondary)' : 'var(--text-primary)',
              background:
                tipo === 'mais'
                  ? 'color-mix(in srgb, var(--code-string) 12%, transparent)'
                  : tipo === 'menos'
                    ? 'color-mix(in srgb, var(--erro) 10%, transparent)'
                    : undefined,
              whiteSpace: 'pre',
            }}
          >
            {l || ' '}
          </div>
        );
      })}
    </pre>
  );
}

/** O "sempre" de cada pedido: o comando exato, ou as edições da conversa
 *  (backend agente._regra). O plano não tem: cada plano é aprovado olhando. */
function rotuloSempre(ferramenta?: string): string | null {
  if (ferramenta === 'ExitPlanMode') return null;
  if (ferramenta === 'Bash' || ferramenta === 'PowerShell') return 'Sempre este comando';
  return 'Sempre nesta conversa';
}

/** PROVISÓRIO — desenho próprio, sem referência (layout.thread.etapas._approval
 *  no solis-tokens.json): precisa do aval do Matheus nos 3 temas e 2 navs.
 *  Um cartão por pedido; some quando a resposta chega do servidor (a etapa
 *  `aprovacao_resposta`), e o que foi respondido vira um passo da lista.
 *  Numa edição, o diff do que muda vem embaixo (12/11/2026). */
function CartaoAprovacao({ pedido }: { pedido: Etapa }) {
  const [enviando, definirEnviando] = useState(false);
  const [falhou, definirFalhou] = useState(false);
  const responder = async (aprovar: boolean, sempre = false) => {
    definirEnviando(true);
    definirFalhou(false);
    // Deu certo: o cartão some quando a etapa de resposta chegar pelo stream.
    if (!(await responderAprovacao(pedido.id ?? '', aprovar, sempre))) {
      definirFalhou(true);
      definirEnviando(false);
    }
  };
  const conector = conectorDe(pedido.ferramenta);
  const doClaude = conector
    ? `O Claude quer usar o ${conector.nome}`
    : (QUER[pedido.ferramenta ?? ''] ?? `O Claude quer usar ${pedido.ferramenta ?? 'uma ferramenta'}`);
  // Quem pede pode ser um ajudante (subagente): o cartão diz que é ele.
  const titulo = pedido.ajudante !== undefined ? doClaude.replace(/^O Claude quer/, 'O ajudante quer') : doClaude;
  const sempre = rotuloSempre(pedido.ferramenta);
  return (
    <div
      role="group"
      aria-label={titulo}
      style={{
        maxWidth: 'var(--th-texto-max)',
        padding: 'var(--et-apr-py) var(--et-apr-px)',
        borderRadius: 'var(--et-apr-raio)',
        border: '1px solid color-mix(in srgb, var(--accent) var(--et-chip-borda), transparent)',
        background: 'color-mix(in srgb, var(--accent) var(--et-chip-fundo), transparent)',
      }}
    >
      <div className={`flex ${pedido.ferramenta === 'ExitPlanMode' ? 'items-end' : 'items-center'}`} style={{ gap: 'var(--et-apr-gap)' }}>
        <div className="flex-1 min-w-0">
          <div className="text-text-primary" style={{ fontSize: 'var(--et-texto)' }}>
            {titulo}
          </div>
          {pedido.alvo && pedido.ferramenta === 'ExitPlanMode' ? (
            // O plano inteiro, legível: é ele que está sendo aprovado.
            <div
              className="text-text-primary whitespace-pre-wrap overflow-y-auto"
              style={{ fontSize: 'var(--et-texto)', lineHeight: 1.5, marginTop: 6, maxHeight: 320 }}
            >
              {pedido.alvo}
            </div>
          ) : (
            pedido.alvo && (
              <div
                title={pedido.alvo}
                className="text-text-secondary font-mono truncate"
                style={{ fontSize: 'var(--et-dobra-texto)', marginTop: 2 }}
              >
                {pedido.alvo}
              </div>
            )
          )}
          {falhou && (
            <div className="text-[var(--erro)]" style={{ fontSize: 'var(--et-dobra-texto)', marginTop: 2 }}>
              Não consegui responder: o pedido já acabou ou o servidor caiu.
            </div>
          )}
        </div>
        <div className="flex shrink-0" style={{ gap: 'var(--mac-botao-gap)' }}>
          <Botao onClick={() => responder(false)} disabled={enviando}>
            Recusar
          </Botao>
          {sempre && (
            <Botao onClick={() => responder(true, true)} disabled={enviando}>
              {sempre}
            </Botao>
          )}
          <Botao tipo="destaque" onClick={() => responder(true)} disabled={enviando}>
            Aprovar
          </Botao>
        </div>
      </div>
      {pedido.diff && <Diff texto={pedido.diff} />}
      {/* Num conector: o que vai ser mandado (o evento, o arquivo, a mensagem). */}
      {pedido.entrada && (
        <div style={{ marginTop: 10 }}>
          <SaidaTerminal texto={pedido.entrada} rotulo="O que vai ser mandado" />
        </div>
      )}
    </div>
  );
}

export function CartoesAprovacao({ etapas }: { etapas: EtapaRecebida[] }) {
  const pendentes = aprovacoesPendentes(etapas);
  if (!pendentes.length) return null;
  return (
    <div className="flex flex-col" style={{ marginTop: 'var(--et-chip-top)', gap: 8 }}>
      {pendentes.map((p) => (
        <CartaoAprovacao key={p.id} pedido={p} />
      ))}
    </div>
  );
}
