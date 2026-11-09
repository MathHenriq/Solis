import { useEffect, useRef, useState } from 'react';
import { falarTexto, partesDaFala } from './servidor';

/** O Solis falando: toca uma resposta em pedaços. O primeiro pedaço é curto
 *  (o servidor corta assim) e começa a tocar enquanto o próximo é gerado — a
 *  voz de nuvem leva segundos por frase, e esperar a resposta inteira seria
 *  silêncio demais.
 *
 *  Quem fala (nuvem, reserva ou local) é o servidor que decide
 *  (backend/solis/fala.py); privado só sai pela voz local. */

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

export function useFala(conversa: number | null) {
  const [falando, definirFalando] = useState<number | null>(null);
  const [preparando, definirPreparando] = useState(false);
  const [falhou, definirFalhou] = useState<number | null>(null);
  const vez = useRef(0);
  const audio = useRef<HTMLAudioElement | null>(null);

  const parar = () => {
    vez.current += 1;
    audio.current?.pause();
    audio.current = null;
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
    let proximo = pedacos.length ? falarTexto(pedacos[0], conversa) : null;
    for (let i = 0; i < pedacos.length && proximo; i++) {
      const pronto = await proximo;
      if (vez.current !== minha) return;
      // Já pede o seguinte enquanto este toca.
      proximo = i + 1 < pedacos.length ? falarTexto(pedacos[i + 1], conversa) : null;
      if (!pronto) {
        definirFalhou(id);
        window.setTimeout(() => definirFalhou((f) => (f === id ? null : f)), 4000);
        break;
      }
      const url = URL.createObjectURL(pronto.audio);
      const el = new Audio(url);
      audio.current = el;
      definirPreparando(false);
      await new Promise<void>((fim) => {
        el.onended = el.onerror = () => fim();
        el.play().catch(() => fim());
      });
      URL.revokeObjectURL(url);
      if (vez.current !== minha) return;
    }
    if (vez.current === minha) {
      definirFalando(null);
      definirPreparando(false);
      audio.current = null;
    }
  }

  return { falando, preparando, falhou, ouvir, parar };
}
