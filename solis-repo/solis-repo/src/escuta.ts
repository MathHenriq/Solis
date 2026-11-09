import { useEffect, useRef, useState } from 'react';
import { aoMudarFala } from './fala';
import { urlEscuta } from './servidor';

/** A escuta da palavra "Solis": o microfone fica aberto e o áudio vai pro
 *  servidor (só pro servidor do próprio Solis, em 127.0.0.1), que ouve a
 *  palavra com o Porcupine e transcreve o que vem depois
 *  (backend/solis/ativacao.py). Aqui: abrir o microfone, mandar os quadros,
 *  reconectar se o servidor cair, e pausar enquanto o Solis fala.
 *
 *  Ligada em Configurações → Voz; o estado fica no navegador, como a aparência. */

const CHAVE = 'solis.escuta';

export function escutaLigada(): boolean {
  try {
    return localStorage.getItem(CHAVE) === '1';
  } catch {
    return false;
  }
}

export function definirEscutaLigada(ligada: boolean) {
  try {
    localStorage.setItem(CHAVE, ligada ? '1' : '0');
  } catch {
    /* sem armazenamento: vale só nesta sessão */
  }
  window.dispatchEvent(new Event('solis-escuta'));
}

/** Um bipe curto e baixo quando a palavra é ouvida: a pessoa precisa saber que
 *  o Solis está ouvindo, mesmo olhando pra outra janela. Aprovado com a linha em Configurações
 *  (09/11/2026). */
function bipe(contexto: AudioContext) {
  const o = contexto.createOscillator();
  const g = contexto.createGain();
  o.frequency.value = 880;
  g.gain.setValueAtTime(0.0001, contexto.currentTime);
  g.gain.exponentialRampToValueAtTime(0.08, contexto.currentTime + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, contexto.currentTime + 0.18);
  o.connect(g).connect(contexto.destination);
  o.start();
  o.stop(contexto.currentTime + 0.2);
}

export type EstadoEscuta = 'desligada' | 'esperando' | 'ouvindo' | 'erro';

export function useEscuta(aoTexto: (texto: string) => void) {
  const [ligada, definirLigada] = useState(escutaLigada);
  const [estado, definirEstado] = useState<EstadoEscuta>('desligada');
  const [erro, definirErro] = useState<string | null>(null);
  const aoTextoAtual = useRef(aoTexto);
  aoTextoAtual.current = aoTexto;

  useEffect(() => {
    const atualizar = () => definirLigada(escutaLigada());
    window.addEventListener('solis-escuta', atualizar);
    return () => window.removeEventListener('solis-escuta', atualizar);
  }, []);

  useEffect(() => {
    if (!ligada) {
      definirEstado('desligada');
      return;
    }
    let fim = false;
    let fluxo: MediaStream | null = null;
    let contexto: AudioContext | null = null;
    let ws: WebSocket | null = null;
    let espera: number | undefined;
    let pausada = false;
    const pararDeOuvirFala = aoMudarFala((falando) => {
      pausada = falando;
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ pausa: falando }));
    });

    function conectar(tentativa = 0) {
      if (fim) return;
      ws = new WebSocket(urlEscuta());
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => {
        definirEstado('esperando');
        definirErro(null);
        if (pausada) ws?.send(JSON.stringify({ pausa: true }));
        tentativa = 0;
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data as string) as { tipo: string; texto?: string; motivo?: string };
        if (msg.tipo === 'ativou') {
          definirEstado('ouvindo');
          if (contexto) bipe(contexto);
        } else if (msg.tipo === 'texto') {
          definirEstado('esperando');
          if (msg.texto) aoTextoAtual.current(msg.texto);
        } else if (msg.tipo === 'nada') {
          definirEstado('esperando');
        } else if (msg.tipo === 'erro') {
          definirErro(msg.motivo ?? 'a escuta não ligou');
          definirEstado('erro');
          fim = true; // configuração faltando: não adianta reconectar
        }
      };
      ws.onclose = () => {
        if (fim) return;
        // Servidor reiniciando ou fora: tenta de novo, cada vez mais devagar.
        espera = window.setTimeout(() => conectar(tentativa + 1), Math.min(30_000, 1000 * 2 ** tentativa));
      };
    }

    (async () => {
      try {
        fluxo = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
        contexto = new AudioContext({ sampleRate: 16000 });
        await contexto.audioWorklet.addModule('/escuta-processador.js');
        const no = new AudioWorkletNode(contexto, 'escuta-processador');
        no.port.onmessage = (e) => {
          if (!pausada && ws?.readyState === WebSocket.OPEN) ws.send(e.data as ArrayBuffer);
        };
        contexto.createMediaStreamSource(fluxo).connect(no);
        if (fim) return;
        conectar();
      } catch {
        definirErro('Sem acesso ao microfone. Libere no navegador.');
        definirEstado('erro');
      }
    })();

    return () => {
      fim = true;
      pararDeOuvirFala();
      window.clearTimeout(espera);
      ws?.close();
      fluxo?.getTracks().forEach((t) => t.stop());
      contexto?.close();
    };
  }, [ligada]);

  return { estado, erro, ligada };
}
