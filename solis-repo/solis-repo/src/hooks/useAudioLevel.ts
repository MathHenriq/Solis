import { useCallback, useEffect, useRef, useState } from "react";

/* Camada 3 da assinatura — glow reativo ao áudio.
 *
 * ⚠️ REGRA DE ARQUITETURA: isto NÃO passa pelo pipeline do Whisper. O Whisper
 * transcreve em batch/streaming e tem latência própria; usá-lo como fonte do
 * glow deixaria a animação atrasada em relação à voz.
 *
 * O frontend captura o áudio DUAS vezes em paralelo:
 *   1. uma cópia vai pro backend Python/Whisper pra transcrição;
 *   2. outra fica só aqui, na Web Audio API, calculando amplitude em tempo real.
 * Local, sem round-trip de rede/processo, sem o delay do Whisper. Por isso o
 * hook devolve o MediaStream: quem faz a transcrição usa a mesma captura, sem
 * pedir o microfone duas vezes.
 *
 * O nível é escrito como VARIÁVEL CSS, não como state do React. Um setState por
 * frame pagaria reconciliação a ~60fps só pra mexer num brilho — exatamente o
 * que PERFORMANCE.md seção 4 manda evitar. O CSS lê --solis-audio-level e o
 * compositor resolve, porque o que anima continua sendo opacity/transform.
 */

/* Valores de solis-tokens.json → signature.audioReactive. */
const SMOOTHING_FACTOR = 0.3; // peso do valor novo na média móvel
const NOISE_FLOOR = 0.05; // abaixo disso é silêncio: ruído ambiente, ignorar
const FFT_SIZE = 256;

export type MicStatus =
  | "idle" // ainda não pediu o microfone
  | "requesting" // permissão pedida, aguardando
  | "active" // capturando
  | "denied" // usuário/SO negou
  | "unavailable"; // sem dispositivo ou API indisponível

export interface AudioLevel {
  status: MicStatus;
  /** Captura crua, pra quem for mandar pro Whisper. Nunca abrir uma segunda. */
  stream: MediaStream | null;
  start: () => Promise<void>;
  stop: () => void;
}

/** RMS de um buffer de domínio do tempo (0..1). */
function computeRMS(data: Uint8Array): number {
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    const v = (data[i] - 128) / 128; // 0..255 → -1..1
    sum += v * v;
  }
  return Math.sqrt(sum / data.length);
}

/**
 * Captura o nível do microfone enquanto `active` for true.
 *
 * `active` deve ser true só durante o estado `listening` — é a única fase em
 * que a Camada 3 existe (audioReactive.activeOnlyDuringState).
 *
 * Movimento reduzido não é tratado aqui: o hook continua entregando o nível, e
 * o CSS decide virar indicador estático. A informação nunca some, só a
 * movimentação — desligar o hook apagaria a informação junto.
 */
export function useAudioLevel(active: boolean): AudioLevel {
  const [status, setStatus] = useState<MicStatus>("idle");
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number>(0);
  const smoothedRef = useRef(0);

  const writeLevel = (value: number) => {
    document.documentElement.style.setProperty(
      "--solis-audio-level",
      value.toFixed(3),
    );
  };

  const stop = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = 0;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    void ctxRef.current?.close().catch(() => {
      /* fechar um contexto já fechado não é erro que interesse à interface */
    });
    ctxRef.current = null;

    smoothedRef.current = 0;
    // Fade pra zero em vez de corte seco: se o STT falhar no meio da fala, o
    // glow para suavemente e o estado volta pra idle (ERROR_STATES.md, item 5).
    writeLevel(0);
    setStatus((s) => (s === "denied" || s === "unavailable" ? s : "idle"));
  }, []);

  const start = useCallback(async () => {
    if (streamRef.current) return;

    if (!navigator.mediaDevices?.getUserMedia || typeof AudioContext === "undefined") {
      setStatus("unavailable");
      return;
    }

    setStatus("requesting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      // Permissão negada desliga a Camada 3 inteira pra este usuário, e só ela:
      // as Camadas 1 e 2 seguem funcionando e o símbolo fica em idle normal.
      // Quem trata o texto e o caminho de saída é a interface — ver
      // ERROR_STATES.md item 1. O campo de texto continua 100% disponível.
      setStatus("denied");
      return;
    }

    streamRef.current = stream;
    const ctx = new AudioContext();
    ctxRef.current = ctx;

    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = FFT_SIZE;
    source.connect(analyser);
    // De propósito NÃO conecta em ctx.destination: isso devolveria a voz do
    // usuário pelos alto-falantes.

    const data = new Uint8Array(analyser.frequencyBinCount);
    setStatus("active");

    const tick = () => {
      analyser.getByteTimeDomainData(data);
      const rms = computeRMS(data);

      // Piso de ruído: abaixo disso é silêncio, não sussurro.
      const gated = rms < NOISE_FLOOR ? 0 : rms;

      // Média móvel. Áudio cru é ruidoso — sem isso o glow "tremula" em vez
      // de "respirar".
      smoothedRef.current =
        smoothedRef.current * (1 - SMOOTHING_FACTOR) + gated * SMOOTHING_FACTOR;

      writeLevel(Math.min(1, smoothedRef.current));
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  useEffect(() => {
    if (active) void start();
    else stop();
    return stop;
  }, [active, start, stop]);

  return { status, stream: streamRef.current, start, stop };
}
