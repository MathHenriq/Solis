import { useEffect, useRef, useState } from 'react';
import { partesDaFala, prepararFala, urlFrase } from './servidor';
import { PedacoDeFala } from './somAosPedacos';

/** O Solis falando: toca uma resposta em pedaços. O primeiro pedaço é curto
 *  (o servidor corta assim) e começa a tocar enquanto o próximo é gerado — a
 *  voz de nuvem leva segundos por frase, e esperar a resposta inteira seria
 *  silêncio demais.
 *
 *  Quem fala (nuvem, reserva ou local) é o servidor que decide
 *  (backend/solis/fala.py); privado só sai pela voz local.
 *
 *  Cada pedaço toca ENQUANTO chega (11/11/2026): o <audio> busca o fluxo do
 *  servidor, e a Fish manda o áudio enquanto gera — o primeiro som em
 *  ~0,8 s em vez de ~3 s do áudio inteiro. O próximo pedaço já começa a
 *  carregar enquanto este toca. */

/** Marcado quando a mensagem foi ditada pela voz: a resposta dela é falada
 *  sozinha. Fica no módulo porque a primeira mensagem sai da tela de abertura
 *  e a resposta chega na thread. */
export const respostaFalada = { proxima: false, narrou: false };

/** A próxima resposta vai ser falada (ou não): e ainda não foi narrada. */
export function marcarRespostaFalada(falada: boolean) {
  respostaFalada.proxima = falada;
  respostaFalada.narrou = false;
}

// Enquanto a narração toca, `falando` fica neste valor (nenhuma mensagem tem
// esse id): a escuta pausa igual, e nenhuma mensagem aparece falando.
const NARRANDO = -1;

const CHAVE_AUTO = 'solis.fala.auto';

/** Falar sozinho a resposta de uma mensagem ditada (Configurações → Voz).
 *  Ligado por padrão. Guardado no navegador, como a aparência. */
export function falaAutomatica(): boolean {
  try {
    return localStorage.getItem(CHAVE_AUTO) !== '0';
  } catch {
    return true;
  }
}

export function definirFalaAutomatica(ligada: boolean) {
  try {
    localStorage.setItem(CHAVE_AUTO, ligada ? '1' : '0');
  } catch {
    /* sem armazenamento: vale só nesta sessão */
  }
}

/** Quem precisa saber que o Solis está falando: a escuta da palavra pausa
 *  enquanto ele fala, senão a própria voz dele (dizendo "Solis") o acordaria. */
const ouvintesDaFala = new Set<(falando: boolean, pergunta: boolean) => void>();
// Quem está falando agora (cada useFala é um). Global, e não o estado de um
// componente: em 16/11/2026 o Matheus saiu da conversa enquanto (ou logo
// depois que) o Solis falava, o componente sumiu sem avisar "parei", e a
// escuta da palavra ficou pausada pra sempre — dez "Solis" sem resposta.
const falandoAgora = new Set<symbol>();

// A resposta falada que acabou de terminar (inteira, sem ser cortada) acabou
// numa pergunta: a escuta ouve a resposta sem precisar de "Solis". Pedido do
// Matheus (17/11/2026): "qual música você quer ouvir?", ele respondeu, e a
// escuta esperava o "Solis" de novo — a resposta se perdeu.
let fimComPergunta = false;

// "Não entendi, pode explicar?" não abre a escuta sem o "Solis": quem não foi
// entendido chama de novo. Em 19/11/2026 uma ativação sem chamada virou um
// laço: o Solis perguntava, ouvia o ruído ("." ) ou a conversa do Matheus com
// os amigos, e perguntava de novo. A mesma lista do memoria.nao_entendeu.
const NAO_ENTENDEU =
  /\bn[ãa]o (entendi|compreendi|captei|consegui entender)\b|\bpode (explicar|esclarecer|repetir|reformular)\b|\bn[ãa]o ficou claro\b/i;

/** O texto falado acaba numa pergunta (o "?" no fim, com aspas ou parêntese
 *  depois) que espera resposta: não a de quem não entendeu. */
