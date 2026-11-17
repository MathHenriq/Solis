import { alternarConversa, useConversaAtiva } from '../conversaVoz';
import { Icone } from './icons';

/** O modo Conversa (conversaVoz.ts) pelas caixas de conversa, ao lado do
 *  microfone — decisão do Matheus (17/11/2026): entrar falando ou por um botão.
 *  Desenho próprio com o Claude como base (o botão de voz dele, com as ondas de
 *  som), no mesmo tamanho, cor e espaço do microfone. Aprovado pelo Matheus pelos
 *  prints (17/11/2026, design/botao-conversa-validacao.png). Na conversa, o
 *  accent; clicar sai. */
export function BotaoConversa({ tamanho, interativo = true }: { tamanho: number; interativo?: boolean }) {
  const ativa = useConversaAtiva();
  return (
    <button
      type="button"
      onClick={interativo ? alternarConversa : undefined}
      className={`p-sm ${ativa ? 'text-accent' : 'text-text-secondary hover:text-text-primary'}`}
      aria-label={interativo ? (ativa ? 'Sair da conversa por voz' : 'Conversar por voz') : undefined}
      title={interativo ? (ativa ? 'Sair da conversa por voz (Esc)' : 'Conversar por voz') : undefined}
      aria-pressed={interativo ? ativa : undefined}
      aria-hidden={!interativo}
      tabIndex={interativo ? undefined : -1}
    >
      <Icone nome="ondas" tamanho={tamanho} />
    </button>
  );
}
