import { useEffect, useRef, useState } from 'react';
import type { FaseChamada } from './components/Chamada';
import type { EstadoEscuta } from './escuta';
import { aoMudarFala } from './fala';

/** As fases da chamada (components/Chamada.tsx), a partir do que já existe:
 *
 *  - a escuta ouviu "Solis" (estado 'ouvindo') → `ouvindo`;
 *  - o pedido foi transcrito e enviado (`enviado`) → `pensando`, com a frase de
 *    legenda;
 *  - a resposta começou a chegar, ou o Solis está falando → `respondendo`;
 *  - acabou (sem resposta chegando e sem fala), ou não ouviu nada → `saindo`,
 *    e some depois do tempo da saída (layout.chamada.exitMs). */

const SAIDA_MS = 520; // a saída da ilha: forma 260 ms + subir 300 ms depois de 160 (index.css)

/** Só em desenvolvimento: `?chamada=pensando&legenda=...` fixa uma fase, pra
 *  fotografar a animação sem microfone, Whisper nem modelo. */
function forcada(): { fase: FaseChamada; legenda?: string; resposta?: string } | null {
  if (!import.meta.env.DEV) return null;
  const q = new URLSearchParams(window.location.search);
  const f = q.get('chamada');
  return f && ['ouvindo', 'pensando', 'respondendo', 'saindo'].includes(f)
    ? { fase: f as FaseChamada, legenda: q.get('legenda') ?? undefined, resposta: q.get('resposta') ?? undefined }
    : null;
}

export function useChamada(escuta: EstadoEscuta, respondendo: boolean, comTexto: boolean) {
  const [teste] = useState(forcada);
  const [fase, definirFase] = useState<FaseChamada | null>(teste?.fase ?? null);
  const [legenda, definirLegenda] = useState<string | undefined>(teste?.legenda);
  const [falando, definirFalando] = useState(false);
  const faseAtual = useRef(fase);
  faseAtual.current = fase;

  useEffect(() => aoMudarFala(definirFalando), []);

  const [respostaTeste, definirRespostaTeste] = useState(teste?.resposta);

  // Só em desenvolvimento: trocar a fase pela página (`__faseChamada`), ou
  // ensaiar uma chamada inteira (`__ensaioChamada`) — pra fotografar a ilha, e
  // no app Tauri pra vê-la por cima das outras janelas sem microfone nem modelo.
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const w = window as unknown as {
      __faseChamada?: (f: FaseChamada | null) => void;
      __ensaioChamada?: (legenda: string, resposta: string) => void;
    };
    w.__faseChamada = definirFase;
    w.__ensaioChamada = (frase, resposta) => {
      definirLegenda(undefined);
      definirRespostaTeste(undefined);
      definirFase('ouvindo');
      window.setTimeout(() => {
        definirLegenda(frase);
        definirFase('pensando');
      }, 2500);
      window.setTimeout(() => {
        definirRespostaTeste(resposta);
        definirFase('respondendo');
      }, 4500);
      window.setTimeout(() => definirFase('saindo'), 8500);
      window.setTimeout(() => definirFase(null), 8500 + SAIDA_MS);
    };
  }, []);

  // A palavra foi ouvida.
  useEffect(() => {
    if (teste) return;
    if (escuta === 'ouvindo') {
      definirLegenda(undefined);
      definirFase('ouvindo');
    } else if (faseAtual.current === 'ouvindo') {
      // Voltou a esperar sem pedido (não ouviu nada, ou a conexão caiu).
      definirFase('saindo');
    }
  }, [escuta]);

  // Pensando → respondendo → saindo, pelo que a conversa e a fala dizem.
  useEffect(() => {
    const f = faseAtual.current;
    if (teste || (f !== 'pensando' && f !== 'respondendo')) return;
    if (falando || (respondendo && comTexto)) definirFase('respondendo');
    else if (!respondendo && !falando) definirFase('saindo');
  }, [respondendo, comTexto, falando]);

  useEffect(() => {
    if (fase !== 'saindo' || teste) return;
    const t = window.setTimeout(() => definirFase(null), SAIDA_MS);
    return () => window.clearTimeout(t);
  }, [fase]);

  /** O pedido ouvido foi enviado: a frase vira a legenda. */
  const enviado = (texto: string) => {
    definirLegenda(texto);
    definirFase('pensando');
  };

  return { fase, legenda, enviado, resposta: respostaTeste };
}
