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

/** `busca`: só as que batem — por palavra, por prefixo e sem diferença de
 *  acento (o índice FTS5 do servidor). */
export async function listarMemorias(busca = ''): Promise<Resultado<Memoria[]>> {
  try {
    const r = await fetch(`${BASE}/memorias${busca.trim() ? `?q=${encodeURIComponent(busca)}` : ''}`);
    if (!r.ok) return { estado: 'sem-servidor' };
    return { estado: 'ok', dados: ((await r.json()) as { memorias: Memoria[] }).memorias };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

/** Troca o texto de uma memória. A memória como ficou, ou null se não deu. */
export async function corrigirMemoria(id: number, texto: string): Promise<Memoria | null> {
  try {
    const r = await fetch(`${BASE}/memorias/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto }),
    });
    return r.ok ? ((await r.json()) as { memoria: Memoria }).memoria : null;
  } catch {
    return null;
  }
}

/** Esquece uma memória (a que ela substituiu, se houver, volta a valer). */
export async function esquecerMemoria(id: number): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/memorias/${id}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

/** Os nomes dos cérebros, num lugar só (o servidor tem o mesmo em
 *  cerebros.NOMES). Daqui saem o "· Groq" embaixo da resposta, o "o Gemini" das
 *  etapas e os comandos /groq, /gemini... que o campo de digitar reconhece. */
export const NOMES_CEREBRO: Record<string, string> = {
  local: 'Modelo local',
  claude: 'Claude',
  codex: 'Codex',
  groq: 'Groq',
  gemini: 'Gemini',
  mistral: 'Mistral',
  openrouter: 'OpenRouter',
};

/** Um cérebro em Configurações → Cérebros, na ordem em que é tentado.
 *  `pausa.ate` é epoch em segundos: depois de falhar (cota, login, limite
 *  grátis), o cérebro fica de lado até lá. O local nunca desliga nem pausa.
 *  `tipo` api: `instalado` quer dizer que há uma chave guardada (ela mesma
 *  nunca vem pra cá); `modelo` é o que o Solis escolheu entre os do serviço,
 *  `nota` o preço do grátis, `site` onde criar a chave. */
export type Cerebro = {
  nome: string;
  rotulo: string;
  tipo: 'local' | 'cli' | 'api';
  ligado: boolean;
  instalado: boolean;
  pausa: { ate: number; motivo: string } | null;
  modelo?: string | null;
  nota?: string;
  site?: string;
};

async function cerebros(caminho: string, init?: RequestInit): Promise<Cerebro[] | null> {
  try {
    const r = await fetch(`${BASE}${caminho}`, init);
    return r.ok ? ((await r.json()) as { cerebros: Cerebro[] }).cerebros : null;
  } catch {
    return null;
  }
}

/** null: servidor desligado. */
export const listarCerebros = () => cerebros('/cerebros');

/** Guarda a ordem e o liga/desliga; devolve a lista como o servidor ficou. */
export const ordenarCerebros = (ordem: Pick<Cerebro, 'nome' | 'ligado'>[]) =>
  cerebros('/cerebros', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ordem: ordem.map(({ nome, ligado }) => ({ nome, ligado })) }),
  });

export const retomarCerebro = (nome: string) => cerebros(`/cerebros/${nome}/retomar`, { method: 'POST' });

/** O servidor confere a chave no próprio serviço antes de guardar. */
export type ResultadoChave =
  | { estado: 'ok'; cerebros: Cerebro[] }
  | { estado: 'recusada' | 'vazia' | 'servico-fora' | 'sem-servidor' };

export async function guardarChave(nome: string, chave: string): Promise<ResultadoChave> {
  try {
    const r = await fetch(`${BASE}/cerebros/${nome}/chave`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chave }),
    });
    if (r.ok) return { estado: 'ok', cerebros: ((await r.json()) as { cerebros: Cerebro[] }).cerebros };
    const erro = ((await r.json().catch(() => ({}))) as { erro?: string }).erro;
    if (erro === 'chave_recusada') return { estado: 'recusada' };
    if (erro === 'chave_vazia') return { estado: 'vazia' };
    if (erro === 'provedor_fora') return { estado: 'servico-fora' };
    return { estado: 'sem-servidor' };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

export const apagarChave = (nome: string) => cerebros(`/cerebros/${nome}/chave`, { method: 'DELETE' });

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
  /** Trechos dos arquivos do Conhecimento que entraram no pedido. */
  arquivos?: number;
  novas?: number;
  /** As memórias guardadas depois da resposta. */
  textos?: string[];
  /** As tarefas tiradas da mensagem depois da resposta. */
  tarefas?: { texto: string; prazo: string | null; hora: string | null }[];
  /** Os compromissos tirados da mensagem depois da resposta. */
  compromissos?: { titulo: string; dia: string; hora: string | null }[];
  vetores?: number;
  resumiu?: boolean;
  /** O título que a conversa ganhou. */
  titulo?: string;
  cortada?: boolean;
  /** Etapa `ferramenta`: qual (listar_pasta, buscar_arquivos, ler_arquivo), em
   *  quê (o caminho ou a busca) e se deu certo. */
  ferramenta?: string;
  alvo?: string;
  ok?: boolean;
  /** Etapa `rapida`: o que foi respondido em código (hora, data, agenda...). */
  tipo?: string;
  /** Etapas `aprovacao` e `aprovacao_resposta` (backend/solis/agente.py): o
   *  pedido do Claude pra escrever, editar, rodar ou ler fora das pastas, o
   *  resumo dele em português, e o que o Matheus respondeu. */
  id?: string;
  resumo?: string;
  aprovado?: boolean;
  /** Etapa `guardada`: o id da mensagem da pessoa no banco — é por ele que a
   *  tela edita a mensagem ou refaz a resposta. */
  pessoa?: number;
  /** Etapa `fim`: o Matheus parou a resposta no meio. */
  parada?: boolean;
  /** Etapa `aprovacao` de uma edição: o que muda, em diff unificado. */
  diff?: string;
  /** Etapa `modo`: o modo da conversa mudou (o plano aprovado volta pra "pedir"). */
  modo?: string;
  /** Etapa `ferramenta` de um comando: o fim da saída dele. Etapa `saida`
   *  (só ao vivo, não fica no banco): o fim da saída até agora, do comando
   *  `comando`, com o `id` do uso da ferramenta. */
  saida?: string;
  comando?: string;
  /** Etapa `ferramenta` de um comando deixado rodando em segundo plano. */
  fundo?: boolean;
  /** Etapa `aprovacao` pedida por um ajudante (subagente): a tarefa dele. */
  ajudante?: string;
  /** Etapa `aprovacao` de um conector: o que vai ser mandado (JSON). */
  entrada?: string;
  /** Etapa `aprovacao` do navegador: o site da página aberta ("loja.com.br");
   *  na tela, o programa onde a ação cai ("Bloco de Notas"). */
  site?: string;
  /** Etapa `aprovacao` na tela: o print marcado (data URL). */
  imagem?: string;
  /** Etapa `arquivos`: os documentos que o Claude criou nesta resposta (caminhos). */
  lista?: string[];
  /** Etapa `ferramenta` de uma busca na web: os resultados (as fontes encontradas). */
  links?: { titulo: string; url: string }[];
  /** Etapa `fonte`: uma página que um ajudante leu. */
  url?: string;
  /** Etapa `plano`: a lista de tarefas do Claude como está agora. */
  itens?: { id: string; texto: string; estado: 'pendente' | 'fazendo' | 'feita' }[];
  /** Etapa `fontes`: as fontes da rodada, numa resposta que veio sozinha (o relatório). */
  fontes?: { url: string; titulo: string; lida: boolean }[];
};

/** `cerebro`: quem respondeu — uma chave de NOMES_CEREBRO. Nulo nas falas da
 *  pessoa e nas respostas antigas, de antes de existir mais de um. `etapas`:
 *  nulo nas falas da pessoa e nas respostas de antes das etapas existirem. */
/** Um arquivo anexado a uma mensagem: mora na pasta de trabalho do Solis. */
export type Anexo = { nome: string; caminho: string; tipo: string; tamanho: number };

export type Mensagem = {
  id: number;
  anexos?: Anexo[];
  papel: 'pessoa' | 'solis';
  texto: string;
  criada: string;
  cerebro: string | null;
  etapas: Etapa[] | null;
};
export type Falha =
  | { tipo: 'sem-servidor' | 'sem-ollama' | 'sem-modelo' }
  /** Um cérebro escolhido com /claude, /groq... não respondeu. */
  | { tipo: 'sem-cerebro'; cerebro: string };

/** A conversa mais recente guardada — o app reabre nela. null quando o servidor
 *  não responde: aí a tela começa vazia, que é o que dá pra mostrar. */
/** O modelo do Claude e o quanto ele pensa. null = o padrão da conta. */
export type AjustesClaude = { modelo: string | null; esforco: string | null; modelos: string[]; esforcos: string[] };

export async function lerAjustesClaude(): Promise<AjustesClaude | null> {
  try {
    const r = await fetch(`${BASE}/cerebros/claude/ajustes`);
    return r.ok ? ((await r.json()) as AjustesClaude) : null;
  } catch {
    return null;
  }
}

export async function guardarAjustesClaude(modelo: string | null, esforco: string | null): Promise<AjustesClaude | null> {
  try {
    const r = await fetch(`${BASE}/cerebros/claude/ajustes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modelo, esforco }),
    });
    return r.ok ? ((await r.json()) as AjustesClaude) : null;
  } catch {
    return null;
  }
}

