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
      className={`${cor} whitespace-nowrap shrink-0 disabled:opacity-50`}
      style={{
        height: 'var(--mac-botao-h)',
        padding: '0 var(--mac-botao-px)',
        borderRadius: 'var(--mac-botao-raio)',
        fontSize: 'var(--mac-botao-texto)',
      }}
    />
  );
}

/** Opções que se excluem no mesmo eixo (a Navegação, o modelo da voz): uma
 *  peça só, não botões soltos. No visual novo (layout.visualNovo.config), como
 *  no Claude: 38 de altura, a borda da caixa de escrever e a escolhida com o
 *  véu, sem o dourado. */
export function Segmentado<T extends string>({
  opcoes,
  valor,
  aoTrocar,
  rotulo,
}: {
  opcoes: readonly (readonly [T, string])[];
  valor: T;
  aoTrocar: (v: T) => void;
  rotulo: string;
}) {
  return (
    <div
      className="flex shrink-0"
      style={{
        height: 'var(--vn-sb-nova-h)',
        padding: 'var(--vn-cfg-seg-pad)',
        gap: 'var(--vn-cfg-seg-pad)',
        borderRadius: 'var(--vn-sb-nova-raio)',
        border: '1px solid var(--vn-caixa-borda)',
      }}
      role="group"
      aria-label={rotulo}
    >
      {opcoes.map(([id, nome]) => (
        <button
          key={id}
          type="button"
          onClick={() => aoTrocar(id)}
          aria-pressed={valor === id}
          className={`whitespace-nowrap ${valor === id ? 'text-text-primary' : 'text-[var(--vn-inativo)] hover:text-text-primary'}`}
          style={{
            padding: '0 var(--vn-cfg-seg-px)',
            borderRadius: 'calc(var(--vn-sb-nova-raio) - var(--vn-cfg-seg-pad))',
            fontSize: 'var(--vn-sb-rotulo)',
            fontWeight: valor === id ? 500 : undefined,
            background: valor === id ? 'var(--vn-ativo)' : undefined,
          }}
        >
          {nome}
        </button>
      ))}
    </div>
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
