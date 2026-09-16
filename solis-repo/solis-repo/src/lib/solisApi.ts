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
  /** Turnos anteriores. Sem "system" de propósito: o system prompt é montado no
   *  backend e não é coisa que o frontend informe. */
  history?: TurnoHistorico[];
}

export interface RespostaChat {
  response: string;
  model: string;
  eval_count: number;
  total_duration_ms: number;
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
  opcoes: { corpo?: unknown; timeout?: number } = {},
): Promise<T> {
  const controle = new AbortController();
  // AbortController e não AbortSignal.timeout: o webview do Tauri no Linux é
  // WebKitGTK, e a versão que acompanha distribuição LTS ainda não tem o
  // helper estático.
  const relogio = setTimeout(() => controle.abort(), opcoes.timeout ?? TIMEOUT_PADRAO);

  let resposta: Response;
  try {
    resposta = await fetch(`${BASE_URL}${rota}`, {
      method: opcoes.corpo === undefined ? 'GET' : 'POST',
      headers: opcoes.corpo === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: opcoes.corpo === undefined ? undefined : JSON.stringify(opcoes.corpo),
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