/** Manda um arquivo pro servidor antes da mensagem; o caminho volta e vai
 *  junto com ela. null se não deu (servidor fora, grande demais). */
export async function enviarAnexo(arquivo: File): Promise<Anexo | null> {
  try {
    const r = await fetch(`${BASE}/anexos?nome=${encodeURIComponent(arquivo.name || 'colado.png')}`, {
      method: 'POST',
      body: arquivo,
    });
    return r.ok ? ((await r.json()) as Anexo) : null;
  } catch {
    return null;
  }
}

/** A pasta de projeto da conversa e o modo do Claude nela. */
export type Projeto = {
  pasta: string | null;
  modo: 'pedir' | 'aceitar' | 'planejar';
  recentes: string[];
  /** O projeto da conversa (instruções, arquivos fixos, pasta), ou null. */
  projeto: { id: number; nome: string } | null;
};

/** Um projeto: nome, instruções, arquivos fixos e, se quiser, a pasta de código. */
export type ArquivoProjeto = { id: number; nome: string; caminho: string; tipo: string; tamanho: number };
export type ProjetoSolis = {
  id: number;
  nome: string;
  instrucoes: string;
  pasta: string | null;
  /** Na lista: quantos; num projeto aberto: os arquivos. */
  arquivos: number | ArquivoProjeto[];
  conversas?: number;
};

export async function listarProjetos(): Promise<ProjetoSolis[] | null> {
  try {
    const r = await fetch(`${BASE}/projetos`);
    return r.ok ? ((await r.json()) as { projetos: ProjetoSolis[] }).projetos : null;
  } catch {
    return null;
  }
}

export async function lerProjetoSolis(id: number): Promise<ProjetoSolis | null> {
  try {
    const r = await fetch(`${BASE}/projetos/${id}`);
    return r.ok ? ((await r.json()) as ProjetoSolis) : null;
  } catch {
    return null;
  }
}

/** Cria (sem id) ou edita. Erro: 'pasta-inexistente', 'sem-nome' ou null (servidor fora). */
export async function salvarProjetoSolis(
  dados: { id?: number; nome: string; instrucoes: string; pasta: string | null },
): Promise<ProjetoSolis | 'pasta-inexistente' | 'sem-nome' | null> {
  try {
    const r = await fetch(`${BASE}/projetos${dados.id ? `/${dados.id}` : ''}`, {
      method: dados.id ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome: dados.nome, instrucoes: dados.instrucoes, pasta: dados.pasta }),
    });
    if (r.status === 400) return (await r.json()).erro === 'sem_nome' ? 'sem-nome' : 'pasta-inexistente';
    return r.ok ? ((await r.json()) as ProjetoSolis) : null;
  } catch {
    return null;
  }
}

export async function apagarProjetoSolis(id: number): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/projetos/${id}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

export async function enviarArquivoProjeto(id: number, arquivo: File): Promise<ArquivoProjeto | null> {
  try {
    const r = await fetch(`${BASE}/projetos/${id}/arquivos?nome=${encodeURIComponent(arquivo.name)}`, {
      method: 'POST',
      body: arquivo,
    });
    return r.ok ? ((await r.json()) as ArquivoProjeto) : null;
  } catch {
    return null;
  }
}

export async function removerArquivoProjeto(id: number, arquivo: number): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/projetos/${id}/arquivos/${arquivo}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

export async function lerProjeto(conversa: number): Promise<Projeto | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/projeto`);
    return r.ok ? ((await r.json()) as Projeto) : null;
  } catch {
    return null;
  }
}

export async function guardarProjeto(
  conversa: number,
  pasta: string | null,
  modo: Projeto['modo'],
  /** O projeto (id), ou null pra tirar; sem ele, fica o que era. */
  projeto?: number | null,
): Promise<Projeto | 'pasta-inexistente' | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/projeto`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(projeto === undefined ? { pasta, modo } : { pasta, modo, projeto }),
    });
    if (r.status === 400) return 'pasta-inexistente';
    return r.ok ? ((await r.json()) as Projeto) : null;
  } catch {
    return null;
  }
}

