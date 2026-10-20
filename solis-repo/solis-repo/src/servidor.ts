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

export type Mensagem = { papel: 'pessoa' | 'solis'; texto: string };
export type Falha = 'sem-servidor' | 'sem-ollama' | 'sem-modelo';

/** Manda a conversa e entrega a resposta pedaço a pedaço em `aoReceber`.
 *  Devolve null quando deu certo, ou QUEM falhou. Um corte no meio da resposta
 *  não é falha: o texto só termina onde parou. */
export async function conversar(
  mensagens: Mensagem[],
  aoReceber: (pedaco: string) => void,
): Promise<Falha | null> {
  const lista = await listarModelos();
  if (lista.estado !== 'ok') return lista.estado;
  const modelo = modeloEmUso(lista.dados);
  if (!modelo) return 'sem-modelo';

  let r: Response;
  try {
    r = await fetch(`${BASE}/conversa`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modelo, mensagens }),
    });
  } catch {
    return 'sem-servidor';
  }
  if (r.status === 503) return 'sem-ollama';
  if (r.status === 404) return 'sem-modelo';
  if (!r.ok || !r.body) return 'sem-servidor';

  const leitor = r.body.getReader();
  // `stream: true` porque um acento pode chegar partido entre dois pedaços.
  const texto = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      aoReceber(texto.decode(value, { stream: true }));
    }
  } catch {
    /* conexão caiu no meio: fica o que chegou */
  }
  return null;
}
