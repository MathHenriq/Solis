/** Ponto único de conversa com o servidor local (backend/, FastAPI).
 *
 *  As telas não fazem `fetch` direto: recebem um resultado que já diz QUEM
 *  falhou, porque o texto do erro muda com isso (ERROR_STATES.md — "nunca é
 *  vago sobre o que aconteceu"). Servidor desligado e Ollama desligado são
 *  problemas diferentes, com consertos diferentes. */

const BASE = import.meta.env.VITE_SOLIS_SERVIDOR ?? 'http://127.0.0.1:8765';

export type Modelo = {
  nome: string;
  bytes: number;
  quantizacao: string | null;
  contexto: number | null;
  emUso: boolean;
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