/** A última fala depois da qual o Claude mudou arquivo nesta conversa: dela
 *  pra trás, toda fala da pessoa pode voltar atrás. null: nada pra voltar. */
export async function lerVolta(conversa: number): Promise<number | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/voltar`);
    return r.ok ? ((await r.json()) as { ultima: number | null }).ultima : null;
  } catch {
    return null;
  }
}

/** O que voltou (ou voltaria, simulando): os arquivos e as linhas. */
export type Volta = { arquivos: string[]; mais: number; menos: number; erros: string[] };

/** Voltar atrás: os arquivos que o Claude mudou da fala `desde` em diante
 *  voltam a como estavam antes dela; com `conversa`, a conversa volta junto. */
export async function voltarAtras(
  conversa: number,
  desde: number,
  opcoes: { simular?: boolean; conversa?: boolean } = {},
): Promise<Volta | 'respondendo' | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/voltar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ desde, simular: !!opcoes.simular, conversa: !!opcoes.conversa }),
    });
    if (r.status === 409) return 'respondendo';
    return r.ok ? ((await r.json()) as Volta) : null;
  } catch {
    return null;
  }
}

/** Um arquivo mudado no repositório: M mudou, A novo, D apagado, R
 *  renomeado, U em conflito, ? fora do git. */
export type ArquivoGit = { caminho: string; status: string; mais: number; menos: number };

/** O git da pasta de projeto da conversa. */
export type Git =
  | { repo: false }
  | {
      repo: true;
      raiz: string;
      ramo: string;
      upstream: string | null;
      frente: number;
      atras: number;
      arquivos: ArquivoGit[];
      gh: boolean;
    };

export async function lerGit(conversa: number): Promise<Git | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/git`);
    return r.ok ? ((await r.json()) as Git) : null;
  } catch {
    return null;
  }
}

export async function lerDiffGit(conversa: number, arquivo: string): Promise<string | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/git/diff?arquivo=${encodeURIComponent(arquivo)}`);
    return r.ok ? ((await r.json()) as { diff: string }).diff : null;
  } catch {
    return null;
  }
}

/** Commit, push ou PR. Erro do git: `{ erro }` com o que ele disse. */
export async function acaoGit(
  conversa: number,
  acao: 'commit' | 'push' | 'pr',
  mensagem?: string,
): Promise<{ ok: true; dados: { hash?: string; mensagem?: string; url?: string } } | { ok: false; erro: string }> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/git/${acao}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: acao === 'commit' ? JSON.stringify({ mensagem }) : undefined,
    });
    const corpo = await r.json();
    return r.ok ? { ok: true, dados: corpo } : { ok: false, erro: corpo.motivo ?? 'não deu' };
  } catch {
    return { ok: false, erro: 'Não consegui falar com o servidor do Solis.' };
  }
}

/** As bibliotecas que as skills de documento usam (docx, xlsx, pptx, pdf). */
export type EstadoDocumentos = { pronto: boolean; falta: string[]; pasta: string; node: boolean; python: boolean };

export async function lerDocumentos(): Promise<EstadoDocumentos | null> {
  try {
    const r = await fetch(`${BASE}/documentos`);
    return r.ok ? ((await r.json()) as EstadoDocumentos) : null;
  } catch {
    return null;
  }
}

/** Baixa e instala as bibliotecas (um ou dois minutos). Erro: o motivo. */
export async function prepararDocumentos(): Promise<EstadoDocumentos | { erro: string }> {
  try {
    const r = await fetch(`${BASE}/documentos/preparar`, { method: 'POST' });
    const corpo = await r.json();
    return r.ok ? (corpo as EstadoDocumentos) : { erro: corpo.motivo ?? 'não deu' };
  } catch {
    return { erro: 'Não consegui falar com o servidor do Solis.' };
  }
}

/** O conteúdo de um artefato (.html ou .svg) pro painel ao lado da conversa. */
export async function lerArtefato(caminho: string): Promise<{ tipo: 'html' | 'svg'; texto: string } | null> {
  try {
    const r = await fetch(`${BASE}/arquivos/conteudo?caminho=${encodeURIComponent(caminho)}`);
    return r.ok ? ((await r.json()) as { tipo: 'html' | 'svg'; texto: string }) : null;
  } catch {
    return null;
  }
}

/** Abre o documento no programa do Windows, ou mostra na pasta. */
export async function abrirArquivo(caminho: string, pasta = false): Promise<boolean> {
  try {
    const r = await fetch(`${BASE}/arquivos/abrir`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caminho, pasta }),
    });
    return r.ok;
  } catch {
    return false;
  }
}

/** Um conector da conta do claude.ai que o Claude do Solis usa. */
export type Conector = {
  nome: string;
  estado: 'conectado' | 'precisa_entrar' | 'conectando' | 'falhou';
  ferramentas: number;
  so_leem: number;
};

/** null: o servidor não respondeu (ou não conseguiu ler). */
export async function listarConectores(atualizar = false): Promise<Conector[] | null> {
  try {
    const r = await fetch(`${BASE}/conectores${atualizar ? '?atualizar=true' : ''}`);
    return r.ok ? ((await r.json()) as { conectores: Conector[] }).conectores : null;
  } catch {
    return null;
  }
}

/** Um comando que o Claude deixou rodando em segundo plano, ou um ajudante
 *  (subagente) trabalhando: o que ele faz `agora` e as últimas ações. */
export type ComandoFundo = {
  id: string;
  tipo?: 'comando' | 'ajudante';
  comando: string;
  descricao: string;
  segundos: number;
  saida: string;
  agora?: { ferramenta: string; alvo: string } | null;
  passos?: { ferramenta: string; alvo: string; ok: boolean }[];
};

/** O que roda em segundo plano na conversa, e a resposta que o Claude começou
 *  sozinho quando um comando acabou (texto e etapas até agora). */
export type Fundo = {
  comandos: ComandoFundo[];
  resposta: { texto: string; etapas: Etapa[] } | null;
  /** Cartões de um ajudante que pediu aprovação sem resposta em andamento. */
  aprovacoes?: Etapa[];
};

export async function lerFundo(conversa: number): Promise<Fundo | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/fundo`);
    return r.ok ? ((await r.json()) as Fundo) : null;
  } catch {
    return null;
  }
}

export async function pararFundo(conversa: number, tarefa: string): Promise<boolean> {
  try {
    const r = await fetch(`${BASE}/conversas/${conversa}/fundo/${encodeURIComponent(tarefa)}/parar`, { method: 'POST' });
    return r.ok;
  } catch {
    return false;
  }
}

