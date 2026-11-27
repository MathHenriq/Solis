import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Icone } from './icons';

/** A moldura das telas de lista no visual novo (layout.visualNovo.tela).
 *
 *  PROVISÓRIO — desenho próprio (27/11/2026): nasceu na Memória, aprovada pelos
 *  prints, e as telas passaram pra cá uma por vez (CLAUDE.md), até Configurações;
 *  a moldura antiga saiu. Do Tela.tsx fica só o EstadoVazio. A tela fica na coluna
 *  da conversa (--vn-coluna), no centro, como a lista de conversas do Claude.
 *
 *  `bg-canvas`, e não fundo transparente: a lista sangra até a base da janela,
 *  e sobre a foto do horizonte o texto perderia contraste. */
export function TelaColuna({
  titulo,
  subtitulo,
  acao,
  topo,
  children,
  estado,
  sobre,
}: {
  titulo: string;
  /** A contagem embaixo do título. Vazio ('') ainda ocupa o lugar dela. */
  subtitulo?: string;
  /** Um botão no canto direito do título. */
  acao?: ReactNode;
  /** O que fica parado embaixo da contagem, acima da lista (a busca da Memória).
   *  Com ele a lista começa mais perto (--vn-tela-lista-gap); sem ele, a
   *  distância medida da contagem à primeira linha (--vn-tela-lista-gap-contagem). */
  topo?: ReactNode;
  children?: ReactNode;
  /** Um <EstadoVazio>: se posiciona pela altura da janela, fora da lista. */
  estado?: ReactNode;
  /** O que flutua sobre a tela (o aviso com Desfazer). */
  sobre?: ReactNode;
}) {
  // A calha que a rolagem da lista reserva de cada lado (12 com a barra do app,
  // 0 com a que flutua, a do celular): o cabeçalho anda o mesmo tanto, pra o
  // título e a lista ficarem na mesma coluna em qualquer largura. Medida, e não
  // copiada com overflow no cabeçalho: lá ela cortaria o menu do "Adicionar
  // fonte", que desce por cima da lista.
  const lista = useRef<HTMLDivElement>(null);
  const [calha, definirCalha] = useState(0);
  useLayoutEffect(() => {
    const el = lista.current;
    if (el) definirCalha((el.offsetWidth - el.clientWidth) / 2);
  }, []);

  return (
    <main className="vn-tela relative flex-1 flex flex-col overflow-hidden bg-canvas" style={{ zIndex: 1 }}>
      <div
        className="shrink-0"
        style={{
          paddingInline: `calc(var(--vn-tela-px) + ${calha}px)`,
          paddingTop: 'var(--mem-titulo-top)',
        }}
      >
        <div style={{ maxWidth: 'var(--vn-coluna)', marginInline: 'auto' }}>
          {/* A ação fica ao lado só do título e conta como da altura dele (o
              botão de 38 passa 4 pra baixo, dentro da folga da contagem): a
              contagem embaixo usa a largura toda e não quebra no celular. Se não
              couber ao lado do título (a Agenda, no celular), desce pra uma linha
              própria, sem cobrir a contagem. */}
          <div className="flex flex-wrap items-start justify-between" style={{ columnGap: 'var(--space-lg, 24px)', rowGap: 12 }}>
            {/* O título é a única serifada do cabeçalho, como a saudação da Conversa. */}
            <h1 className="font-display text-text-primary leading-none min-w-0" style={{ fontSize: 'var(--mem-titulo)' }}>
              {titulo}
            </h1>
            {acao && (
              <div className="shrink-0" style={{ marginBottom: 'calc(var(--mem-titulo) - var(--vn-sb-nova-h))' }}>
                {acao}
              </div>
            )}
          </div>
          {subtitulo !== undefined && (
            <p
              className="text-text-secondary"
              style={{ fontSize: 'var(--mem-contagem)', marginTop: 'var(--vn-tela-contagem-gap)' }}
            >
              {subtitulo}
            </p>
          )}
          {topo}
        </div>
      </div>

      {/* A lista rola sozinha e sangra até a base da janela: o corte da última
          linha é o que diz que há mais coisa abaixo, por isso sem padding
          embaixo. A calha dos dois lados mantém a coluna no eixo do título. */}
      <div
        ref={lista}
        className="flex-1 overflow-y-auto"
        style={{
          marginTop: topo ? 'var(--vn-tela-lista-gap)' : 'var(--vn-tela-lista-gap-contagem)',
          paddingInline: 'var(--vn-tela-px)',
          scrollbarGutter: 'stable both-edges',
        }}
      >
        <div style={{ maxWidth: 'var(--vn-coluna)', marginInline: 'auto' }}>{children}</div>
      </div>

      {estado}
      {sobre}
    </main>
  );
}

/** A busca do cabeçalho (Memória, Conhecimento): o fundo e a borda da caixa de
 *  escrever, sem a sombra (não flutua). Vai no `topo` da TelaColuna. */
