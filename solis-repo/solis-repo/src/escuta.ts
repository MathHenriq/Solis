import { useEffect, useRef, useState } from 'react';
import { aoMudarFala } from './fala';
import { criarAnalisador, definirFonte } from './nivel';
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
    let analisador: AnalyserNode | null = null;
    const pararDeOuvirFala = aoMudarFala((falando) => {
      pausada = falando;
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ pausa: falando }));
    });

    // O microfone (e o áudio a 16 kHz) só fica aberto enquanto o servidor
    // está de fato escutando: abre no "pronta" e fecha no erro ou na queda.
    // Antes abria primeiro e não fechava no erro — com o modelo do Whisper
    // faltando, o microfone ficava aberto o app inteiro, à toa, e o som do PC
    // ficava estranho (relato do Matheus, 13/11/2026).
    async function abrirMicrofone() {
      if (fluxo || fim) return;
      try {
        // Sem o processamento de chamada (eco, ruído, ganho): com ele, o
        // navegador mexe no microfone do Windows. O eco não faz falta: a
        // escuta já pausa enquanto o Solis fala.
        const f = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
        });
        if (fim || ws?.readyState !== WebSocket.OPEN) {
          f.getTracks().forEach((t) => t.stop());
          return;
        }
        fluxo = f;
        contexto = new AudioContext({ sampleRate: 16000 });
        await contexto.audioWorklet.addModule('/escuta-processador.js');
        const no = new AudioWorkletNode(contexto, 'escuta-processador');
        no.port.onmessage = (e) => {
          if (!pausada && ws?.readyState === WebSocket.OPEN) ws.send(e.data as ArrayBuffer);
        };
        const origem = contexto.createMediaStreamSource(fluxo);
        origem.connect(no);
        analisador = criarAnalisador(contexto, origem);
        definirEstado('esperando');
      } catch {
        fecharMicrofone();
        definirErro('Sem acesso ao microfone. Libere no navegador.');
        definirEstado('erro');
      }
    }

    function fecharMicrofone() {
      definirFonte(null);
      fluxo?.getTracks().forEach((t) => t.stop());
      fluxo = null;
      void contexto?.close();
      contexto = null;
      analisador = null;
    }

    function conectar(tentativa = 0) {
      if (fim) return;
      ws = new WebSocket(urlEscuta());
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => {
        definirErro(null);
        if (pausada) ws?.send(JSON.stringify({ pausa: true }));
        tentativa = 0;
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data as string) as { tipo: string; texto?: string; motivo?: string };
        if (msg.tipo === 'pronta') {
          void abrirMicrofone();
        } else if (msg.tipo === 'ativou') {
          definirEstado('ouvindo');
          if (contexto) bipe(contexto);
          definirFonte(analisador);
        } else if (msg.tipo === 'texto') {
          definirFonte(null);
          definirEstado('esperando');
          if (msg.texto) aoTextoAtual.current(msg.texto);
        } else if (msg.tipo === 'nada') {
          definirFonte(null);
          definirEstado('esperando');
        } else if (msg.tipo === 'erro') {
          fecharMicrofone();
          definirErro(msg.motivo ?? 'a escuta não ligou');
          definirEstado('erro');
          fim = true; // configuração faltando: não adianta reconectar
        }
      };
      ws.onclose = () => {
        // Servidor fora: sem ele, o microfone não serve pra nada — fecha.
        fecharMicrofone();
        if (fim) return;
        // Servidor reiniciando ou fora: tenta de novo, cada vez mais devagar.
        espera = window.setTimeout(() => conectar(tentativa + 1), Math.min(30_000, 1000 * 2 ** tentativa));
      };
    }

    conectar();

    return () => {
      fim = true;
      pararDeOuvirFala();
      window.clearTimeout(espera);
      ws?.close();
      fecharMicrofone();
    };
  }, [ligada]);

  return { estado, erro, ligada };
}