/** Para a resposta em andamento. O que já chegou fica guardado. */
export async function pararResposta(conversa: number): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/conversas/${conversa}/parar`, { method: 'POST' })).ok;
  } catch {
    return false;
  }
}

/** O Matheus respondeu o cartão de aprovação. False se o pedido já tinha
 *  acabado (respondido, ou passou o tempo) ou o servidor não respondeu. */
export async function responderAprovacao(id: string, aprovar: boolean, sempre = false): Promise<boolean> {
  try {
    const r = await fetch(`${BASE}/aprovacoes/${encodeURIComponent(id)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ aprovar, sempre }),
    });
    return r.ok;
  } catch {
    return false;
  }
}

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

/** Outro nome pra conversa. null: não deu. */
export async function renomearConversa(id: number, titulo: string): Promise<string | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ titulo }),
    });
    return r.ok ? ((await r.json()) as { titulo: string }).titulo : null;
  } catch {
    return null;
  }
}

/** Apaga a conversa (e os anexos; as memórias ficam). 'respondendo': espere acabar. */
export async function apagarConversa(id: number): Promise<true | 'respondendo' | null> {
  try {
    const r = await fetch(`${BASE}/conversas/${id}`, { method: 'DELETE' });
    if (r.status === 409) return 'respondendo';
    return r.ok ? true : null;
  } catch {
    return null;
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
/** `voz`: a mensagem veio pela voz e a resposta vai ser falada — o servidor
 *  pede uma resposta curta e direta (ollama.VOZ). */
/** `desde`: editar uma mensagem ou refazer a resposta — a conversa volta a
 *  antes da mensagem `desde` (da pessoa) e `texto` vai no lugar dela. */
export async function conversar(
  conversa: number | null,
  texto: string,
  ouvintes: Ouvintes,
  voz = false,
  desde?: number,
  anexos: string[] = [],
  /** O botão Pesquisa: pesquisa longa, pelo Claude, com as fontes. */
  pesquisa = false,
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
      ouvintes.aoCriar(conversa);
    }
    r = await fetch(`${BASE}/conversas/${conversa}/mensagens`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        modelo: modelo ?? '',
        texto,
        voz,
        anexos,
        ...(desde !== undefined ? { desde } : {}),
        ...(pesquisa ? { pesquisa } : {}),
      }),
    });
  } catch {
    return { tipo: 'sem-servidor' };
  }
  // A conversa sumir do banco (o arquivo foi apagado com o app aberto) não é
  // culpa de ninguém: começa outra e manda de novo.
  // Na edição, 404 é a mensagem que não existe mais: começar outra conversa
  // jogaria fora o resto.
  if (r.status === 404 && desde === undefined) return conversar(null, texto, ouvintes, voz);
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

/** Um arquivo do Conhecimento. `indexados < trechos` = ainda virando vetor
 *  (o "Indexando… 64%" da tela). `paginas` só no PDF; `url` só na página web. */
export type Documento = {
  id: number;
  nome: string;
  tipo: 'pdf' | 'nota' | 'web';
  url: string | null;
  paginas: number | null;
  bytes: number;
  privado: boolean;
  criado: string;
  trechos: number;
  indexados: number;
  /** Páginas escaneadas (imagem) do PDF, e quantas o OCR já leu. */
  escaneadas: number;
  lidas: number;
  /** Por que a leitura das escaneadas não anda: o Ollama fora, ou nada neste
   *  computador lê imagem. Só vem na lista (GET), e só enquanto falta página. */
  leitura_parada?: 'ollama' | 'ocr' | null;
};

