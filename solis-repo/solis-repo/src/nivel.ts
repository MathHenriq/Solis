import { useEffect, useState } from 'react';
import tokens from '../docs/solis-tokens.json';

/** O nível do microfone pro brilho do símbolo — Camada 3 da assinatura
 *  (docs/SOLIS_SIGNATURE.md): enquanto o Solis ouve, o brilho acompanha a voz.
 *
 *  Medido aqui, no navegador, por um AnalyserNode — nunca pelo Whisper, que
 *  responde segundos depois e deixaria o brilho atrasado. Quem abre o
 *  microfone (voz.ts, apertar pra falar; escuta.ts, depois da palavra "Solis")
 *  liga a fonte com `definirFonte` e desliga quando para de ouvir.
 *
 *  O laço escreve opacity e transform direto nos elementos registrados, sem
 *  passar pelo React: são as duas propriedades que o compositor anima sozinho
 *  (PERFORMANCE.md, regra 1), e nenhum render por quadro (regra 4). Ele só
 *  roda com fonte ligada E algum símbolo na tela.
 *
 *  Números em solis-tokens.json → states.glow.reativo. */

const R = tokens.states.glow.reativo;
/** dBFS (RMS da janela do analisador) que vira brilho mínimo e máximo. PROVISÓRIO. */
const PISO_DB = R.pisoDb;
const TETO_DB = R.tetoDb;
/** Peso do valor novo na média móvel: o brilho respira, não tremula. */
const PESO_NOVO = R.pesoNovo;
/** A faixa do estado listening (states.motion.listening), agora seguindo a voz. */
const OPACIDADE = R.opacity;
const ESCALA = R.scale;

/** De quanto em quanto tempo o nível vira estilo. Entre uma amostra e outra,
 *  quem anda é a transição do CSS (.solis-brilho[data-reativo]). Medido
 *  gravando, 6 s de fala contínua: ~300 recálculos de estilo e ~33 ms de main
 *  thread por segundo — contra ~9 ms do brilho por keyframe —, e nada quando
 *  não está ouvindo. Escrever a cada quadro não custava mais (a transição é
 *  que pesa, e a Web Animations API deu o mesmo), mas o passo deixa o silêncio
 *  de graça: só mudança visível (1% de opacidade) é escrita. */
export const PASSO_MS = R.passoMs;

let fonte: AnalyserNode | null = null;
const alvos = new Set<HTMLElement | SVGElement>();
const ouvintes = new Set<(ligado: boolean) => void>();
let relogio: number | undefined;
let suave = 0;
let escrito = '';

/** Um AnalyserNode no tamanho certo pro laço, ligado a uma fonte de áudio.
 *  A janela (2048 amostras, ~43 ms a 48 kHz) é maior que o passo seria se
 *  fosse por quadro: amostrando a ~12 por segundo, uma janela curta pegaria
 *  instantes soltos da voz em vez da energia dela. */
export function criarAnalisador(contexto: AudioContext, origem: AudioNode): AnalyserNode {
  const a = contexto.createAnalyser();
  a.fftSize = 2048;
  origem.connect(a);
  return a;
}

export function definirFonte(a: AnalyserNode | null) {
  if (a === fonte) return;
  fonte = a;
  suave = 0;
  ouvintes.forEach((f) => f(!!a));
  girar();
}

/** Se há uma voz sendo ouvida agora — o símbolo troca de estado com isto. */
export function useNivelLigado(): boolean {
  const [ligado, definirLigado] = useState(() => !!fonte);
  useEffect(() => {
    ouvintes.add(definirLigado);
    definirLigado(!!fonte);
    return () => {
      ouvintes.delete(definirLigado);
    };
  }, []);
  return ligado;
}

/** O elemento passa a ter opacity e transform guiados pelo nível. */
export function registrarAlvo(el: HTMLElement | SVGElement): () => void {
  alvos.add(el);
  escrito = '';
  girar();
  return () => {
    alvos.delete(el);
    el.style.opacity = '';
    el.style.transform = '';
  };
}

/** Quem quer o nível além dos elementos desta janela: no app Tauri, a janela
 *  da chamada (a ilha por cima de tudo) é outra página, e recebe o nível por
 *  evento (tauri.ts). */
const ouvintesNivel = new Set<(opacidade: string, transform: string) => void>();

export function aoNivel(f: (opacidade: string, transform: string) => void): () => void {
  ouvintesNivel.add(f);
  girar();
  return () => {
    ouvintesNivel.delete(f);
  };
}

/** A outra ponta: escreve nos elementos desta janela um nível medido em outra. */
export function escreverNivel(opacidade: string, transform: string) {
  alvos.forEach((el) => {
    el.style.opacity = opacidade;
    el.style.transform = transform;
  });
}

function girar() {
  if (relogio !== undefined || !fonte || (!alvos.size && !ouvintesNivel.size)) return;
  const reduzido = window.matchMedia('(prefers-reduced-motion: reduce)');
  let dados = new Float32Array(2048);
  relogio = window.setInterval(() => {
    if (!fonte || (!alvos.size && !ouvintesNivel.size)) {
      window.clearInterval(relogio);
      relogio = undefined;
      return;
    }
    if (dados.length !== fonte.fftSize) dados = new Float32Array(fonte.fftSize);
    fonte.getFloatTimeDomainData(dados);
    let soma = 0;
    for (let i = 0; i < dados.length; i++) soma += dados[i] * dados[i];
    const db = 10 * Math.log10(soma / dados.length + 1e-12);
    const alvo = Math.min(1, Math.max(0, (db - PISO_DB) / (TETO_DB - PISO_DB)));
    suave = suave * (1 - PESO_NOVO) + alvo * PESO_NOVO;
    // Duas casas: mudança menor que 1% de opacidade não é vista, e não
    // escrever é o que deixa o silêncio de graça.
    const opacidade = (OPACIDADE[0] + (OPACIDADE[1] - OPACIDADE[0]) * suave).toFixed(2);
    // Movimento reduzido: o nível continua dito pela intensidade, sem escala.
    const escala = reduzido.matches ? 'none' : `scale(${(ESCALA[0] + (ESCALA[1] - ESCALA[0]) * suave).toFixed(3)})`;
    if (opacidade + escala === escrito) return;
    escrito = opacidade + escala;
    escreverNivel(opacidade, escala);
    ouvintesNivel.forEach((f) => f(opacidade, escala));
  }, PASSO_MS);
}
