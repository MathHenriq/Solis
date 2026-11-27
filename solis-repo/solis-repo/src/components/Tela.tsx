import { Icone, type NomeIcone } from './icons';

/** O vazio e o erro das telas (a moldura delas é a TelaColuna, em TelaNova.tsx;
 *  a moldura antiga saiu quando a última tela passou pro visual novo, 27/11/2026).
 *
 *  Ícone + título + corpo, centralizado — o vazio e o erro de qualquer tela.
 *  Referência: referencias/telas/10-memoria-vazio.png; medidas em
 *  layout.estadoVazio no solis-tokens.json.
 *
 *  O mesmo bloco serve pra erro porque ERROR_STATES.md §6 pede isso: o erro é
 *  uma mensagem dentro do fluxo, no tom do resto, nunca um alerta. O corpo
 *  aceita quebra de linha explícita (`\n`) porque a referência quebra o texto
 *  em frases, não pela largura. */
export function EstadoVazio({ icone, titulo, corpo }: { icone: NomeIcone; titulo: string; corpo: string }) {
  return (
    <div
      className="absolute flex flex-col items-center text-center pointer-events-none"
      style={{
        left: 'var(--mem-pad-l)',
        right: 'var(--mem-pad-r)',
        top: 'var(--vazio-centro-y)',
        transform: 'translateY(-50%)',
      }}
    >
      <Icone
        nome={icone}
        tamanho="var(--vazio-icone)"
        tracoFixo="var(--vazio-traco)"
        className="text-text-secondary"
      />
      <h2
        className="font-display text-text-primary leading-none"
        style={{ fontSize: 'var(--vazio-titulo)', marginTop: 'var(--vazio-icone-gap)' }}
      >
        {titulo}
      </h2>
      <p
        className="text-text-secondary whitespace-pre-line"
        style={{
          fontSize: 'var(--vazio-corpo)',
          lineHeight: 'var(--vazio-corpo-lh)',
          marginTop: 'var(--vazio-titulo-gap)',
        }}
      >
        {corpo}
      </p>
    </div>
  );
}
