import { Icone } from './icons';

/** O cadeado da caixa de escrever (26/11/2026, decisão do Matheus pra voz do
 *  celular): a próxima mensagem é privada. A fala é transcrita só no Solis (sem
 *  o Whisper da Groq), a mensagem é guardada selada e respondida só pelo modelo
 *  local, e o que ela ensinar vira memória privada. Desliga sozinho depois de
 *  enviar. Sem ele, o privado continua valendo pelas palavras ("isso é privado...").
 *
 *  O desenho é o do botão Pesquisa (o chip em accent com o nome quando ligado).
 *  PROVISÓRIO: o visual é refeito no fim. */
export function BotaoCadeado({
  ligado,
  aoTrocar,
  tamanho = 20,
  interativo = true,
}: {
  ligado: boolean;
  aoTrocar?: (ligado: boolean) => void;
  tamanho?: number;
  interativo?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={interativo ? () => aoTrocar?.(!ligado) : undefined}
      aria-pressed={interativo ? ligado : undefined}
      aria-label={interativo ? 'Privado' : undefined}
      aria-hidden={!interativo}
      tabIndex={interativo ? undefined : -1}
      title="Privado: a fala e a mensagem ficam no Solis. Transcrita aqui e respondida só pelo modelo local; nada vai pra nuvem."
      className={`flex items-center justify-center shrink-0 ${ligado ? 'text-accent' : 'text-text-secondary hover:text-text-primary'}`}
      style={{
        height: 'var(--mac-alvo)',
        minWidth: 'var(--mac-alvo)',
        padding: ligado ? '0 12px 0 10px' : 0,
        gap: 6,
        borderRadius: 999,
        fontSize: 'var(--et-dobra-texto)',
        background: ligado ? 'color-mix(in srgb, var(--accent) var(--et-chip-fundo), transparent)' : undefined,
        border: ligado ? '1px solid color-mix(in srgb, var(--accent) var(--et-chip-borda), transparent)' : '1px solid transparent',
      }}
    >
      <Icone nome="cadeado" tamanho={tamanho} />
      {ligado && 'Privado'}
    </button>
  );
}
