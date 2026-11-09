import type { CSSProperties } from 'react';
import { useNivelLigado } from '../nivel';
import { SolisEstado } from './SolisEstado';
import { SolisSimbolo } from './SolisSimbolo';

/** O símbolo do logo (Sidebar e barra do topo). Parado, é o SolisSimbolo de
 *  sempre. Enquanto o Solis ouve (microfone ou palavra "Solis"), ganha a camada
 *  de brilho seguindo a voz — Camada 3 da assinatura. Desenho próprio,
 *  aprovado pelo Matheus pelos prints em 09/11/2026
 *  (design/brilho-voz-validacao.png; states.glow.reativo).
 *
 *  A caixa de fora é a mesma nos dois estados (bloco, na largura do token), e a
 *  arte nítida tem o mesmo viewBox: trocar de um pro outro não mexe 1px do
 *  layout. O halo é o do avatar (states.glow.avatar), que o SolisEstado
 *  reescala pela largura real. */
export function SimboloDoLogo({ className = '', style }: { className?: string; style?: CSSProperties }) {
  const ouvindo = useNivelLigado();
  return (
    <div className={className} style={style}>
      {ouvindo ? (
        <SolisEstado reativo halo="avatar" className="[&_.solis-arte]:text-current" />
      ) : (
        <SolisSimbolo style={{ display: 'block', width: '100%', height: 'auto' }} />
      )}
    </div>
  );
}
