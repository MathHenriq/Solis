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

/** Uma etapa do que o servidor fez pra responder, com `t` em segundos desde o
 *  pedido (backend/solis/etapas.py). Nomes: memoria, cerebro, processo,
 *  primeira_linha, pensando, primeira_palavra, queda, fim, e depois da
 *  resposta titulo, aprendizado, indexacao, resumo. */
export type Etapa = {
  etapa: string;
  t: number;
  cerebro?: string;
  motivo?: string;
  memorias?: number;
  trechos?: number;
  novas?: number;
  /** As memórias guardadas depois da resposta. */
  textos?: string[];
  vetores?: number;
  resumiu?: boolean;
  /** O título que a conversa ganhou. */
  titulo?: string;
  cortada?: boolean;
};

/** `cerebro`: quem respondeu — 'local', 'claude' ou 'codex'. Nulo nas falas da
 *  pessoa e nas respostas antigas, de antes de existir mais de um. `etapas`:
 *  nulo nas falas da pessoa e nas respostas de antes das etapas existirem. */
export type Mensagem = {
  papel: 'pessoa' | 'solis';
  texto: string;
  criada: string;
  cerebro: string | null;
  etapas: Etapa[] | null;
};
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

/** Uma conversa na lista do painel. `atualizada`: a hora da última mensagem. */
export type ResumoConversa = { id: number; titulo: string; atualizada: string };

/** As conversas do painel, da mais recente pra mais antiga. `busca` procura no
 *  título e no texto. Servidor fora: lista vazia — o painel não tem o que
 *  mostrar, e o aviso de servidor desligado já aparece na própria conversa. */
export async function listarConversas(busca = ''): Promise<ResumoConversa[]> {
  try {
    const r = await fetch(`${BASE}/conversas?q=${encodeURIComponent(busca)}`);
    return r.ok ? ((await r.json()) as { conversas: ResumoConversa[] }).conversas : [];
  } catch {
    return [];
  }
}

export async function abrirConversa(id: number): Promise<{ id: number; mensagens: Mensagem[] } | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${id}`);
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export type Ouvintes = {
  aoReceber: (pedaco: string) => void;
  aoEtapa: (etapa: Etapa) => void;
  aoCriar: (id: number) => void;
};

/** O erro que o servidor manda dentro do stream, já aberto, no lugar da
 *  resposta. Mesmos nomes do JSON de erro das outras rotas. */
function falhaDoStream(e: { erro: string; cerebro?: string }): Falha {
  if (e.erro === 'cerebro_indisponivel') return { tipo: 'sem-cerebro', cerebro: e.cerebro ?? 'cérebro' };
  if (e.erro === 'modelo_inexistente') return { tipo: 'sem-modelo' };
  if (e.erro === 'ollama_indisponivel') return { tipo: 'sem-ollama' };
  return { tipo: 'sem-servidor' };
}

/** Manda uma mensagem e entrega a resposta pedaço a pedaço em `aoReceber`, e
 *  cada etapa do que o servidor está fazendo em `aoEtapa`.
 *
 *  Só a mensagem nova vai: o histórico mora no banco, do lado do servidor, e é
 *  ele que o monta — e é ele que decide quem responde (modelo local, Claude ou
 *  Codex); a etapa `primeira_palavra` diz qual foi. `conversa` null cria uma
 *  conversa nova antes, e o id dela volta por `aoCriar`. A resposta termina na
 *  etapa `fim`, mas a promessa só resolve quando o stream fecha, depois das
 *  etapas de fundo (aprendizado, resumo). Devolve null quando deu certo, ou
 *  QUEM falhou. Um corte no meio da resposta não é falha: o texto só termina
 *  onde parou. */
export async function conversar(conversa: number | null, texto: string, ouvintes: Ouvintes): Promise<Falha | null> {
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
      ouvintes.aoCriar(conversa);
    }
    r = await fetch(`${BASE}/conversas/${conversa}/mensagens`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modelo: modelo ?? '', texto }),
    });
  } catch {
    return { tipo: 'sem-servidor' };
  }
  // A conversa sumir do banco (o arquivo foi apagado com o app aberto) não é
  // culpa de ninguém: começa outra e manda de novo.
  if (r.status === 404) return conversar(null, texto, ouvintes);
  if (!r.ok || !r.body) return { tipo: 'sem-servidor' };

  // NDJSON: um evento por linha — {"texto"}, {"etapa"} ou {"erro"}. Uma linha
  // pode chegar partida entre dois pedaços da rede; o resto espera o próximo.
  const leitor = r.body.getReader();
  // `stream: true` porque um acento pode chegar partido entre dois pedaços.
  const decodificador = new TextDecoder();
  let resto = '';
  let falha: Falha | null = null;
  const tratar = (linha: string) => {
    if (!linha.trim()) return;
    const e = JSON.parse(linha) as { texto?: string; etapa?: string; erro?: string };
    if (e.texto !== undefined) ouvintes.aoReceber(e.texto);
    else if (e.erro !== undefined) falha = falhaDoStream(e as { erro: string });
    else if (e.etapa !== undefined) ouvintes.aoEtapa(e as Etapa);
  };
  try {
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      const linhas = (resto + decodificador.decode(value, { stream: true })).split('\n');
      resto = linhas.pop() ?? '';
      linhas.forEach(tratar);
    }
    tratar(resto);
  } catch {
    /* conexão caiu no meio: fica o que chegou */
  }
  return falha;
}
