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
const CHAVE_RAPIDA = 'solis.escuta.rapida';
const PAUSA_MAX_MS = 90_000;
/** Depois de um aparelho de som entrar ou sair, quanto a escuta espera, com o
 *  microfone solto, antes de abrir de novo no aparelho padrão. */
const TROCA_DE_APARELHO_MS = 2_000;

export function escutaLigada(): boolean {
  try {
    return localStorage.getItem(CHAVE) === '1';
  } catch {
    return false;
  }
}

/** Escuta rápida (Configurações → Voz): o Whisper que confere o "Solis" fica na
 *  placa de vídeo enquanto a escuta estiver ligada — 453 MB com internet (o
 *  pequeno; o pedido vai pra Groq, backend/solis/transcricao.py), 1,2 GB sem (o
 *  turbo) —, e a primeira chamada responde na hora. Desligada, ele sai depois de
 *  10 min parado e a primeira chamada depois disso espera ele carregar. Escolha
 *  do Matheus: a opção é dele. Ligada por padrão. */
export function escutaRapida(): boolean {
  try {
    return localStorage.getItem(CHAVE_RAPIDA) !== '0';
  } catch {
    return true;
  }
}

export function definirEscutaRapida(rapida: boolean) {
  try {
    localStorage.setItem(CHAVE_RAPIDA, rapida ? '1' : '0');
  } catch {
    /* sem armazenamento: vale só nesta sessão */
  }
  window.dispatchEvent(new Event('solis-escuta'));
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

/** `suspensa`: desligada por enquanto (o modo Conversa, com o microfone dele). */
export function useEscuta(aoTexto: (texto: string) => void, suspensa = false) {
  const [ligada, definirLigada] = useState(escutaLigada);
  const [rapida, definirRapida] = useState(escutaRapida);
  const [estado, definirEstado] = useState<EstadoEscuta>('desligada');
  const [erro, definirErro] = useState<string | null>(null);
  const aoTextoAtual = useRef(aoTexto);
  aoTextoAtual.current = aoTexto;

  useEffect(() => {
    const atualizar = () => {
      definirLigada(escutaLigada());
      definirRapida(escutaRapida());
    };
    window.addEventListener('solis-escuta', atualizar);
    return () => window.removeEventListener('solis-escuta', atualizar);
  }, []);

  useEffect(() => {
    if (!ligada || suspensa) {
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
    let tetoDaPausa: number | undefined;
    // `seguir`: a fala acabou numa pergunta — o servidor já abre o pedido,
    // sem esperar o "Solis" (backend/solis/ativacao.py, Escuta.seguir).
    const pausar = (falando: boolean, seguir = false) => {
      pausada = falando;
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(seguir ? { pausa: false, seguir: true } : { pausa: falando }));
    };
    const pararDeOuvirFala = aoMudarFala((falando, pergunta) => {
      pausar(falando, pergunta);
      // Trava de segurança (16/11/2026: a escuta ficou pausada pra sempre
      // depois de uma resposta falada): nenhuma fala do Solis dura isso, então
      // uma pausa maior é um "parei" que se perdeu — a escuta volta sozinha.
      window.clearTimeout(tetoDaPausa);
      if (falando) {
        tetoDaPausa = window.setTimeout(() => {
          console.warn('escuta: pausada há mais de 90 s; voltando a ouvir');
          pausar(false);
        }, PAUSA_MAX_MS);
      }
    });

    // O microfone (e o áudio a 16 kHz) só fica aberto enquanto o servidor
    // está de fato escutando: abre no "pronta" e fecha no erro ou na queda.
    // Antes abria primeiro e não fechava no erro — com o modelo do Whisper
    // faltando, o microfone ficava aberto o app inteiro, à toa, e o som do PC
    // ficava estranho (relato do Matheus, 13/11/2026).
    /** `tentativa` > 0: reabrindo depois de uma troca de aparelho. No meio da
     *  troca o Windows pode ainda não ter microfone padrão — tenta de novo
     *  algumas vezes antes de dar erro. */
    let abrindo = false;
    let reabrir = false;
    async function abrirMicrofone(tentativa = 0) {
      if (fluxo || fim || abrindo) return;
      abrindo = true;
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
        // O aparelho sumiu (o fone USB saiu): o microfone parou de mandar som.
        f.getAudioTracks().forEach((t) => t.addEventListener('ended', () => fluxo === f && trocouAparelho()));
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
        if (tentativa > 0 && tentativa < 4 && !fim) {
          trocaDeAparelho = window.setTimeout(() => {
            trocaDeAparelho = undefined;
            void abrirMicrofone(tentativa + 1);
          }, TROCA_DE_APARELHO_MS);
          return;
        }
        definirErro('Sem acesso ao microfone. Libere no navegador.');
        definirEstado('erro');
      } finally {
        abrindo = false;
        // O aparelho trocou enquanto abria: o que abriu pode ser o de antes.
        if (reabrir) {
          reabrir = false;
          trocouAparelho();
        }
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

    // Um aparelho de som entrou, saiu ou virou o padrão (o fone USB ligado ou
    // tirado). Antes a escuta não seguia a troca: ficava no microfone de quando
    // abriu (medido em 18/11/2026: com o fone USB já ligado e padrão, a única
    // sessão de microfone do Solis no Windows era a do notebook), e, se ele
    // sumisse, ficava calada sem avisar. No mesmo dia, com o Solis aberto, o áudio do
    // Discord não saía enquanto o Matheus ligava e tirava o fone, e voltou
    // quando ele fechou o Solis (relato dele; a causa exata não deu pra
    // reproduzir). Agora a escuta solta o microfone e o som na hora, espera a
    // troca assentar e abre de novo no aparelho padrão.
    let trocaDeAparelho: number | undefined;
    function trocouAparelho() {
      if (abrindo) {
        reabrir = true;
        return;
      }
      if (!fluxo && trocaDeAparelho === undefined) return; // fechado: abre no padrão quando for abrir
      fecharMicrofone();
      window.clearTimeout(trocaDeAparelho);
      trocaDeAparelho = window.setTimeout(() => {
        trocaDeAparelho = undefined;
        void abrirMicrofone(1);
      }, TROCA_DE_APARELHO_MS);
    }
    navigator.mediaDevices.addEventListener('devicechange', trocouAparelho);

    function conectar(tentativa = 0) {
      if (fim) return;
      ws = new WebSocket(urlEscuta(rapida));
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
      window.clearTimeout(tetoDaPausa);
      window.clearTimeout(trocaDeAparelho);
      navigator.mediaDevices.removeEventListener('devicechange', trocouAparelho);
      pararDeOuvirFala();
      window.clearTimeout(espera);
      ws?.close();
      fecharMicrofone();
    };
    // Trocar a escuta rápida reconecta: o servidor decide se segura o Whisper na conexão.
  }, [ligada, rapida, suspensa]);

  return { estado, erro, ligada };
}
