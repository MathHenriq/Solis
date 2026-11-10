import { useEffect, useRef } from 'react';
import { registrarAlvo } from '../nivel';
import { SolisEstado, type EstadoSolis } from './SolisEstado';

/** O Solis aparecendo quando é chamado ("Solis" ou, depois, o atalho global).
 *  PROVISÓRIO: desenho próprio, aguardando aprovação pelos prints
 *  (layout.chamada no solis-tokens.json, onde estão os números e o porquê).
 *
 *  As fases, todas só com transform e opacity (PERFORMANCE.md):
 *  - `ouvindo`: o sol nasce da linha do horizonte (a linha cresce do centro, o
 *    símbolo sobe de trás dela), os anéis saem em ondas, e o brilho e os anéis
 *    seguem a voz (src/nivel.ts — a Camada 3 aprovada);
 *  - `pensando`: as ondas param, o brilho respira devagar (thinking), e a frase
 *    ouvida fica embaixo, como legenda;
 *  - `respondendo`: o brilho acompanha a resposta (responding);
 *  - `saindo`: o sol se põe e a linha recolhe.
 *
 *  Hoje aparece por cima do app web. No app Tauri (docs/PLANO.md, bloco 1) é o
 *  conteúdo da janela pequena e transparente que fica por cima de tudo. */

export type FaseChamada = 'ouvindo' | 'pensando' | 'respondendo' | 'saindo';

const ESTADO: Record<FaseChamada, EstadoSolis> = {
  ouvindo: 'listening',
  pensando: 'thinking',
  respondendo: 'responding',
  saindo: 'responding',
};

/** Centro do sol no desenho do símbolo (viewBox 384,91 × 220,85): os anéis
 *  são semicírculos em volta dele, apoiados na mesma altura. */
const CENTRO = { x: 192.5, y: 168 };
const RAIOS = [178, 214, 250]; // layout.chamada.ringRadii

export function Chamada({ fase, legenda, comSidebar = false }: { fase: FaseChamada; legenda?: string; comSidebar?: boolean }) {
  const aneis = useRef<HTMLDivElement>(null);
  // Ouvindo, a intensidade dos anéis segue a voz, como o brilho do símbolo.
  useEffect(() => {
    if (fase === 'ouvindo' && aneis.current) return registrarAlvo(aneis.current);
  }, [fase]);

  return (
    <div
      className="solis-chamada pointer-events-none"
      data-fase={fase}
      data-sidebar={comSidebar || undefined}
      role="status"
      aria-live="polite"
    >
      <span className="sr-only">{fase === 'ouvindo' ? 'Solis ouvindo' : fase === 'pensando' ? 'Solis pensando' : ''}</span>
      <div className="solis-chamada-palco">
        {/* Cada anel numa div própria: transform num elemento de dentro de um
            SVG roda no main thread; numa div, vai pro compositor. */}
        <div ref={aneis} className="solis-chamada-aneis" aria-hidden>
          {RAIOS.map((r, i) => (
            <div key={r} className="solis-chamada-anel" style={{ animationDelay: `calc(var(--ch-onda-passo) * ${i})` }}>
              <svg viewBox="0 0 384.91 220.85">
                <path d={`M ${CENTRO.x - r} ${CENTRO.y} A ${r} ${r} 0 0 1 ${CENTRO.x + r} ${CENTRO.y}`} />
              </svg>
            </div>
          ))}
        </div>
        <div className="solis-chamada-sol">
          <SolisEstado
            estado={ESTADO[fase]}
            reativo={fase === 'ouvindo'}
            halo="avatar"
            className="[&_.solis-arte]:text-text-primary"
          />
        </div>
      </div>
      <div className="solis-chamada-horizonte" aria-hidden />
      {legenda && fase !== 'ouvindo' && <p className="solis-chamada-legenda">{legenda}</p>}
    </div>
  );
}
