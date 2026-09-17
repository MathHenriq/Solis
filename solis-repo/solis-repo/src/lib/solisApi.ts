/** Cliente do backend local do Solis (backend/app/main.py).
 *
 *  Só transporte: monta a chamada, valida o envelope, tipa o retorno. Nenhuma
 *  decisão de interface mora aqui — nem texto pra mostrar ao usuário, nem
 *  estado de tela. Quem traduz falha em frase é a camada de cima (useConversa),
 *  porque a mesma falha aparece diferente na Conversa, na tela de Modelos e num
 *  log de diagnóstico.
 */

/** O backend é um processo auxiliar na mesma máquina, não um serviço de rede.
 *  127.0.0.1 e não localhost: em máquina com IPv6 o `localhost` tenta ::1
 *  primeiro e a primeira chamada morre em timeout antes do fallback. */
export const BASE_URL = 'http://127.0.0.1:8000';

/** Conectar é rápido ou não vai acontecer. */
const TIMEOUT_PADRAO = 8_000;
/** Gerar não é: um modelo local de 8B leva dezenas de segundos numa resposta
 *  longa. O teto existe só pra que a tela nunca fique em `thinking` pra sempre
 *  (ERROR_STATES.md §2) — não pra cortar geração lenta como se fosse erro. */
const TIMEOUT_CHAT = 180_000;

export type PapelTurno = 'user' | 'assistant';

export interface TurnoHistorico {
  role: PapelTurno;
  content: string;
}

export interface Saude {
  status: string;
  ollama: 'online' | 'offline';
}

export interface ModeloInstalado {
  nome: string;
  /** bytes em disco */
  tamanho: number;
  familia: string;
  parametros: string;
  quantizacao: string;
  modificado: string;
}

export interface ListaModelos {
  models: ModeloInstalado[];
  /** Qual responde quando ninguém escolhe. Nulo = nenhum modelo instalado. */
  default: string | null;
}

export interface PedidoChat {
  message: string;
  model?: string;
  /** Deixar indefinido mantém o padrão do backend (ligado). */
  use_knowledge?: boolean;
  /** Turnos anteriores. Sem "system" de propósito: o system prompt é montado no
   *  backend e não é coisa que o frontend informe. */
  history?: TurnoHistorico[];
}

/** De onde saiu um pedaço da resposta, quando ela veio da base de conhecimento. */
export interface Fonte {
  document: string;
  chunk_idx: number;
  /** BM25 do SQLite: negativo, e quanto menor, melhor o casamento. */
  score: number;
  preview: string;
}

export interface RespostaChat {
  response: string;
  model: string;
  eval_count: number;
  total_duration_ms: number;
  /** Vazio quando a resposta não veio de documento nenhum. */
  sources: Fonte[];
  used_knowledge: boolean;
}

/** Um arquivo da base de conhecimento. `status` 'erro' vem com `error` preenchido. */
export interface Documento {
  id: number;
  name: string;
  chars: number;
  n_chunks: number;
  status: 'processado' | 'erro';
  error: string | null;
  created_at: string;
}

export interface ChunkEncontrado {
  chunk_id: number;
  document_id: number;
  idx: number;
  text: string;
  document: string;
  score: number;
}

export interface RespostaBusca {
  /** A expressão MATCH que a pergunta gerou. Vazia = não havia termo buscável. */
  fts_query: string;
  chunks: ChunkEncontrado[];
  passou_no_gate: boolean;
  motivo: string;
}

/** Por que a chamada falhou, no nível em que dá pra decidir o que dizer:
 *  - `rede`    → o backend não atendeu (processo parado, porta errada);
 *  - `timeout` → atendeu mas não respondeu a tempo;
 *  - `http`    → respondeu com erro, e `message` é o texto legível que ele mandou. */
export type TipoFalha = 'rede' | 'timeout' | 'http';

export class SolisApiError extends Error {
  readonly tipo: TipoFalha;
  readonly status: number;

  constructor(mensagem: string, tipo: TipoFalha, status = 0) {
    super(mensagem);
    this.name = 'SolisApiError';
    this.tipo = tipo;
    this.status = status;
  }
}

