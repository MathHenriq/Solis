/** Ponto único de conversa com o servidor local (backend/, FastAPI).
 *
 *  As telas não fazem `fetch` direto: recebem um resultado que já diz QUEM
 *  falhou, porque o texto do erro muda com isso (ERROR_STATES.md — "nunca é
 *  vago sobre o que aconteceu"). Servidor desligado e Ollama desligado são
 *  problemas diferentes, com consertos diferentes. */

import { escrever, ler } from './theme/config';

const BASE = import.meta.env.VITE_SOLIS_SERVIDOR ?? 'http://127.0.0.1:8765';

export type Modelo = {
  nome: string;
  bytes: number;
  quantizacao: string | null;
  contexto: number | null;
  /** Na memória do Ollama agora. Não é o "Em uso" — ver `modeloEmUso`. */
  carregado: boolean;
  embeddings: boolean;
};

export type Resultado<T> =
  | { estado: 'ok'; dados: T }
  | { estado: 'sem-servidor' }
  | { estado: 'sem-ollama' };

export async function listarModelos(): Promise<Resultado<Modelo[]>> {
  let r: Response;
  try {
    r = await fetch(`${BASE}/modelos`);
  } catch {
    // fetch só rejeita quando não houve resposta nenhuma: ninguém na porta.
    return { estado: 'sem-servidor' };
  }
  if (r.status === 503) return { estado: 'sem-ollama' };
  if (!r.ok) return { estado: 'sem-servidor' };
  const corpo = (await r.json()) as { modelos: Modelo[] };
  return { estado: 'ok', dados: corpo.modelos };
}

/** `privada`: nunca sai da máquina — quando modelos de nuvem entrarem, ela fica
 *  de fora do que eles veem. */
export type Memoria = { id: number; texto: string; tema: string; pedido: boolean; privada: boolean; criada: string };

export async function listarMemorias(): Promise<Resultado<Memoria[]>> {
  try {
    const r = await fetch(`${BASE}/memorias`);
    if (!r.ok) return { estado: 'sem-servidor' };
    return { estado: 'ok', dados: ((await r.json()) as { memorias: Memoria[] }).memorias };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

const CHAVE_MODELO = 'solis.modelo';

export function escolherModelo(nome: string): void {
  escrever(CHAVE_MODELO, nome);
}

/** O modelo que a Conversa usa — é o "Em uso" da tela de Modelos.
 *
 *  O escolhido, se ainda estiver instalado; senão o primeiro que conversa. O
 *  padrão existe pra o Solis responder de primeira, sem exigir uma visita a
 *  Modelos antes; e o "Em uso" na tela mostra qual foi, então não é escondido.
 *  Modelo de embeddings não conversa e nunca entra. */
export function modeloEmUso(modelos: Modelo[]): string | null {
  const conversam = modelos.filter((m) => !m.embeddings);
  const escolhido = ler(CHAVE_MODELO);
  return conversam.find((m) => m.nome === escolhido)?.nome ?? conversam[0]?.nome ?? null;
}

/** `cerebro`: quem respondeu — 'local', 'claude' ou 'codex'. Nulo nas falas da
 *  pessoa e nas respostas antigas, de antes de existir mais de um. */
export type Mensagem = { papel: 'pessoa' | 'solis'; texto: string; criada: string; cerebro: string | null };
export type Falha =
  | { tipo: 'sem-servidor' | 'sem-ollama' | 'sem-modelo' }
  /** Um cérebro escolhido com /claude ou /codex não respondeu. */
  | { tipo: 'sem-cerebro'; cerebro: string };

/** A conversa mais recente guardada — o app reabre nela. null quando o servidor
 *  não responde: aí a tela começa vazia, que é o que dá pra mostrar. */
export async function carregarConversa(): Promise<{ id: number | null; mensagens: Mensagem[] } | null> {
  try {
    const r = await fetch(`${BASE}/conversas/atual`);
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

/** Manda uma mensagem e entrega a resposta pedaço a pedaço em `aoReceber`.
 *
 *  Só a mensagem nova vai: o histórico mora no banco, do lado do servidor, e é
 *  ele que o monta — e é ele que decide quem responde (modelo local, Claude ou
 *  Codex); `aoCerebro` diz qual foi. `conversa` null cria uma conversa nova
 *  antes, e o id dela volta por `aoCriar`. Devolve null quando deu certo, ou
 *  QUEM falhou. Um corte no meio da resposta não é falha: o texto só termina
 *  onde parou. */
export async function conversar(
  conversa: number | null,
  texto: string,
  aoReceber: (pedaco: string) => void,
  aoCriar: (id: number) => void,
  aoCerebro: (cerebro: string) => void = () => {},
): Promise<Falha | null> {
  const lista = await listarModelos();
  if (lista.estado === 'sem-servidor') return { tipo: 'sem-servidor' };
  // Ollama fora não é mais fim de conversa: o Claude ou o Codex ainda podem
  // responder. Sem modelo local, o servidor simplesmente não tenta o local.
  const modelo = lista.estado === 'ok' ? modeloEmUso(lista.dados) : null;
  if (lista.estado === 'ok' && !modelo) return { tipo: 'sem-modelo' };

  let r: Response;
  try {
    if (conversa === null) {
      const criada = await fetch(`${BASE}/conversas`, { method: 'POST' });
      if (!criada.ok) return { tipo: 'sem-servidor' };
      conversa = ((await criada.json()) as { id: number }).id;
      aoCriar(conversa);
    }
    r = await fetch(`${BASE}/conversas/${conversa}/mensagens`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modelo: modelo ?? '', texto }),
    });
  } catch {
    return { tipo: 'sem-servidor' };
  }
  if (r.status === 503) return { tipo: 'sem-ollama' };
  if (r.status === 502) {
    const { cerebro } = (await r.json()) as { cerebro: string };
    return { tipo: 'sem-cerebro', cerebro };
  }
  if (r.status === 404) {
    // Dois 404 diferentes. A conversa sumir do banco (o arquivo foi apagado com
    // o app aberto) não é culpa de ninguém: começa outra e manda de novo.
    const { erro } = (await r.json()) as { erro: string };
    if (erro === 'conversa_inexistente') return conversar(null, texto, aoReceber, aoCriar, aoCerebro);
    return { tipo: 'sem-modelo' };
  }
  if (!r.ok || !r.body) return { tipo: 'sem-servidor' };
  aoCerebro(r.headers.get('X-Solis-Cerebro') ?? 'local');

  const leitor = r.body.getReader();
  // `stream: true` porque um acento pode chegar partido entre dois pedaços.
  const decodificador = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      aoReceber(decodificador.decode(value, { stream: true }));
    }
  } catch {
    /* conexão caiu no meio: fica o que chegou */
  }
  return null;
}
