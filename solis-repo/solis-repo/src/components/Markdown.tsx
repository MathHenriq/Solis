import { useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import { Icone } from './icons';

/** A resposta do modelo em markdown, inteiro (docs/PARIDADE.md → Markdown).
 *
 *  Antes a thread tinha um leitor próprio que só sabia parágrafo, lista e
 *  negrito: bloco de código aparecia cru, com as crases e sem a indentação
 *  (visto no teste do projeto, 12/11/2026). Agora é o react-markdown, com GFM
 *  (tabela, lista numerada, tachado), quebra de linha simples mantida (como o
 *  pre-line de antes) e realce de sintaxe nos blocos.
 *
 *  O que já estava validado na thread continua igual: parágrafo com o
 *  respiro --th-par-gap, lista com o ponto no accent, código em linha no fundo
 *  --mem-hover-forte. O bloco de código e a tabela são desenho próprio,
 *  PROVISÓRIO (layout.thread.etapas._codeBlock e themes.*._code nos tokens). */

type No = { type: string; tagName?: string; value?: string; children?: No[]; properties?: Record<string, unknown> };

/** O cursor de "ainda escrevendo" vai DENTRO do último bloco de texto, no fim
 *  — fora dele cairia numa linha própria. */
function rehypeCursor() {
  return (arvore: No) => {
    let alvo: No | null = null;
    const andar = (n: No) => {
      if (n.type === 'element' && ['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'td', 'code'].includes(n.tagName ?? ''))
        alvo = n;
      n.children?.forEach(andar);
    };
    andar(arvore);
    const pai = (alvo ?? arvore) as No;
    pai.children = [
      ...(pai.children ?? []),
      { type: 'element', tagName: 'span', properties: { className: ['solis-cursor'], ariaLabel: 'Solis está respondendo' }, children: [] },
    ];
  };
}

const textoDe = (n: No | undefined): string =>
  !n ? '' : n.type === 'text' ? n.value ?? '' : (n.children ?? []).map((c) => textoDe(c)).join('');

function BlocoDeCodigo({ linguagem, codigo, children }: { linguagem: string; codigo: string; children: ReactNode }) {
  const [copiado, definirCopiado] = useState(false);
  return (
    <div
      className="overflow-hidden"
      style={{ marginTop: 'var(--th-par-gap)', borderRadius: 'var(--cod-raio)', background: 'var(--mem-hover-forte)' }}
    >
      <div
        className="flex items-center justify-between text-text-secondary"
        style={{ fontSize: 'var(--cod-cabecalho)', padding: '6px var(--cod-px) 0' }}
      >
        <span>{linguagem || 'código'}</span>
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(codigo.replace(/\n$/, ''));
              definirCopiado(true);
              setTimeout(() => definirCopiado(false), 1500);
            } catch {
              /* sem permissão de área de transferência */
            }
          }}
          className={`flex items-center ${copiado ? 'text-accent' : 'hover:text-text-primary'}`}
          style={{ gap: 4 }}
          aria-label={copiado ? 'Código copiado' : 'Copiar o código'}
        >
          <Icone nome={copiado ? 'feito' : 'copiar'} tamanho={14} />
          {copiado ? 'Copiado' : 'Copiar'}
        </button>
      </div>
      <pre
        className="font-mono overflow-x-auto text-text-primary"
        style={{ fontSize: 'var(--cod-texto)', lineHeight: 1.6, padding: '8px var(--cod-px) var(--cod-py)', margin: 0 }}
      >
        {children}
      </pre>
    </div>
  );
}

const COMPONENTES: Components = {
  p: ({ children }) => <p style={{ marginTop: 'var(--th-par-gap)' }}>{children}</p>,
  h1: ({ children }) => <p className="font-semibold" style={{ marginTop: 'var(--th-par-gap)', fontSize: '1.15em' }}>{children}</p>,
  h2: ({ children }) => <p className="font-semibold" style={{ marginTop: 'var(--th-par-gap)', fontSize: '1.08em' }}>{children}</p>,
  h3: ({ children }) => <p className="font-semibold" style={{ marginTop: 'var(--th-par-gap)' }}>{children}</p>,
  h4: ({ children }) => <p className="font-semibold" style={{ marginTop: 'var(--th-par-gap)' }}>{children}</p>,
  ul: ({ children }) => <ul className="solis-md-ul" style={{ marginTop: 'var(--th-par-gap)' }}>{children}</ul>,
  ol: ({ children, start }) => (
    <ol className="list-decimal" start={start} style={{ marginTop: 'var(--th-par-gap)', paddingLeft: '1.5em' }}>
      {children}
    </ol>
  ),
  li: ({ children }) => <li style={{ marginTop: 8 }}>{children}</li>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2">
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote
      className="text-text-secondary"
      style={{ marginTop: 'var(--th-par-gap)', borderLeft: '2px solid var(--divider)', paddingLeft: 14 }}
    >
      {children}
    </blockquote>
  ),
  hr: () => <hr className="border-divider" style={{ marginTop: 'var(--th-par-gap)' }} />,
  table: ({ children }) => (
    <div className="overflow-x-auto" style={{ marginTop: 'var(--th-par-gap)' }}>
      <table className="solis-md-tabela" style={{ borderCollapse: 'collapse', fontSize: '0.92em' }}>
        {children}
      </table>
    </div>
  ),
  pre: ({ node, children }) => {
    const codigo = (node?.children?.[0] ?? undefined) as unknown as No | undefined;
    const classes = (codigo?.properties?.className as string[] | undefined) ?? [];
    const linguagem = classes.find((c) => c.startsWith('language-'))?.slice('language-'.length) ?? '';
    return (
      <BlocoDeCodigo linguagem={linguagem} codigo={textoDe(codigo)}>
        {children}
      </BlocoDeCodigo>
    );
  },
  code: ({ className, children, node }) => {
    // Dentro de um bloco (```): sem o fundo do código em linha — o bloco já tem.
    const bloco = /language-|hljs/.test(className ?? '') || textoDe(node as unknown as No).includes('\n');
    if (bloco) return <code className={className}>{children}</code>;
    return (
      <code
        className="font-mono"
        style={{ fontSize: '0.9em', background: 'var(--mem-hover-forte)', padding: '1px 5px', borderRadius: 4 }}
      >
        {children}
      </code>
    );
  },
};

export function Markdown({ texto, escrevendo = false }: { texto: string; escrevendo?: boolean }) {
  return (
    <div className="solis-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={escrevendo ? [[rehypeHighlight, { detect: false }], rehypeCursor] : [[rehypeHighlight, { detect: false }]]}
        components={COMPONENTES}
      >
        {texto}
      </ReactMarkdown>
    </div>
  );
}
