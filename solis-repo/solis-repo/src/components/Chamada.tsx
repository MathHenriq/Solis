import { useEffect, useState } from 'react';
import { SolisEstado, type EstadoSolis } from './SolisEstado';

/** O Solis aparecendo quando é chamado: uma ilha preta no topo da tela.
 *  PROVISÓRIO: desenho próprio, aguardando aprovação pelos prints. Pedido do
 *  Matheus (10/11/2026): a lógica da ilha do iPhone — uma cápsula que desce do
 *  alto e muda de forma com mola, conforme o que está acontecendo. O desenho é
 *  do Solis (símbolo, brilho reativo, textos). Números e porquês em
 *  layout.chamada.
 *
 *  - `ouvindo`: aberta, o símbolo no meio, o brilho seguindo a voz;
 *  - `pensando`: pílula fina — o símbolo pequeno e a frase ouvida;
 *  - `respondendo`: larga — o símbolo pequeno e o começo da resposta;
 *  - `saindo`: volta a pílula pequena e sobe pra dentro da borda.
 *
 *  Hoje aparece no topo do app web. No app Tauri é o conteúdo da janela
 *  transparente que fica por cima de tudo (docs/PLANO.md, bloco 1). */

export type FaseChamada = 'ouvindo' | 'pensando' | 'respondendo' | 'saindo';

const ESTADO: Record<FaseChamada, EstadoSolis> = {
  ouvindo: 'listening',
  pensando: 'thinking',
  respondendo: 'responding',
  saindo: 'responding',
};

/** O começo da resposta, sem a marcação do markdown. */
function plano(texto: string) {
  return texto.replace(/[*_`#>]+/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/\s+/g, ' ').trim();
}

export function Chamada({
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
  // Nasce pequena e escondida acima da borda; no quadro seguinte toma a forma
  // da fase, e a transição com mola faz o resto.
  const [entrando, definirEntrando] = useState(true);
  useEffect(() => {
    let q = requestAnimationFrame(() => {
      q = requestAnimationFrame(() => definirEntrando(false));
    });
    return () => cancelAnimationFrame(q);
  }, []);

  return (
    <div className="solis-ilha-faixa pointer-events-none" data-sidebar={comSidebar || undefined}>
      <div
        className="solis-ilha"
        data-fase={fase}
        data-entrando={entrando || undefined}
        role="status"
        aria-live="polite"
        aria-label={fase === 'ouvindo' ? 'Solis ouvindo' : fase === 'pensando' ? 'Solis pensando' : 'Solis respondendo'}
      >
        {fase === 'ouvindo' && (
          <div key="ouvindo" className="solis-ilha-conteudo solis-ilha-aberta">
            <SolisEstado estado="listening" reativo halo="avatar" style={{ width: 'var(--ch-simbolo)' }} />
            <span className="solis-ilha-dica">Pode falar</span>
          </div>
        )}
        {fase === 'pensando' && (
          <div key="pensando" className="solis-ilha-conteudo solis-ilha-linha">
            <SolisEstado estado={ESTADO.pensando} halo="avatar" className="shrink-0" style={{ width: 'var(--ch-simbolo-p)' }} />
            <span className="solis-ilha-frase">{legenda ?? 'Pensando…'}</span>
          </div>
        )}
        {fase === 'respondendo' && (
          <div key="respondendo" className="solis-ilha-conteudo solis-ilha-resposta">
            <SolisEstado estado={ESTADO.respondendo} halo="avatar" className="shrink-0" style={{ width: 'var(--ch-simbolo-p)' }} />
            <p className="solis-ilha-texto">{resposta ? plano(resposta) : legenda}</p>
          </div>
        )}
      </div>
    </div>
  );
}