export async function listarDocumentos(busca = ''): Promise<Resultado<Documento[]>> {
  try {
    const r = await fetch(`${BASE}/conhecimento${busca.trim() ? `?q=${encodeURIComponent(busca)}` : ''}`);
    if (!r.ok) return { estado: 'sem-servidor' };
    return { estado: 'ok', dados: ((await r.json()) as { documentos: Documento[] }).documentos };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

export type ResultadoArquivo =
  | { estado: 'ok'; documento: Documento }
  | { estado: 'nao-leu'; motivo: string }
  | { estado: 'ja-existe' }
  | { estado: 'sem-servidor' };

/** O arquivo vai cru no corpo, como está no disco; o servidor lê e corta. */
export async function adicionarDocumento(arquivo: File, privado = false): Promise<ResultadoArquivo> {
  try {
    const r = await fetch(
      `${BASE}/conhecimento?nome=${encodeURIComponent(arquivo.name)}&privado=${privado}`,
      { method: 'POST', body: arquivo },
    );
    if (r.ok) return { estado: 'ok', documento: ((await r.json()) as { documento: Documento }).documento };
    const corpo = (await r.json().catch(() => ({}))) as { erro?: string; motivo?: string };
    if (corpo.erro === 'nao_leu') return { estado: 'nao-leu', motivo: corpo.motivo ?? '' };
    if (corpo.erro === 'ja_existe') return { estado: 'ja-existe' };
    return { estado: 'sem-servidor' };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

/** O servidor baixa o endereço e tira o conteúdo principal da página. */
export async function adicionarPagina(url: string, privado = false): Promise<ResultadoArquivo> {
  try {
    const r = await fetch(`${BASE}/conhecimento/pagina`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, privado }),
    });
    if (r.ok) return { estado: 'ok', documento: ((await r.json()) as { documento: Documento }).documento };
    const corpo = (await r.json().catch(() => ({}))) as { erro?: string; motivo?: string };
    if (corpo.erro === 'nao_leu') return { estado: 'nao-leu', motivo: corpo.motivo ?? '' };
    if (corpo.erro === 'ja_existe') return { estado: 'ja-existe' };
    return { estado: 'sem-servidor' };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

export async function marcarDocumentoPrivado(id: number, privado: boolean): Promise<Documento | null> {
  try {
    const r = await fetch(`${BASE}/conhecimento/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ privado }),
    });
    return r.ok ? ((await r.json()) as { documento: Documento }).documento : null;
  } catch {
    return null;
  }
}

export async function apagarDocumento(id: number): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/conhecimento/${id}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

// — Tarefas ———————————————————————————————————————————————————————————————————————

export type Tarefa = {
  id: number;
  texto: string;
  /** Data local, AAAA-MM-DD. Null: sem prazo. */
  prazo: string | null;
  /** HH:MM, só com prazo. */
  hora: string | null;
  /** A conversa de onde a tarefa saiu, e o título dela. Null: criada pela tela. */
  conversa: number | null;
  origem: string | null;
  privada: boolean;
  criada: string;
  /** Quando foi marcada (UTC). Null enquanto aberta; a feita antes de hoje não vem. */
  feita: string | null;
};

/** O que a tela manda ao criar ou mudar. */
export type CamposTarefa = { texto?: string; prazo?: string | null; hora?: string | null; feita?: boolean };

export async function listarTarefas(): Promise<Resultado<Tarefa[]>> {
  try {
    const r = await fetch(`${BASE}/tarefas`);
    if (!r.ok) return { estado: 'sem-servidor' };
    return { estado: 'ok', dados: ((await r.json()) as { tarefas: Tarefa[] }).tarefas };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

async function enviarTarefa(url: string, metodo: 'POST' | 'PATCH', campos: CamposTarefa): Promise<Tarefa | null> {
  try {
    const r = await fetch(url, {
      method: metodo,
      headers: { 'Content-Type': 'application/json' },
      // Prazo vazio vai como "", que o servidor entende como "sem prazo".
      body: JSON.stringify({ ...campos, ...('prazo' in campos ? { prazo: campos.prazo ?? '' } : {}) }),
    });
    return r.ok ? ((await r.json()) as { tarefa: Tarefa }).tarefa : null;
  } catch {
    return null;
  }
}

export const criarTarefa = (campos: CamposTarefa & { texto: string }) => enviarTarefa(`${BASE}/tarefas`, 'POST', campos);

export const mudarTarefa = (id: number, campos: CamposTarefa) => enviarTarefa(`${BASE}/tarefas/${id}`, 'PATCH', campos);

export async function apagarTarefa(id: number): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/tarefas/${id}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

// — Agenda ————————————————————————————————————————————————————————————————————————

export type Compromisso = {
  id: number;
  titulo: string;
  /** Data local, AAAA-MM-DD. */
  dia: string;
  /** HH:MM de início. Null: o dia todo. */
  hora: string | null;
  /** Minutos. Null: não dito. */
  duracao: number | null;
  onde: string | null;
  conversa: number | null;
  origem: string | null;
  privado: boolean;
  criado: string;
};

export type CamposCompromisso = {
  titulo?: string;
  dia?: string;
  hora?: string | null;
  duracao?: number | null;
  onde?: string | null;
};

export async function listarAgenda(de: string, ate = de): Promise<Resultado<Compromisso[]>> {
  try {
    const r = await fetch(`${BASE}/agenda?de=${de}&ate=${ate}`);
    if (!r.ok) return { estado: 'sem-servidor' };
    return { estado: 'ok', dados: ((await r.json()) as { compromissos: Compromisso[] }).compromissos };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

async function enviarCompromisso(url: string, metodo: 'POST' | 'PATCH', campos: CamposCompromisso): Promise<Compromisso | null> {
  try {
    const r = await fetch(url, { method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(campos) });
    return r.ok ? ((await r.json()) as { compromisso: Compromisso }).compromisso : null;
  } catch {
    return null;
  }
}

export const criarCompromisso = (campos: CamposCompromisso & { titulo: string; dia: string }) =>
  enviarCompromisso(`${BASE}/agenda`, 'POST', campos);

export const mudarCompromisso = (id: number, campos: CamposCompromisso) =>
  enviarCompromisso(`${BASE}/agenda/${id}`, 'PATCH', campos);

export async function apagarCompromisso(id: number): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/agenda/${id}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

// — Voz ———————————————————————————————————————————————————————————————————————————

export type ResultadoVoz =
  | { estado: 'ok'; texto: string; segundos: number; duracao: number }
  | { estado: 'sem-modelo' | 'audio-ruim' | 'sem-servidor' };

/** O áudio gravado (webm/opus) vira texto no servidor, com o Whisper local. */
export async function transcreverAudio(audio: Blob): Promise<ResultadoVoz> {
  try {
    const r = await fetch(`${BASE}/voz`, { method: 'POST', body: audio });
    if (r.status === 503) return { estado: 'sem-modelo' };
    if (r.status === 400) return { estado: 'audio-ruim' };
    if (!r.ok) return { estado: 'sem-servidor' };
    const d = (await r.json()) as { texto: string; segundos: number; duracao: number };
    return { estado: 'ok', ...d };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

// — Fala ——————————————————————————————————————————————————————————————————————————

/** A resposta em pedaços pra falar: o primeiro é curto, pra começar logo. */
/** Uma frase fixa do Solis (a narração: "Vou passar pro Claude, um instante."),
 *  gravada uma vez no servidor com a voz escolhida. */
export function urlFrase(nome: string): string {
  return `${BASE}/fala/frase/${encodeURIComponent(nome)}`;
}

export async function partesDaFala(texto: string): Promise<string[] | null> {
  try {
    const r = await fetch(`${BASE}/fala/partes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto }),
    });
    return r.ok ? ((await r.json()) as { partes: string[] }).partes : null;
  } catch {
    return null;
  }
}

/** O endereço de onde um <audio> toca o pedaço enquanto ele chega (a Fish
 *  manda aos pedaços; as outras vozes, inteiro). O texto vai no corpo do
 *  POST, nunca na URL. null: servidor fora. */
export async function prepararFala(texto: string, conversa: number | null): Promise<string | null> {
  try {
    const r = await fetch(`${BASE}/fala/fluxo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto, conversa }),
    });
    return r.ok ? `${BASE}/fala/fluxo/${((await r.json()) as { id: string }).id}` : null;
  } catch {
    return null;
  }
}

export type AjustesFala = { voz: string; modelo: string; vozes: string[]; modelos: string[] };

/** A voz e o modelo do Gemini escolhidos, e as opções. Null: servidor fora. */
export async function lerAjustesFala(): Promise<AjustesFala | null> {
  try {
    const r = await fetch(`${BASE}/fala/ajustes`);
    return r.ok ? ((await r.json()) as AjustesFala) : null;
  } catch {
    return null;
  }
}

export async function ajustarFala(campos: { voz?: string; modelo?: string }): Promise<AjustesFala | null> {
  try {
    const r = await fetch(`${BASE}/fala/ajustes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(campos),
    });
    return r.ok ? ((await r.json()) as AjustesFala) : null;
  } catch {
    return null;
  }
}

/** Uma amostra de uma voz do Gemini, pra ouvir antes de escolher. 'sem-voz':
 *  o servidor respondeu, mas nenhuma voz da cadeia falou; null: servidor fora. */
export async function amostraDeVoz(voz: string): Promise<{ audio: Blob; voz: string } | 'sem-voz' | null> {
  try {
    const r = await fetch(`${BASE}/fala`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto: 'Oi, Matheus! É assim que eu falo as respostas. Gostou?', voz }),
    });
    if (r.status === 503) return 'sem-voz';
    if (!r.ok) return null;
    return { audio: await r.blob(), voz: r.headers.get('X-Solis-Voz') ?? '' };
  } catch {
    return null;
  }
}

// — Voz da Fish Audio (em teste) ——————————————————————————————————————————————————

export type EstadoFish = { chave: boolean; voz: string | null; nome: string | null; modelo: string };
export type VozFish = {
  id: string;
  nome: string;
  descricao: string;
  etiquetas: string[];
  linguas: string[];
  usos: number;
  curtidas: number;
  amostra: string | null;
};

