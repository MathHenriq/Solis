import { useEffect, useState } from 'react';
import type { FaseChamada } from './Chamada';
import { SolisEstado, type EstadoSolis } from './SolisEstado';

/** O visual da voz dentro do app (IDEIAS.md): a conversa escurece e o símbolo
 *  do Solis aparece no meio, mostrando o estado REAL — não é enfeite.
 *  Desenho próprio, aprovado pelo Matheus pelos prints (16/11/2026,
 *  design/esfera-validacao.png). Números e porquês em layout.esfera.
 *
 *  É o símbolo com os estados já aprovados (SolisEstado, states.glow), a 190px
 *  — a largura em que o halo "folha" foi medido contra as referências da marca.
 *  A primeira versão, um sol redondo, foi recusada pelo Matheus (16/11/2026):
 *  "quero o Solis".
 *
 *  Decisão do Matheus (16/11/2026): com a janela do Solis na frente, a esfera;
 *  com ela atrás, a ilha (Chamada.tsx) por cima das outras janelas. As fases
 *  são as mesmas da ilha (chamada.ts):
 *
 *  - `ouvindo`: listening, com o brilho seguindo o microfone (nivel.ts, o
 *    mesmo do logo);
 *  - `pensando`: thinking, e embaixo vai o que ele ouviu;
 *  - `respondendo`: responding, e embaixo vai o começo da resposta;
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

const ESTADO: Record<FaseChamada, EstadoSolis> = {
  ouvindo: 'listening',
  pensando: 'thinking',
  respondendo: 'responding',
  saindo: 'responding',
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

  // Ouvindo, a legenda só existe no modo Conversa (o que ele está dizendo); no Pedido, vem vazia.
  const texto = fase === 'respondendo' ? resposta : fase === 'saindo' ? undefined : legenda;
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
          <SolisEstado estado={ESTADO[fase]} reativo={fase === 'ouvindo'} style={{ width: 'var(--es-simbolo)' }} />
        </div>
        <p className="solis-esfera-estado">{ROTULO[fase]}</p>
        <p className="solis-esfera-legenda">{legendaPlana}</p>
      </div>
    </div>
  );
}
