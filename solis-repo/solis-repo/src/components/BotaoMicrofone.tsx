import type { EstadoVoz } from '../voz';
import { Icone } from './icons';

/** O microfone das caixas de conversa. Parado, o cinza de sempre; ouvindo, o
 *  accent pulsando (só opacidade — docs/PERFORMANCE.md); transcrevendo, apagado
 *  e sem clique.
 *
 *  PROVISÓRIO: os estados de ouvir e transcrever são desenho próprio, sem
 *  referência — a Camada 3 da assinatura (o glow reagindo ao áudio) vem depois. */
export function BotaoMicrofone({
  estado,
  aoClicar,
  tamanho,
  interativo = true,
}: {
  estado: EstadoVoz;
  aoClicar?: () => void;
  tamanho: number;
  interativo?: boolean;
}) {
  const ouvindo = estado === 'ouvindo';
  return (
    <button
      type="button"
      onClick={interativo ? aoClicar : undefined}
      className={`p-sm ${ouvindo ? 'text-accent solis-ouvindo' : 'text-text-secondary hover:text-text-primary'}`}
      style={{ opacity: estado === 'transcrevendo' ? 0.4 : undefined, cursor: estado === 'transcrevendo' ? 'progress' : undefined }}
      aria-label={interativo ? (ouvindo ? 'Parar de ouvir' : 'Falar') : undefined}
      aria-pressed={interativo ? ouvindo : undefined}
      aria-busy={estado === 'transcrevendo' || undefined}
      aria-hidden={!interativo}
      tabIndex={interativo ? undefined : -1}
    >
      <Icone nome="microfone" tamanho={tamanho} />
    </button>
  );
}
