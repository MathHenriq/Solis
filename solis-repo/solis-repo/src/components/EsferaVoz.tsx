import { useEffect, useRef, useState } from 'react';
import { registrarAlvo } from '../nivel';
import type { FaseChamada } from './Chamada';

/** O visual da voz dentro do app (IDEIAS.md): a conversa escurece e o sol do
 *  Solis aparece no meio, mostrando o estado REAL — não é enfeite.
 *  PROVISÓRIO: desenho próprio, aguardando aprovação pelos prints. Números e
 *  porquês em layout.esfera.
 *
 *  Decisão do Matheus (16/11/2026): com a janela do Solis na frente, a esfera;
 *  com ela atrás, a ilha (Chamada.tsx) por cima das outras janelas. As fases
 *  são as mesmas da ilha (chamada.ts):
 *
 *  - `ouvindo`: o halo segue o nível do microfone (nivel.ts, o mesmo do
 *    símbolo do logo) — pulsa em intensidade, como o brilho aprovado;
 *  - `pensando`: o arco do símbolo gira em volta do sol, e embaixo vai o que
 *    ele ouviu;
 *  - `respondendo`: o sol pulsa no ritmo de quem fala (states.motion.responding),
 *    e embaixo vai o começo da resposta;
 *  - `saindo`: some.
 *
 *  Tudo que anima em laço é opacity e transform (PERFORMANCE.md, regra 1). O
 *  overlay não pega o clique: dura segundos, e não pode prender a tela. */

const ROTULO: Record<FaseChamada, string> = {
  ouvindo: 'Ouvindo',
  pensando: 'Pensando',
  respondendo: 'Falando',
  saindo: '',
};

function plano(texto: string) {
  return texto.replace(/[*_`#>]+/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/\s+/g, ' ').trim();
}

export function EsferaVoz({
  fase,
  legenda,
  resposta,
  comSidebar = false,
}: {
  fase: FaseChamada;
  legenda?: string;
  resposta?: string;
  comSidebar?: boolean;
}) {
  // Nasce apagada; no quadro seguinte entra, e a transição do CSS faz o resto.
  const [entrando, definirEntrando] = useState(true);
  useEffect(() => {
    let q = requestAnimationFrame(() => {
      q = requestAnimationFrame(() => definirEntrando(false));
    });
    return () => cancelAnimationFrame(q);
  }, []);

  // Ouvindo: o halo é um alvo do nível do microfone (opacity e transform
  // escritos direto, sem render por quadro).
  const halo = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (fase !== 'ouvindo' || !halo.current) return;
    return registrarAlvo(halo.current);
  }, [fase]);

  const texto = fase === 'pensando' ? legenda : fase === 'respondendo' ? resposta : undefined;
  const legendaPlana = texto ? plano(texto) : '';

  return (
    <div
      className="solis-esfera-fundo pointer-events-none font-sans"
      data-fase={fase}
      data-entrando={entrando || undefined}
      data-sidebar={comSidebar || undefined}
      role="status"
      aria-live="polite"
    >
      <div className="solis-esfera-area" data-sidebar={comSidebar || undefined}>
        <div className="solis-esfera" data-fase={fase}>
          <div ref={halo} className="solis-esfera-halo" data-reativo={fase === 'ouvindo' || undefined} />
          <div className="solis-esfera-anel" />
          <div className="solis-esfera-disco" />
        </div>
        <p className="solis-esfera-estado">{ROTULO[fase]}</p>
        <p className="solis-esfera-legenda">{legendaPlana}</p>
      </div>
    </div>
  );
}
