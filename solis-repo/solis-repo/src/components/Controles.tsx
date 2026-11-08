import type { ButtonHTMLAttributes } from 'react';

/** Botões e interruptor usados em mais de uma tela (Memória, Configurações).
 *  Medidas em layout.memoria.acoes e layout.configuracoes. */

/** Botão pequeno de ação: Salvar (destaque), Esquecer (perigo), Cancelar (texto). */
export function Botao({
  tipo = 'texto',
  ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & { tipo?: 'destaque' | 'perigo' | 'texto' }) {
  const cor = {
    destaque: 'bg-accent text-canvas',
    perigo: 'text-[var(--erro)] bg-[color-mix(in_srgb,var(--erro)_14%,transparent)]',
    texto: 'text-text-secondary hover:text-text-primary',
  }[tipo];
  return (
    <button
      type="button"
      {...resto}
      className={`${cor} disabled:opacity-50`}
      style={{
        height: 'var(--mac-botao-h)',
        padding: '0 var(--mac-botao-px)',
        borderRadius: 'var(--mac-botao-raio)',
        fontSize: 'var(--mac-botao-texto)',
      }}
    />
  );
}

export function Interruptor({
  ligado,
  rotulo,
  aoTrocar,
}: {
  ligado: boolean;
  rotulo: string;
  /** Sem ele, o interruptor é só leitura (o modelo local, que nunca desliga;
   *  um cérebro por API sem chave, que não tem como ligar). */
  aoTrocar?: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={ligado}
      aria-label={rotulo}
      aria-disabled={!aoTrocar || undefined}
      onClick={() => aoTrocar?.(!ligado)}
      className={`shrink-0 flex items-center ${ligado ? 'bg-accent' : 'bg-divider'}`}
      style={{
        width: 'var(--cfg-sw-l)',
        height: 'var(--cfg-sw-h)',
        borderRadius: 999,
        padding: 4,
        justifyContent: ligado ? 'flex-end' : 'flex-start',
        transition: 'background-color 160ms var(--ease)',
        opacity: aoTrocar ? 1 : 0.45,
        cursor: aoTrocar ? undefined : 'default',
      }}
    >
      {/* Desligado, a bolinha não pode ser da cor do fundo: no dark ela some no
          trilho escuro (visto no print dos Cérebros). */}
      <span
        className={`block ${ligado ? 'bg-canvas' : 'bg-text-secondary'}`}
        style={{
          width: 'calc(var(--cfg-sw-h) - 8px)',
          height: 'calc(var(--cfg-sw-h) - 8px)',
          borderRadius: 999,
        }}
      />
    </button>
  );
}