export async function estadoFish(): Promise<EstadoFish | null> {
  try {
    const r = await fetch(`${BASE}/fala/fish`);
    return r.ok ? ((await r.json()) as EstadoFish) : null;
  } catch {
    return null;
  }
}

/** A chave é conferida na Fish antes de guardar. 'recusada': a Fish não aceitou. */
export async function guardarChaveFish(chave: string): Promise<EstadoFish | 'recusada' | null> {
  try {
    const r = await fetch(`${BASE}/fala/fish/chave`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chave }),
    });
    if (r.status === 400) return 'recusada';
    return r.ok ? ((await r.json()) as EstadoFish) : null;
  } catch {
    return null;
  }
}

export async function esquecerChaveFish(): Promise<EstadoFish | null> {
  try {
    const r = await fetch(`${BASE}/fala/fish/chave`, { method: 'DELETE' });
    return r.ok ? ((await r.json()) as EstadoFish) : null;
  } catch {
    return null;
  }
}

/** Uma página da biblioteca de vozes da Fish. `lingua` vazia = todas. */
export async function listarVozesFish(filtro: {
  busca: string;
  pagina: number;
  ordem: string;
  lingua: string;
  etiqueta: string;
}): Promise<{ vozes: VozFish[]; tem_mais: boolean } | null> {
  try {
    const q = new URLSearchParams({
      q: filtro.busca,
      pagina: String(filtro.pagina),
      ordem: filtro.ordem,
      lingua: filtro.lingua,
      etiqueta: filtro.etiqueta,
    });
    const r = await fetch(`${BASE}/fala/fish/vozes?${q}`);
    return r.ok ? ((await r.json()) as { vozes: VozFish[]; tem_mais: boolean }) : null;
  } catch {
    return null;
  }
}

export async function escolherVozFish(voz: string | null, nome: string | null = null): Promise<EstadoFish | null> {
  try {
    const r = await fetch(`${BASE}/fala/fish/voz`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voz, nome }),
    });
    return r.ok ? ((await r.json()) as EstadoFish) : null;
  } catch {
    return null;
  }
}

/** A Fish falando uma frase, direto (sem a cadeia), e quanto demorou. */
export async function amostraFish(voz: string | null): Promise<{ audio: Blob; segundos: number } | 'sem-voz' | null> {
  try {
    const r = await fetch(`${BASE}/fala/fish/amostra`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voz }),
    });
    if (r.status === 503) return 'sem-voz';
    if (!r.ok) return null;
    return { audio: await r.blob(), segundos: Number(r.headers.get('X-Solis-Tempo') ?? 0) };
  } catch {
    return null;
  }
}

// — Palavra de ativação ———————————————————————————————————————————————————————————

/** O endereço do WebSocket da escuta (o mesmo servidor, em ws://). */
export const urlEscuta = () => `${BASE.replace(/^http/, 'ws')}/escuta`;

/** O teste da escuta (backend/solis/voz_teste.py). */
export type PassoTeste = { i: number; tipo: 'chamada' | 'sem'; mostrar: string; esperado: string; inicio: number; fim: number };
export type RoteiroTeste = { inicio: number; preparo: number; passos: PassoTeste[]; duracao: number };
export type MedidaEscuta = {
  chamadas: number;
  acordou: number;
  entendeu: number;
  falsos: number;
  trechos_sem: number;
  latencia_mediana: number | null;
  latencia_max: number | null;
  passou: boolean;
};

export async function lerRoteiroTeste(): Promise<RoteiroTeste | null> {
  try {
    const r = await fetch(`${BASE}/voz/teste/roteiro`);
    return r.ok ? ((await r.json()) as RoteiroTeste) : null;
  } catch {
    return null;
  }
}

export async function listarTestesEscuta(): Promise<{ testes: { id: string; medidas: Record<string, MedidaEscuta> }[] } | null> {
  try {
    const r = await fetch(`${BASE}/voz/teste`);
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

/** A gravação e os tempos de cada frase; o servidor já começa a medir. */
export async function enviarTesteEscuta(wav: Blob, passos: PassoTeste[]): Promise<{ id: string } | { erro: string }> {
  try {
    const r = await fetch(`${BASE}/voz/teste`, {
      method: 'POST',
      headers: { 'Content-Type': 'audio/wav', 'X-Solis-Roteiro': encodeURIComponent(JSON.stringify(passos)) },
      body: wav,
    });
    if (r.ok) return (await r.json()) as { id: string };
    const corpo = (await r.json().catch(() => ({}))) as { motivo?: string };
    return { erro: corpo.motivo ? `Não deu pra guardar: ${corpo.motivo}.` : 'Não deu pra guardar a gravação.' };
  } catch {
    return { erro: 'O servidor do Solis não respondeu.' };
  }
}

/** `motor`: quem ouve a palavra — 'whisper' (hoje), 'porcupine' (se um dia
 *  houver chave) ou null (falta o modelo). */
export type EstadoAtivacao = { chave: boolean; palavra: boolean; idioma: boolean; motor: 'whisper' | 'porcupine' | null };

export async function estadoAtivacao(): Promise<{ estado: 'ok'; ativacao: EstadoAtivacao } | { estado: 'sem-servidor' }> {
  try {
    const r = await fetch(`${BASE}/ativacao`);
    if (!r.ok) return { estado: 'sem-servidor' };
    return { estado: 'ok', ativacao: (await r.json()) as EstadoAtivacao };
  } catch {
    return { estado: 'sem-servidor' };
  }
}

// — Controle do PC (backend/solis/pc.py) ——————————————————————————————————————————

export type EstadoPc = { ligada: boolean; pastas: string[]; disponivel: boolean };
export type AcaoPc = {
  id: number;
  quando: string;
  conversa: number | null;
  ferramenta: string;
  argumentos: Record<string, unknown>;
  resultado: string;
  ok: boolean;
};

async function pedirPc<T>(caminho: string, init?: RequestInit): Promise<{ ok: true; dados: T } | { ok: false; motivo: string | null }> {
  try {
    const r = await fetch(`${BASE}${caminho}`, init);
    if (r.status === 400) return { ok: false, motivo: ((await r.json()) as { motivo: string }).motivo };
    if (!r.ok) return { ok: false, motivo: null };
    return { ok: true, dados: (await r.json()) as T };
  } catch {
    return { ok: false, motivo: null };
  }
}

const JSON_PUT = (corpo: unknown): RequestInit => ({
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(corpo),
});

export const estadoPc = () => pedirPc<EstadoPc>('/pc');
export const guardarPastasPc = (pastas: string[]) => pedirPc<EstadoPc>('/pc/pastas', JSON_PUT({ pastas }));
export const ligarPc = (ligada: boolean) => pedirPc<EstadoPc>('/pc/ligada', JSON_PUT({ ligada }));
export const registroPc = (limite = 8) => pedirPc<AcaoPc[]>(`/pc/registro?limite=${limite}`);

// — Tarefas agendadas (backend/solis/agendadas.py) ——————————————————————————————
export type Frequencia = 'uma_vez' | 'diaria' | 'dias_uteis' | 'semanal' | 'hora_em_hora';

export type Agendada = {
  id: number;
  nome: string;
  pedido: string;
  frequencia: Frequencia;
  /** HH:MM; de hora em hora, só os minutos contam. */
  hora: string;
  /** 0 = segunda … 6 = domingo (só na semanal). */
  dia_semana: number | null;
  /** AAAA-MM-DD (só na de uma vez). */
  data: string | null;
  ativa: boolean;
  /** AAAA-MM-DDTHH:MM, hora local; null quando não vai rodar mais. */
  proxima: string | null;
  ultima: string | null;
  ultima_conversa: number | null;
  /** "Todo dia às 8:00", "Toda segunda às 9:30"… */
  descricao: string;
};

export type NovaAgendada = Pick<Agendada, 'nome' | 'pedido' | 'frequencia' | 'hora' | 'dia_semana' | 'data'> & {
  ativa?: boolean;
};

/** O controle da tela (backend/solis/tela.py): desligado até o Matheus ligar. */
export type Tela = { ligada: boolean; disponivel: boolean };

export async function lerTela(): Promise<Tela | null> {
  try {
    const r = await fetch(`${BASE}/tela`);
    return r.ok ? ((await r.json()) as Tela) : null;
  } catch {
    return null;
  }
}

export async function ligarTela(ligada: boolean): Promise<Tela | null> {
  try {
    const r = await fetch(`${BASE}/tela`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ligada }),
    });
    return r.ok ? ((await r.json()) as Tela) : null;
  } catch {
    return null;
  }
}