export function acabaEmPergunta(texto: string): boolean {
  return /\?["'”»)\]]*\s*$/.test(texto) && !NAO_ENTENDEU.test(texto);
}

function avisarFala() {
  const falando = falandoAgora.size > 0;
  const pergunta = !falando && fimComPergunta;
  fimComPergunta = false;
  ouvintesDaFala.forEach((o) => o(falando, pergunta));
}

function marcarFala(quem: symbol, falando: boolean) {
  const antes = falandoAgora.size > 0;
  if (falando) falandoAgora.add(quem);
  else falandoAgora.delete(quem);
  if (antes !== falandoAgora.size > 0) avisarFala();
}

/** A voz do pedido ao vivo (escuta.ts, que toca o que o servidor manda): a escuta
 *  da palavra pausa igual a quando o Solis fala pela tela. */
const AO_VIVO = Symbol('pedido ao vivo');
export function marcarFalaAoVivo(falando: boolean) {
  marcarFala(AO_VIVO, falando);
}

/** `pergunta`: o Solis acabou de falar uma resposta inteira que termina numa pergunta. */
export function aoMudarFala(ouvinte: (falando: boolean, pergunta: boolean) => void): () => void {
  ouvintesDaFala.add(ouvinte);
  // Quem chega no meio de uma fala já sabe que é pra pausar.
  if (falandoAgora.size) ouvinte(true, false);
  return () => ouvintesDaFala.delete(ouvinte);
}

/** Os pedaços a falar, em ordem; quem toca espera o próximo chegar. */
class FilaDeFala {
  private partes: string[] = [];
  private fechada = false;
  /** A resposta ditada acaba numa pergunta (só a que foi falada sozinha, por voz). */
  pergunta = false;
  private avisar: (() => void) | null = null;

  por(partes: string[]) {
    this.partes.push(...partes);
    this.avisar?.();
  }

  fechar() {
    this.fechada = true;
    this.avisar?.();
  }

  /** O próximo pedaço, ou null quando a fila fechou e acabou. */
  async proxima(): Promise<string | null> {
    while (!this.partes.length && !this.fechada) await new Promise<void>((ok) => (this.avisar = ok));
    this.avisar = null;
    return this.partes.shift() ?? null;
  }
}

/** Até onde (a partir de `desde`) o texto tem frases completas: o ponto, a
 *  exclamação ou a interrogação seguidos de espaço ou quebra de linha. O que
 *  vem depois ainda está chegando. "3.5" não corta (sem espaço depois). */
export function fimDaUltimaFrase(texto: string, desde: number): number {
  let fim = desde;
  const re = /[.!?…]+["')\]]*(?=\s)/g;
  re.lastIndex = desde;
  for (let m = re.exec(texto); m; m = re.exec(texto)) fim = m.index + m[0].length;
  return fim;
}

export function useFala(conversa: number | null) {
  const [falando, definirFalando] = useState<number | null>(null);
  const [preparando, definirPreparando] = useState(false);
  const [falhou, definirFalhou] = useState<number | null>(null);
  const vez = useRef(0);
  const audio = useRef<PedacoDeFala | null>(null);
  // O pedaço seguinte, já carregando: parar tem que cortar ele também.
  const seguinte = useRef<Promise<PedacoDeFala | null> | null>(null);
  // A narração tocando (uma frase fixa enquanto o Claude trabalha).
  const narracao = useRef<{ el: PedacoDeFala; fim: Promise<void> } | null>(null);

  const eu = useRef(Symbol('fala'));

  useEffect(() => {
    marcarFala(eu.current, falando !== null);
  }, [falando]);
  // Saindo da tela (no meio da fala ou não): este não fala mais. O setState do
  // parar() num componente que sumiu não roda o efeito de cima — por isso aqui.
  useEffect(() => {
    const quem = eu.current;
    return () => marcarFala(quem, false);
  }, []);

  const parar = () => {
    vez.current += 1;
    audio.current?.cancelar();
    audio.current = null;
    void seguinte.current?.then((p) => p?.cancelar());
    seguinte.current = null;
    narracao.current?.el.cancelar();
    narracao.current = null;
    definirFalando(null);
    definirPreparando(false);
  };
  useEffect(() => parar, []);

  /** A narração (IDEIAS.md): pela voz, o Claude leva de 3,5 a 14 s até a
   *  primeira palavra, e era silêncio. Uma frase fixa, gravada uma vez no
   *  servidor, avisa o que está acontecendo. Não toca por cima de outra fala. */
  function narrar(nome: string) {
    if (narracao.current || audio.current) return;
    const el = new PedacoDeFala(urlFrase(nome, conversa));
    definirFalando(NARRANDO);
    const fim = el
      .tocar(() => {})
      .then(() => undefined)
      .finally(() => {
        if (narracao.current?.el === el) narracao.current = null;
        definirFalando((f) => (f === NARRANDO ? null : f));
      });
    narracao.current = { el, fim };
  }

  /** Toca os pedaços da fila em ordem, carregando o seguinte enquanto o atual
   *  toca. A fila pode ainda estar recebendo (a resposta chegando). */
  async function tocarFila(id: number, fila: FilaDeFala, minha: number, quem?: string) {
    const carregar = async (texto: string | null) => {
      if (texto === null) return null;
      const url = await prepararFala(texto, conversa, quem);
      return url ? new PedacoDeFala(url) : ('falhou' as const);
    };
    const falhar = () => {
      definirFalhou(id);
      window.setTimeout(() => definirFalhou((f) => (f === id ? null : f)), 4000);
    };
    let proximo = fila.proxima().then(carregar);
    for (;;) {
      const el = await proximo;
      if (vez.current !== minha) {
        if (el && el !== 'falhou') el.cancelar();
        return;
      }
      if (el === null) {
        // A fila fechou: acabou, inteira. Acabou perguntando: a escuta ouve a resposta.
        if (fila.pergunta) fimComPergunta = true;
        break;
      }
      // Já carrega o seguinte enquanto este toca (ou espera ele chegar).
      proximo = fila.proxima().then(carregar);
      seguinte.current = proximo.then((p) => (p === 'falhou' ? null : p));
      if (el === 'falhou') {
        falhar();
        break;
      }
      audio.current = el;
      const deu = await el.tocar(() => definirPreparando(false));
      if (vez.current !== minha) return;
      if (!deu) {
        falhar();
        break;
      }
    }
    if (vez.current === minha) {
      definirFalando(null);
      definirPreparando(false);
      audio.current = null;
    }
  }

  async function comecar(id: number): Promise<number> {
    // A resposta chegou com a narração ainda tocando: espera ela acabar (é curta).
    if (narracao.current) await narracao.current.fim;
    parar();
    const minha = ++vez.current;
    definirFalando(id);
    definirPreparando(true);
    definirFalhou(null);
    return minha;
  }

  /** Ouvir uma resposta: na voz de `quem` a disse (a personalidade dela), não
   *  na de quem está falando na conversa agora. */
  async function ouvir(id: number, texto: string, quem?: string) {
    acompanhando.current = null;
    const fila = new FilaDeFala();
    const minha = await comecar(id);
    fila.por((await partesDaFala(texto)) ?? []);
    fila.fechar();
    await tocarFila(id, fila, minha, quem);
  }

  // A resposta que está sendo falada enquanto chega: até onde do texto já foi
  // pra fila, e a fila dela.
  const acompanhando = useRef<{ id: number; enviado: number; fila: FilaDeFala; pedidos: Promise<void>; fechada: boolean } | null>(null);

  /** A cascata (IDEIAS.md): fala a resposta ENQUANTO ela chega — cada frase
   *  completa vai pra fila assim que termina, e o resto no fim. Chamado a cada
   *  pedaço novo do texto; `acabou` no fim da resposta. */
  function acompanhar(id: number, texto: string, acabou: boolean) {
    let a = acompanhando.current;
    if (!a || a.id !== id) {
      if (!texto.trim()) return; // nada pra falar (ou a resposta falhou antes)
      if (!acabou && fimDaUltimaFrase(texto, 0) === 0) return; // nada completo ainda
      const nova = { id, enviado: 0, fila: new FilaDeFala(), pedidos: Promise.resolve(), fechada: false };
      a = nova;
      void (async () => {
        const minha = await comecar(id);
        // O parar() do começo não pode desligar esta mesma resposta.
        acompanhando.current = nova;
        await tocarFila(id, nova.fila, minha);
        if (acompanhando.current === nova) acompanhando.current = null;
      })();
      acompanhando.current = nova;
    }
    const atual = a;
    if (atual.fechada) return;
    const corte = acabou ? texto.length : fimDaUltimaFrase(texto, atual.enviado);
    if (corte > atual.enviado) {
      const trecho = texto.slice(atual.enviado, corte);
      atual.enviado = corte;
      // Em ordem: o trecho seguinte só entra na fila depois do anterior.
      atual.pedidos = atual.pedidos.then(async () => atual.fila.por((await partesDaFala(trecho)) ?? []));
    }
    if (acabou) {
      atual.fechada = true;
      atual.fila.pergunta = acabaEmPergunta(texto);
      atual.pedidos = atual.pedidos.then(() => atual.fila.fechar());
    }
  }

  return { falando, preparando, falhou, ouvir, parar, narrar, acompanhar };
}
