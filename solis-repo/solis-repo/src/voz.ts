import { useEffect, useRef, useState } from 'react';
import { criarAnalisador, definirFonte } from './nivel';
import { transcreverAudio, urlDitado } from './servidor';

/** Apertar pra falar: um clique no microfone começa a ouvir, outro para, e o
 *  texto transcrito volta pra caixa da conversa — a pessoa confere antes de
 *  enviar. Esc desiste sem transcrever.
 *
 *  No Windows, quem grava é o servidor, pelo microfone direto do Windows
 *  (main.ditado, 22/11/2026): aberto aqui na janela, o microfone estragava o
 *  som do Discord, como já tinha acontecido com a escuta. E ele transcreve
 *  online primeiro (o Whisper da Groq; o do PC sem internet). Sem o microfone
 *  do Windows, a janela grava pela dela, como antes.
 *
 *  O áudio não é guardado em lugar nenhum: morre no servidor (backend/solis/voz.py). */

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

/** `privado`: lido na hora de gravar — o cadeado ligado, a fala fica no Solis. */
export function useVoz(aoTexto: (texto: string) => void, privado: () => boolean = () => false) {
  const [estado, definirEstado] = useState<EstadoVoz>('parado');
  const [erro, definirErro] = useState<string | null>(null);
  const gravador = useRef<MediaRecorder | null>(null);
  // O ditado no servidor (o microfone do Windows): a conexão enquanto ouve.
  const nativo = useRef<WebSocket | null>(null);
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

  /** O servidor grava pelo microfone do Windows. 'sem-nativo': não tem (fora do
   *  Windows, ou o microfone não abriu lá) — a janela grava pela dela. */
  function noServidor(): Promise<'ouvindo' | 'sem-nativo'> {
    return new Promise((resolver) => {
      let ws: WebSocket;
      try {
        ws = new WebSocket(urlDitado(privado()));
      } catch {
        resolver('sem-nativo');
        return;
      }
      let ouvindo = false;
      let terminou = false;
      const acabar = () => {
        terminou = true;
        window.clearTimeout(limite.current);
        if (nativo.current === ws) nativo.current = null;
        definirEstado('parado');
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data as string) as { tipo: string; texto?: string; estado?: string };
        if (msg.tipo === 'sem_nativo') {
          terminou = true;
          resolver('sem-nativo');
        } else if (msg.tipo === 'ouvindo') {
          ouvindo = true;
          nativo.current = ws;
          definirEstado('ouvindo');
          limite.current = window.setTimeout(parar, FALA_MAX_MS);
          resolver('ouvindo');
        } else if (msg.tipo === 'texto') {
          acabar();
          aoTextoAtual.current((msg.texto ?? '').trim());
        } else if (msg.tipo === 'erro') {
          acabar();
          const chave = msg.estado as keyof typeof ERROS;
          avisar(chave in ERROS ? chave : 'audio-ruim');
        }
      };
      ws.onclose = () => {
        if (!ouvindo) return resolver('sem-nativo');
        // Caiu no meio (o servidor reiniciou): sem texto, e a caixa volta ao normal.
        if (!terminou && !cancelado.current) {
          acabar();
          avisar('sem-servidor');
        } else if (!terminou) acabar();
      };
    });
  }

  async function comecar() {
    definirErro(null);
    cancelado.current = false;
    if ((await noServidor()) === 'ouvindo') return;
    let fluxo: MediaStream;
    try {
      // Sem o processamento de chamada, como na escuta (escuta.ts): com o
      // ganho automático ligado, o navegador mexe no volume do microfone do
      // Windows enquanto a pessoa fala — e ele fica mexido depois. O Whisper
      // ouve bem sem eco e sem ruído tratados.
      fluxo = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
    } catch {
      avisar('sem-microfone');
      return;
    }
    const partes: Blob[] = [];
    // O brilho do símbolo segue esta voz (nivel.ts) — uma cópia do microfone
    // medida aqui mesmo, sem esperar o Whisper.
    const contexto = new AudioContext();
    definirFonte(criarAnalisador(contexto, contexto.createMediaStreamSource(fluxo)));
    const g = new MediaRecorder(fluxo);
    g.ondataavailable = (e) => e.data.size && partes.push(e.data);
    g.onstop = async () => {
      definirFonte(null);
      contexto.close();
      fluxo.getTracks().forEach((t) => t.stop());
      window.clearTimeout(limite.current);
      gravador.current = null;
      if (cancelado.current) {
        definirEstado('parado');
        return;
      }
      definirEstado('transcrevendo');
      const r = await transcreverAudio(new Blob(partes, { type: g.mimeType }), privado());
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

  function parar() {
    if (nativo.current) {
      window.clearTimeout(limite.current);
      nativo.current.send(JSON.stringify({ parar: true }));
      definirEstado('transcrevendo');
      return;
    }
    if (gravador.current?.state === 'recording') gravador.current.stop();
  }
  const cancelar = () => {
    cancelado.current = true;
    if (nativo.current) {
      const ws = nativo.current;
      nativo.current = null;
      window.clearTimeout(limite.current);
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ cancelar: true }));
      ws.close();
      definirEstado('parado');
      return;
    }
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
