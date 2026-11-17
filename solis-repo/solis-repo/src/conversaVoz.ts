import { useEffect, useRef, useState } from 'react';
import { criarAnalisador, definirFonte } from './nivel';
import { urlConversaVoz } from './servidor';

/** O modo Conversa (IDEIAS.md → Voz): bate-papo por voz em tempo real pelo
 *  Gemini Live (backend/solis/conversa_voz.py). Decisões do Matheus (17/11/2026):
 *  entra falando ("Solis, vamos conversar") ou por um botão; o que for dito fica
 *  salvo na conversa; acaba sozinho com 30 s de silêncio (ou Esc).
 *
 *  Aqui: o microfone vai pro servidor (16 kHz, com o cancelamento de eco ligado —
 *  a voz dele sai das caixas e não pode voltar pelo microfone), a voz dele toca
 *  pedaço por pedaço numa fila do Web Audio (24 kHz) e para na hora quando ele é
 *  interrompido. A escuta da palavra "Solis" fica desligada enquanto a conversa
 *  dura (App.tsx: useEscuta suspensa) — só um microfone aberto, e nada de acordar
 *  com o "Solis" dito no meio da conversa. */

export type FaseConversa = 'conectando' | 'ouvindo' | 'falando';

// Se há conversa agora, pra quem não mora no App (o botão nas caixas de conversa).
let ativaAgora = false;
const ouvintesAtiva = new Set<(ativa: boolean) => void>();

function marcarAtiva(ativa: boolean) {
  if (ativa === ativaAgora) return;
  ativaAgora = ativa;
  ouvintesAtiva.forEach((o) => o(ativa));
}

/** O botão: entra no modo Conversa, ou sai se já estiver nele (App.tsx ouve). */
export function alternarConversa() {
  window.dispatchEvent(new Event('solis-conversa'));
}

export function useConversaAtiva(): boolean {
  const [ativa, definir] = useState(ativaAgora);
  useEffect(() => {
    ouvintesAtiva.add(definir);
    definir(ativaAgora);
    return () => {
      ouvintesAtiva.delete(definir);
    };
  }, []);
  return ativa;
}

export function useConversaVoz(aoTurno: (conversa: number) => void) {
  const [fase, definirFase] = useState<FaseConversa | null>(null);
  const [ouviu, definirOuviu] = useState('');
  const [disse, definirDisse] = useState('');
  const [erro, definirErro] = useState<string | null>(null);
  const aoTurnoAtual = useRef(aoTurno);
  aoTurnoAtual.current = aoTurno;
  const encerrarRef = useRef<() => void>(() => {});

  function iniciar(conversa: number | null) {
    if (fase) return;
    definirErro(null);
    definirOuviu('');
    definirDisse('');
    definirFase('conectando');
    let ws: WebSocket | null = new WebSocket(urlConversaVoz(conversa));
    ws.binaryType = 'arraybuffer';
    let fluxo: MediaStream | null = null;
    let entrada: AudioContext | null = null;
    const saida = new AudioContext({ sampleRate: 24000 });
    let proximo = 0;
    const tocando = new Set<AudioBufferSourceNode>();
    let idConversa = conversa;
    let acabou = false;

    const pararDeTocar = () => {
      tocando.forEach((s) => {
        try {
          s.stop();
        } catch {
          /* já parou */
        }
      });
      tocando.clear();
      proximo = 0;
    };

    const fechar = () => {
      if (acabou) return;
      acabou = true;
      definirFonte(null);
      fluxo?.getTracks().forEach((t) => t.stop());
      void entrada?.close();
      pararDeTocar();
      void saida.close();
      try {
        ws?.close();
      } catch {
        /* já fechou */
      }
      ws = null;
      definirFase(null);
      window.removeEventListener('keydown', tecla);
    };

    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') encerrar();
    };
    window.addEventListener('keydown', tecla);

    const encerrar = () => {
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ fim: true }));
      fechar();
    };
    encerrarRef.current = encerrar;

    async function abrirMicrofone() {
      try {
        fluxo = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        if (acabou) {
          fluxo.getTracks().forEach((t) => t.stop());
          return;
        }
        entrada = new AudioContext({ sampleRate: 16000 });
        await entrada.audioWorklet.addModule('/escuta-processador.js');
        const no = new AudioWorkletNode(entrada, 'escuta-processador');
        no.port.onmessage = (e) => {
          if (ws?.readyState === WebSocket.OPEN) ws.send(e.data as ArrayBuffer);
        };
        const origem = entrada.createMediaStreamSource(fluxo);
        origem.connect(no);
        // O brilho do símbolo segue a voz dele (o mesmo nível da escuta).
        definirFonte(criarAnalisador(entrada, origem));
        definirFase('ouvindo');
      } catch {
        definirErro('Sem acesso ao microfone. Libere no navegador.');
        encerrar();
      }
    }

    function tocar(dados: ArrayBuffer) {
      const pcm = new Int16Array(dados);
      if (!pcm.length || saida.state === 'closed') return;
      const buffer = saida.createBuffer(1, pcm.length, 24000);
      const canal = buffer.getChannelData(0);
      for (let i = 0; i < pcm.length; i++) canal[i] = pcm[i] / 0x8000;
      const fonte = saida.createBufferSource();
      fonte.buffer = buffer;
      fonte.connect(saida.destination);
      const quando = Math.max(saida.currentTime + 0.02, proximo);
      fonte.start(quando);
      proximo = quando + buffer.duration;
      tocando.add(fonte);
      definirFase('falando');
      fonte.onended = () => {
        tocando.delete(fonte);
        if (!tocando.size && !acabou) definirFase('ouvindo');
      };
    }

    ws.onmessage = (e) => {
      if (typeof e.data !== 'string') {
        tocar(e.data as ArrayBuffer);
        return;
      }
      const msg = JSON.parse(e.data) as { tipo: string; texto?: string; conversa?: number; motivo?: string };
      if (msg.tipo === 'pronta') {
        idConversa = msg.conversa ?? idConversa;
        void saida.resume();
        void abrirMicrofone();
      } else if (msg.tipo === 'ouviu') {
        definirOuviu(msg.texto ?? '');
        definirDisse('');
      } else if (msg.tipo === 'disse') {
        definirDisse(msg.texto ?? '');
      } else if (msg.tipo === 'interrompido') {
        pararDeTocar();
        definirFase('ouvindo');
      } else if (msg.tipo === 'turno') {
        // A troca fechou (e foi salva): a legenda volta limpa pra próxima fala.
        definirOuviu('');
        if (idConversa !== null) aoTurnoAtual.current(idConversa);
      } else if (msg.tipo === 'erro') {
        definirErro(msg.motivo ?? 'o modo conversa não abriu');
      } else if (msg.tipo === 'fim') {
        fechar();
      }
    };
    ws.onclose = () => fechar();
  }

  // Saindo da tela com a conversa aberta: encerra (o microfone não fica aberto à toa).
  useEffect(() => () => encerrarRef.current(), []);
  useEffect(() => marcarAtiva(fase !== null), [fase]);

  return { fase, ouviu, disse, erro, iniciar, encerrar: () => encerrarRef.current() };
}

/** "Solis, vamos conversar" (e parecidos): entra no modo Conversa em vez de virar mensagem. */
export function pedeConversa(texto: string): boolean {
  return /\b(vamos|bora|quero)\s+(conversar|bater\s+(um\s+)?papo)\b|\bmodo\s+conversa\b/i.test(texto);
}
