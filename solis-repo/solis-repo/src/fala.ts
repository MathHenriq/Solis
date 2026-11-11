import { useEffect, useRef, useState } from 'react';
import { partesDaFala, prepararFala } from './servidor';
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
export const respostaFalada = { proxima: false };

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
const ouvintesDaFala = new Set<(falando: boolean) => void>();

export function aoMudarFala(ouvinte: (falando: boolean) => void): () => void {
  ouvintesDaFala.add(ouvinte);
  return () => ouvintesDaFala.delete(ouvinte);
}

export function useFala(conversa: number | null) {
  const [falando, definirFalando] = useState<number | null>(null);
  const [preparando, definirPreparando] = useState(false);
  const [falhou, definirFalhou] = useState<number | null>(null);
  const vez = useRef(0);
  const audio = useRef<PedacoDeFala | null>(null);
  // O pedaço seguinte, já carregando: parar tem que cortar ele também.
  const seguinte = useRef<Promise<PedacoDeFala | null> | null>(null);

  useEffect(() => {
    ouvintesDaFala.forEach((o) => o(falando !== null));
  }, [falando]);

  const parar = () => {
    vez.current += 1;
    audio.current?.cancelar();
    audio.current = null;
    void seguinte.current?.then((p) => p?.cancelar());
    seguinte.current = null;
    definirFalando(null);
    definirPreparando(false);
  };
  useEffect(() => parar, []);

  async function ouvir(id: number, texto: string) {
    parar();
    const minha = ++vez.current;
    definirFalando(id);
    definirPreparando(true);
    definirFalhou(null);
    const pedacos = (await partesDaFala(texto)) ?? [];
    const carregar = async (i: number) => {
      const url = await prepararFala(pedacos[i], conversa);
      return url ? new PedacoDeFala(url) : null;
    };
    const falhar = () => {
      definirFalhou(id);
      window.setTimeout(() => definirFalhou((f) => (f === id ? null : f)), 4000);
    };
    let proximo = pedacos.length ? carregar(0) : null;
    for (let i = 0; i < pedacos.length && proximo; i++) {
      const el = await proximo;
      if (vez.current !== minha) {
        el?.cancelar();
        return;
      }
      // Já carrega o seguinte enquanto este toca.
      proximo = i + 1 < pedacos.length ? carregar(i + 1) : null;
      seguinte.current = proximo;
      if (!el) {
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

  return { falando, preparando, falhou, ouvir, parar };
}
