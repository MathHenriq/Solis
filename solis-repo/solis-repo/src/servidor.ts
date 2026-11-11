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
};

/** `cerebro`: quem respondeu — uma chave de NOMES_CEREBRO. Nulo nas falas da
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
  /** Um cérebro escolhido com /claude, /groq... não respondeu. */
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

/** Um pedaço em áudio, pela cadeia de vozes do servidor (nuvem → reserva →
 *  local). `conversa` deixa o servidor decidir se pode ir pra nuvem. */
export async function falarTexto(texto: string, conversa: number | null): Promise<{ audio: Blob; voz: string } | null> {
  try {
    const r = await fetch(`${BASE}/fala`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto, conversa }),
    });
    if (!r.ok) return null;
    return { audio: await r.blob(), voz: r.headers.get('X-Solis-Voz') ?? '' };
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

// — Palavra de ativação ———————————————————————————————————————————————————————————

/** O endereço do WebSocket da escuta (o mesmo servidor, em ws://). */
export const urlEscuta = () => `${BASE.replace(/^http/, 'ws')}/escuta`;

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