export function BuscaColuna({
  valor,
  aoMudar,
  placeholder,
  rotulo,
}: {
  valor: string;
  aoMudar: (v: string) => void;
  placeholder: string;
  rotulo: string;
}) {
  return (
    <div
      className="flex items-center"
      style={{
        marginTop: 'var(--vn-tela-busca-top)',
        height: 'var(--mem-busca-h)',
        borderRadius: 'var(--mem-busca-raio)',
        background: 'var(--vn-caixa-fundo)',
        border: '1px solid var(--vn-caixa-borda)',
      }}
    >
      <span
        className="text-text-secondary shrink-0 flex"
        style={{ paddingLeft: 'var(--vn-tela-busca-pl)', paddingRight: 'var(--vn-tela-busca-gap)' }}
      >
        <Icone nome="buscar" tamanho="var(--vn-tela-busca-icone)" />
      </span>
      <input
        className="flex-1 min-w-0 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
        style={{ fontSize: 'var(--mem-item-texto)', paddingRight: 'var(--vn-tela-busca-pl)' }}
        placeholder={placeholder}
        aria-label={rotulo}
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
      />
    </div>
  );
}

/** Uma linha da lista: a divisória embaixo, na largura da coluna, e no hover um
 *  bloco arredondado que passa 16 dela (as divisórias de cima e de baixo somem;
 *  regras .vn-linha no index.css). Com `aoClicar` a linha inteira é o alvo. */
export function LinhaColuna({
  children,
  aoClicar,
  rotulo,
  fixa = false,
}: {
  children: ReactNode;
  aoClicar?: () => void;
  /** Nome acessível da ação de `aoClicar`. */
  rotulo?: string;
  /** Linha de ajuste (um interruptor, campos): sem o véu do hover, que diria
   *  que a linha inteira é clicável. */
  fixa?: boolean;
}) {
  return (
    <div
      role={aoClicar ? 'button' : undefined}
      tabIndex={aoClicar ? 0 : undefined}
      aria-label={rotulo}
      onClick={aoClicar}
      onKeyDown={
        aoClicar &&
        ((e) => {
          if (e.target !== e.currentTarget || (e.key !== 'Enter' && e.key !== ' ')) return;
          e.preventDefault();
          aoClicar();
        })
      }
      className={`vn-linha group outline-none ${fixa ? 'vn-linha-fixa' : ''} ${aoClicar ? 'cursor-pointer' : ''}`}
    >
      <div className="vn-linha-corpo">{children}</div>
    </div>
  );
}

/** O título de uma seção da lista ("Disponíveis para baixar"): serifado, como na
 *  referência, no tamanho do nome das linhas. */
export function SecaoColuna({ children }: { children: ReactNode }) {
  return (
    <h2
      className="font-display text-text-primary leading-none"
      style={{
        fontSize: 'var(--vn-tela-secao)',
        marginTop: 'var(--vn-tela-secao-top)',
        marginBottom: 'var(--vn-tela-secao-base)',
      }}
    >
      {children}
    </h2>
  );
}

/** O rótulo de um grupo da lista (HOJE, ESTA SEMANA): caixa alta pequena, no
 *  tom secundário, como o "Recentes" da barra. O primeiro fica mais perto da
 *  contagem (medido na 15-tarefas, layout.visualNovo.tela.groupFirstTop). */
export function GrupoColuna({ children, primeiro = false }: { children: ReactNode; primeiro?: boolean }) {
  return (
    <h2
      className="text-text-secondary uppercase"
      style={{
        fontSize: 'var(--mem-origem)',
        letterSpacing: '0.08em',
        marginTop: primeiro ? 'var(--vn-tela-grupo-primeiro)' : 'var(--mem-item-pad-y)',
        marginBottom: 'var(--mem-origem-top)',
      }}
    >
      {children}
    </h2>
  );
}

/** O botão de borda das linhas e do cabeçalho ("Baixar", "Adicionar fonte"): o
 *  mesmo do "Nova conversa" da barra lateral. */
export function BotaoBorda({
  children,
  onClick,
  rotulo,
  quadrado = false,
}: {
  children: ReactNode;
  onClick?: () => void;
  /** Nome acessível, quando o texto some (só o ícone, no celular). */
  rotulo?: string;
  /** Só um ícone (as setas da Agenda): 38 x 38. */
  quadrado?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        // Dentro de uma linha clicável, o botão não pode disparar a linha.
        e.stopPropagation();
        onClick?.();
      }}
      aria-label={rotulo}
      title={rotulo}
      className="flex items-center justify-center shrink-0 text-text-primary hover:bg-[var(--mem-hover-forte)]"
      style={{
        height: 'var(--vn-sb-nova-h)',
        width: quadrado ? 'var(--vn-sb-nova-h)' : undefined,
        borderRadius: 'var(--vn-sb-nova-raio)',
        border: '1px solid var(--vn-caixa-borda)',
        padding: quadrado ? 0 : '0 var(--vn-tela-botao-px)',
        gap: 8,
        fontSize: 'var(--vn-sb-rotulo)',
        fontWeight: 500,
      }}
    >
      {children}
    </button>
  );
}