async function detalheDoErro(resposta: Response): Promise<string> {
  // O FastAPI devolve {"detail": "..."} — e o backend do Solis põe ali uma
  // frase já legível (gateway.OllamaError), não um stack trace.
  try {
    const corpo: unknown = await resposta.json();
    if (corpo && typeof corpo === 'object' && 'detail' in corpo) {
      const detalhe = (corpo as { detail: unknown }).detail;
      if (typeof detalhe === 'string' && detalhe.trim()) return detalhe;
    }
  } catch {
    /* corpo não era JSON — cai no genérico abaixo */
  }
  return `O backend do Solis respondeu ${resposta.status}.`;
}

async function pedir<T>(
  rota: string,
  opcoes: { metodo?: 'GET' | 'POST' | 'DELETE'; corpo?: unknown; timeout?: number } = {},
): Promise<T> {
  const controle = new AbortController();
  // AbortController e não AbortSignal.timeout: o webview do Tauri no Linux é
  // WebKitGTK, e a versão que acompanha distribuição LTS ainda não tem o
  // helper estático.
  const relogio = setTimeout(() => controle.abort(), opcoes.timeout ?? TIMEOUT_PADRAO);

  let resposta: Response;
  try {
    // FormData vai cru e SEM Content-Type: o navegador precisa escrever o
    // header ele mesmo pra incluir o `boundary` que separa as partes. Definir
    // 'multipart/form-data' na mão produz um header sem boundary e o servidor
    // não consegue ler o arquivo.
    const ehFormData = typeof FormData !== 'undefined' && opcoes.corpo instanceof FormData;
    resposta = await fetch(`${BASE_URL}${rota}`, {
      method: opcoes.metodo ?? (opcoes.corpo === undefined ? 'GET' : 'POST'),
      headers:
        opcoes.corpo === undefined || ehFormData ? undefined : { 'Content-Type': 'application/json' },
      body:
        opcoes.corpo === undefined
          ? undefined
          : ehFormData
            ? (opcoes.corpo as FormData)
            : JSON.stringify(opcoes.corpo),
      signal: controle.signal,
    });
  } catch (erro) {
    // O fetch só rejeita por falha de transporte — erro HTTP vem em `resposta`.
    // Distinguir abort de recusa importa: são duas frases diferentes na tela.
    throw controle.signal.aborted
      ? new SolisApiError(`Sem resposta de ${BASE_URL}${rota} no tempo limite.`, 'timeout')
      : new SolisApiError(`Sem conexão com ${BASE_URL}.`, 'rede');
  } finally {
    clearTimeout(relogio);
  }

  if (!resposta.ok) {
    throw new SolisApiError(await detalheDoErro(resposta), 'http', resposta.status);
  }
  return (await resposta.json()) as T;
}

/** Estado do backend e do motor. A rota responde 200 mesmo com o Ollama fora do
 *  ar — `ollama: 'offline'` é resposta, não erro. Isto aqui só rejeita se o
 *  próprio backend não estiver de pé. */
export function health(): Promise<Saude> {
  return pedir<Saude>('/health');
}

/** Modelos instalados no Ollama e qual é o default. */
export function listModels(): Promise<ListaModelos> {
  return pedir<ListaModelos>('/models');
}

/** Uma rodada de conversa. */
export function chat(pedido: PedidoChat): Promise<RespostaChat> {
  return pedir<RespostaChat>('/chat', { corpo: pedido, timeout: TIMEOUT_CHAT });
}

/** Sobe um arquivo para a base de conhecimento.
 *
 *  Resolve mesmo quando o arquivo não deu pra ler: aí o documento volta com
 *  `status: 'erro'` e a mensagem em `error`. Rejeitar seria perder o registro
 *  que a tela precisa mostrar na linha do arquivo. */
export function uploadDocumento(arquivo: File): Promise<Documento> {
  const forma = new FormData();
  forma.append('file', arquivo);
  // Mesmo teto do /chat: extrair texto de um PDF grande leva tempo, e o
  // backend faz isso numa thread — a espera é real, não travamento.
  return pedir<Documento>('/knowledge/documents', { corpo: forma, timeout: TIMEOUT_CHAT });
}

export function listarDocumentos(): Promise<Documento[]> {
  return pedir<Documento[]>('/knowledge/documents');
}

export function removerDocumento(id: number): Promise<{ removed: number }> {
  return pedir<{ removed: number }>(`/knowledge/documents/${id}`, { metodo: 'DELETE' });
}

/** Busca crua na base, sem modelo no meio. Mostra a consulta gerada e o gate. */
export function buscarConhecimento(query: string, k?: number): Promise<RespostaBusca> {
  return pedir<RespostaBusca>('/knowledge/search', { corpo: k === undefined ? { query } : { query, k } });
}