/** O uso da cota do Claude (backend/solis/uso.py): cada cota com quanto já foi
 *  (0-100) e quando volta. */
export type Cota = { tipo: string; rotulo: string; usado: number; volta: string | null };
export type Uso = { plano: string | null; cotas: Cota[]; quando: string };

export async function lerUso(atualizar = false): Promise<Uso | null> {
  try {
    const r = await fetch(`${BASE}/uso${atualizar ? '?atualizar=true' : ''}`);
    return r.ok ? ((await r.json()) as Uso) : null;
  } catch {
    return null;
  }
}

/** Os estilos de resposta (backend/solis/estilos.py): `atual` é o escolhido. */
export type Estilo = { id: string; nome: string; instrucoes: string; seu: boolean };
export type Estilos = { atual: string; estilos: Estilo[] };

export async function listarEstilos(): Promise<Estilos | null> {
  try {
    const r = await fetch(`${BASE}/estilos`);
    return r.ok ? ((await r.json()) as Estilos) : null;
  } catch {
    return null;
  }
}

export async function escolherEstilo(id: string): Promise<Estilos | null> {
  try {
    const r = await fetch(`${BASE}/estilos/atual`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
    return r.ok ? ((await r.json()) as Estilos) : null;
  } catch {
    return null;
  }
}

/** Cria (sem `id`) ou muda um estilo seu. Erro: o motivo em português. */
export async function salvarEstilo(nome: string, instrucoes: string, id?: string): Promise<Estilo | { erro: string }> {
  try {
    const r = await fetch(`${BASE}/estilos${id ? `/${encodeURIComponent(id)}` : ''}`, {
      method: id ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome, instrucoes }),
    });
    if (r.ok) return (await r.json()) as Estilo;
    const motivo = ((await r.json().catch(() => ({}))) as { motivo?: string }).motivo ?? '';
    const frases: Record<string, string> = {
      nome: 'Dê um nome ao estilo (até 40 caracteres).',
      'instruções': 'Diga como escrever (até 2000 caracteres).',
    };
    return { erro: frases[motivo] ?? (motivo ? motivo.charAt(0).toUpperCase() + motivo.slice(1) + '.' : 'Não deu pra salvar.') };
  } catch {
    return { erro: 'O servidor do Solis não respondeu.' };
  }
}

export async function apagarEstilo(id: string): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/estilos/${encodeURIComponent(id)}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

/** Um servidor MCP (backend/solis/servidores_mcp.py): os seus (`origem` seu),
 *  o da memória do Solis e os internos do Codex. `ferramentas`: a última
 *  conferida (nula se nunca conferido). */
export type FerramentasMcp = { total: number; so_leem: number; erro: string | null; quando: number };
export type ServidorMcp = {
  nome: string;
  tipo: 'comando' | 'endereco';
  comando: string;
  url: string;
  variaveis: string[];
  para: ('claude' | 'codex')[];
  origem: 'seu' | 'solis' | 'codex';
  editavel: boolean;
  desligado_no_codex: boolean;
  ferramentas: FerramentasMcp | null;
};
export type ServidorMcpInteiro = {
  nome: string;
  tipo: 'comando' | 'endereco';
  comando: string;
  url: string;
  variaveis: string;
  para: ('claude' | 'codex')[];
};

export async function listarServidoresMcp(): Promise<ServidorMcp[] | null> {
  try {
    const r = await fetch(`${BASE}/mcp`);
    return r.ok ? ((await r.json()) as { servidores: ServidorMcp[] }).servidores : null;
  } catch {
    return null;
  }
}

export async function lerServidorMcp(nome: string): Promise<ServidorMcpInteiro | null> {
  try {
    const r = await fetch(`${BASE}/mcp/${encodeURIComponent(nome)}`);
    return r.ok ? ((await r.json()) as ServidorMcpInteiro) : null;
  } catch {
    return null;
  }
}

const MOTIVO_MCP: Record<string, string> = {
  nome: 'O nome precisa ter só letras, números, hífen ou sublinhado.',
  tipo: 'Escolha se é um comando no PC ou um endereço.',
  comando: 'Escreva o comando que sobe o servidor (aspas fechadas).',
  'endereço': 'O endereço precisa começar com https:// (ou http://).',
  'variáveis': 'Uma variável por linha, no formato CHAVE=valor.',
  'pra quem': 'Escolha pra quem o servidor vale.',
};

