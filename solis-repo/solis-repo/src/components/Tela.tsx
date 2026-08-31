import type { ReactNode } from 'react';

/** Moldura comum das telas de lista.
 *
 *  Título, subtítulo e uma ação opcional no canto direito — o padrão que se
 *  repete em Memória, Modelos locais, Ferramentas, Tarefas, Agenda,
 *  Conhecimento e Configurações. As medidas são as já validadas na Memória
 *  (`layout.memoria` no solis-tokens.json); as referências das outras telas
 *  confirmam o mesmo padrão, e ter um componente só é o que garante que ele
 *  continue igual quando uma delas mudar.
 *
 *  `bg-canvas` e não fundo transparente: estas listas sangram até a base da
 *  janela, e sobre a foto do horizonte o texto perderia contraste. O Horizonte
 *  segue montado no shell — a Camada 1 não remonta —, só não aparece por baixo.
 *  A Conversa é a exceção: lá o conteúdo para em 66% da altura e a cena aparece. */
export function Tela({
  titulo,
  subtitulo,
  acao,
  children,
  rolagem = true,
}: {
  titulo: string;
  subtitulo?: string;
  acao?: ReactNode;
  children: ReactNode;
  rolagem?: boolean;
}) {
  return (
    <main className="relative flex-1 flex flex-col overflow-hidden bg-canvas" style={{ zIndex: 1 }}>
      <div
        className="shrink-0 flex items-start justify-between"
        style={{
          paddingLeft: 'var(--mem-pad-l)',
          paddingRight: 'var(--mem-pad-r)',
          paddingTop: 'var(--mem-titulo-top)',
        }}
      >
        <div>
          <h1 className="font-display text-text-primary leading-none" style={{ fontSize: 'var(--mem-titulo)' }}>
            {titulo}
          </h1>
          {subtitulo && (
            <p
              className="text-text-secondary"
              style={{ fontSize: 'var(--mem-contagem)', marginTop: 'var(--mem-contagem-gap)' }}
            >
              {subtitulo}
            </p>
          )}
        </div>
        {acao}
      </div>

      <div
        className={rolagem ? 'flex-1 overflow-y-auto' : 'flex-1 overflow-hidden'}
        style={{
          marginTop: 'var(--mem-lista-gap)',
          paddingLeft: 'var(--mem-pad-l)',
          paddingRight: 'var(--mem-pad-r)',
        }}
      >
        {children}
      </div>
    </main>
  );
}

/** Linha de lista. Divisória embaixo, véu no hover, e o conteúdo livre.
 *
 *  O véu vem de `--mem-hover`, que é branco no tema escuro e preto nos claros:
 *  o mesmo componente serve os 3 temas porque lê a variável em vez de um hex. */
export function LinhaLista({
  children,
  destacada = false,
  hover = true,
}: {
  children: ReactNode;
  destacada?: boolean;
  hover?: boolean;
}) {
  return (
    <div
      className={`solis-linha border-b border-divider ${hover ? 'hover:bg-[var(--mem-hover)]' : ''}`}
      style={{
        paddingTop: 'var(--mem-item-pad-y)',
        paddingBottom: 'var(--mem-item-pad-y)',
        background: destacada ? 'var(--mem-hover)' : undefined,
      }}
    >
      {children}
    </div>
  );
}

/** Botão de contorno fino — "Baixar", "Adicionar fonte", "Hoje". */
export function BotaoContorno({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-sm border border-divider rounded-md text-text-primary shrink-0"
      style={{ height: 'var(--cfg-sw-l)', paddingLeft: 20, paddingRight: 20, fontSize: 'var(--cfg-rotulo)' }}
    >
      {children}
    </button>
  );
}
