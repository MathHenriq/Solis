import { useEffect, useRef, useState } from 'react';
import { transcreverAudio } from './servidor';

/** Apertar pra falar: um clique no microfone começa a ouvir, outro para, e o
 *  texto transcrito (Whisper, no servidor local) volta pra caixa da conversa —
 *  a pessoa confere antes de enviar. Esc desiste sem transcrever.
 *
 *  O áudio não é guardado em lugar nenhum: vai do navegador pro servidor e
 *  morre ali (backend/solis/voz.py). */

export type EstadoVoz = 'parado' | 'ouvindo' | 'transcrevendo';

/** Fala mais longa que isto para sozinha: apertar pra falar é frase, não ditado. */
const FALA_MAX_MS = 2 * 60 * 1000;
/** Quanto tempo o aviso de erro fica no lugar do texto de ajuda da caixa. */
const ERRO_MS = 5000;

const ERROS = {
  'sem-microfone': 'Sem acesso ao microfone. Libere no navegador e tente de novo.',
  'sem-modelo': 'Falta o modelo de voz no servidor do Solis.',
  'audio-ruim': 'Não consegui ler o áudio. Tente de novo.',
  'sem-servidor': 'Servidor do Solis desligado.',
  vazio: 'Não ouvi nada. Tente de novo, mais perto do microfone.',
} as const;

export function useVoz(aoTexto: (texto: string) => void) {
  const [estado, definirEstado] = useState<EstadoVoz>('parado');
  const [erro, definirErro] = useState<string | null>(null);
  const gravador = useRef<MediaRecorder | null>(null);
  const cancelado = useRef(false);
  const limite = useRef<number | undefined>(undefined);
  const prazoErro = useRef<number | undefined>(undefined);
  const aoTextoAtual = useRef(aoTexto);
  aoTextoAtual.current = aoTexto;

  const avisar = (chave: keyof typeof ERROS) => {
    window.clearTimeout(prazoErro.current);
    definirErro(ERROS[chave]);
    prazoErro.current = window.setTimeout(() => definirErro(null), ERRO_MS);
  };

  async function comecar() {
    definirErro(null);
    let fluxo: MediaStream;
    try {
      fluxo = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      avisar('sem-microfone');
      return;
    }
    const partes: Blob[] = [];
    const g = new MediaRecorder(fluxo);
    g.ondataavailable = (e) => e.data.size && partes.push(e.data);
    g.onstop = async () => {
      fluxo.getTracks().forEach((t) => t.stop());
      window.clearTimeout(limite.current);
      gravador.current = null;
      if (cancelado.current) {
        definirEstado('parado');
        return;
      }
      definirEstado('transcrevendo');
      const r = await transcreverAudio(new Blob(partes, { type: g.mimeType }));
      definirEstado('parado');
      if (r.estado !== 'ok') return avisar(r.estado);
      if (!r.texto.trim()) return avisar('vazio');
      aoTextoAtual.current(r.texto.trim());
    };
    cancelado.current = false;
    gravador.current = g;
    g.start();
    definirEstado('ouvindo');
    limite.current = window.setTimeout(() => g.state === 'recording' && g.stop(), FALA_MAX_MS);
  }

  const parar = () => gravador.current?.state === 'recording' && gravador.current.stop();
  const cancelar = () => {
    cancelado.current = true;
    parar();
  };

  // Clique: começa ou para. Transcrevendo, não faz nada (um clique a mais não
  // pode começar outra gravação por cima).
  const alternar = () => (estado === 'parado' ? comecar() : estado === 'ouvindo' ? parar() : undefined);

  // Esc desiste enquanto ouve; sair da tela também, sem mandar nada.
  useEffect(() => {
    if (estado !== 'ouvindo') return;
    const tecla = (e: KeyboardEvent) => e.key === 'Escape' && cancelar();
    window.addEventListener('keydown', tecla);
    return () => window.removeEventListener('keydown', tecla);
  }, [estado]);
  useEffect(() => () => cancelar(), []);

  /** O texto de ajuda da caixa enquanto a voz está em uso, ou o erro. */
  const dica =
    erro ??
    (estado === 'ouvindo'
      ? 'Ouvindo… clique no microfone pra parar (Esc desiste)'
      : estado === 'transcrevendo'
        ? 'Transcrevendo…'
        : null);

  return { estado, alternar, dica, erro: !!erro };
}