/** Adiciona (sem `antigo`) ou muda. Erro: o motivo em português. */
export async function salvarServidorMcp(dados: ServidorMcpInteiro, antigo?: string): Promise<ServidorMcp | { erro: string }> {
  try {
    const r = await fetch(`${BASE}/mcp${antigo ? `/${encodeURIComponent(antigo)}` : ''}`, {
      method: antigo ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    if (r.ok) return (await r.json()) as ServidorMcp;
    const corpo = (await r.json().catch(() => ({}))) as { motivo?: string };
    const motivo = corpo.motivo ?? '';
    return { erro: MOTIVO_MCP[motivo] ?? (motivo ? motivo.charAt(0).toUpperCase() + motivo.slice(1) + '.' : 'Não deu pra salvar.') };
  } catch {
    return { erro: 'O servidor do Solis não respondeu.' };
  }
}

export async function removerServidorMcp(nome: string): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/mcp/${encodeURIComponent(nome)}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

export async function conferirServidorMcp(nome: string): Promise<FerramentasMcp | null> {
  try {
    const r = await fetch(`${BASE}/mcp/${encodeURIComponent(nome)}/conferir`, { method: 'POST' });
    return r.ok ? ((await r.json()) as FerramentasMcp) : null;
  } catch {
    return null;
  }
}

/** Uma skill (backend/solis/skills.py): as suas (`origem` solis, escritas no
 *  Solis ou à mão) e as da conta do claude.ai (`conta`: as suas de lá;
 *  `anthropic`: as da Anthropic). `ligada` só conta pro Claude. */
export type Skill = {
  nome: string;
  descricao: string;
  para: ('claude' | 'codex')[];
  origem: 'solis' | 'conta' | 'anthropic';
  editavel: boolean;
  ligada: boolean;
};
export type SkillInteira = { nome: string; descricao: string; instrucoes: string; para: ('claude' | 'codex')[] };

export async function listarSkills(): Promise<Skill[] | null> {
  try {
    const r = await fetch(`${BASE}/skills`);
    return r.ok ? ((await r.json()) as { skills: Skill[] }).skills : null;
  } catch {
    return null;
  }
}

export async function lerSkill(nome: string): Promise<SkillInteira | null> {
  try {
    const r = await fetch(`${BASE}/skills/${encodeURIComponent(nome)}`);
    return r.ok ? ((await r.json()) as SkillInteira) : null;
  } catch {
    return null;
  }
}

const MOTIVO_SKILL: Record<string, string> = {
  nome: 'O nome precisa ter letras e números, separados por hífen.',
  'descrição': 'Diga quando usar a skill (até 1024 caracteres).',
  'instruções': 'Escreva as instruções da skill.',
  'pra quem': 'Escolha pra quem a skill serve.',
};

/** Cria (sem `antigo`) ou muda. Erro: o motivo em português. */
export async function salvarSkill(dados: SkillInteira, antigo?: string): Promise<Skill | { erro: string }> {
  try {
    const r = await fetch(`${BASE}/skills${antigo ? `/${encodeURIComponent(antigo)}` : ''}`, {
      method: antigo ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    if (r.ok) return (await r.json()) as Skill;
    const corpo = (await r.json().catch(() => ({}))) as { motivo?: string };
    const motivo = corpo.motivo ?? '';
    return { erro: MOTIVO_SKILL[motivo] ?? (motivo ? motivo.charAt(0).toUpperCase() + motivo.slice(1) + '.' : 'Não deu pra salvar.') };
  } catch {
    return { erro: 'O servidor do Solis não respondeu.' };
  }
}

export async function apagarSkill(nome: string): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/skills/${encodeURIComponent(nome)}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

export async function ligarSkill(nome: string, ligada: boolean): Promise<boolean> {
  try {
    const r = await fetch(`${BASE}/skills/${encodeURIComponent(nome)}/ligada`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ligada }),
    });
    return r.ok;
  } catch {
    return false;
  }
}

/** O navegador do Claude (backend/solis/navegador.py): o Chrome ou o Edge do
 *  PC, numa janela com o perfil do Solis. */
export type Navegador = {
  escolhido: 'chrome' | 'msedge' | null;
  desligado: boolean;
  instalados: { canal: 'chrome' | 'msedge'; nome: string }[];
  pronto: boolean;
  aberto: boolean;
};

export async function lerNavegador(): Promise<Navegador | null> {
  try {
    const r = await fetch(`${BASE}/navegador`);
    return r.ok ? ((await r.json()) as Navegador) : null;
  } catch {
    return null;
  }
}

export async function escolherNavegador(navegador: string): Promise<Navegador | null> {
  try {
    const r = await fetch(`${BASE}/navegador`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ navegador }),
    });
    return r.ok ? ((await r.json()) as Navegador) : null;
  } catch {
    return null;
  }
}

/** Abre a janela (pra entrar nas contas). Erro: o motivo em português. */
export async function abrirNavegador(): Promise<Navegador | { erro: string }> {
  try {
    const r = await fetch(`${BASE}/navegador/abrir`, { method: 'POST' });
    if (r.ok) return (await r.json()) as Navegador;
    const corpo = (await r.json().catch(() => ({}))) as { motivo?: string };
    return { erro: corpo.motivo === 'navegador desligado' ? 'O navegador está desligado.' : 'O navegador não abriu.' };
  } catch {
    return { erro: 'O servidor do Solis não respondeu.' };
  }
}

export async function listarAgendadas(): Promise<Agendada[] | null> {
  try {
    const r = await fetch(`${BASE}/agendadas`);
    return r.ok ? ((await r.json()) as { agendadas: Agendada[] }).agendadas : null;
  } catch {
    return null;
  }
}

/** Cria (sem id) ou muda. Erro: o motivo em português (o servidor diz qual campo). */
export async function salvarAgendada(dados: NovaAgendada, id?: number): Promise<Agendada | { erro: string }> {
  try {
    const r = await fetch(`${BASE}/agendadas${id ? `/${id}` : ''}`, {
      method: id ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    const corpo = await r.json();
    if (r.ok) return corpo as Agendada;
    if (corpo.erro === 'sem_nome_ou_pedido') return { erro: 'Dê um nome e diga o que o Claude deve fazer.' };
    if (corpo.motivo === 'essa data já passou') return { erro: 'Essa data e hora já passaram.' };
    return { erro: corpo.motivo ? `Confira ${corpo.motivo === 'hora' ? 'a hora' : corpo.motivo === 'data' ? 'a data' : `o ${corpo.motivo}`}.` : 'Não deu pra salvar.' };
  } catch {
    return { erro: 'Não consegui falar com o servidor do Solis.' };
  }
}

export async function apagarAgendada(id: number): Promise<boolean> {
  try {
    return (await fetch(`${BASE}/agendadas/${id}`, { method: 'DELETE' })).ok;
  } catch {
    return false;
  }
}

/** Roda agora (não muda a próxima vez). Devolve a conversa onde o Claude vai responder. */
export async function rodarAgendada(id: number): Promise<number | null> {
  try {
    const r = await fetch(`${BASE}/agendadas/${id}/rodar`, { method: 'POST' });
    return r.ok ? ((await r.json()) as { conversa: number }).conversa : null;
  } catch {
    return null;
  }
}
