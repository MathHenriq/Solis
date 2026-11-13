import { useEffect, useState } from 'react';
import { abrirArquivo, lerArtefato } from '../servidor';
import { Icone } from './icons';

/** O artefato aberto ao lado da conversa: a página (.html) ou a imagem (.svg)
 *  que o Claude criou, rodando de verdade — como o painel de artefatos do
 *  Claude. Num iframe isolado (sandbox sem allow-same-origin): o artefato roda
 *  o JavaScript dele, mas não enxerga o Solis, o servidor nem os dados.
 *
 *  Aprovado pelo Matheus em 13/11/2026 — desenho próprio, base no painel de artefatos do
 *  Claude: uma coluna à direita da conversa, separada pela linha da tela
 *  (--divider), com o cabeçalho de ações em texto (layout.thread._artifact no
 *  solis-tokens.json). */

const nome = (c: string) => c.split(/[\\/]/).pop() ?? c;

export function PainelArtefato({ caminho, versao, aoFechar }: { caminho: string; versao: number; aoFechar: () => void }) {
  const [doc, definirDoc] = useState<string | null | undefined>(undefined);
  const [recarga, definirRecarga] = useState(0);

  useEffect(() => {
    let vivo = true;
    definirDoc(undefined);
    void lerArtefato(caminho).then((r) => {
      if (!vivo) return;
      if (!r) return definirDoc(null);
      // Um .svg vira uma página com ele no meio, no fundo claro (como uma imagem).
      definirDoc(
        r.tipo === 'svg'
          ? `<!doctype html><html><body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#fff">${r.texto}</body></html>`
          : r.texto,
      );
    });
    return () => {
      vivo = false;
    };
  }, [caminho, versao, recarga]);

  const acao = 'text-text-secondary hover:text-text-primary hover:underline shrink-0';
  return (
    <aside
      aria-label={`Artefato: ${nome(caminho)}`}
      className="painel-artefato relative flex flex-col shrink-0 border-l border-divider bg-canvas"
      style={{ width: 'var(--art-largura)', zIndex: 1 }}
    >
      <div
        className="flex items-center border-b border-divider shrink-0"
        style={{ height: 'var(--art-cabecalho)', padding: '0 var(--art-px)', gap: 16 }}
      >
        <Icone nome="documento" tamanho={16} className="text-text-secondary shrink-0" />
        <span className="text-text-primary truncate min-w-0 flex-1" title={caminho} style={{ fontSize: 'var(--et-texto)' }}>
          {nome(caminho)}
        </span>
        <button type="button" className={acao} style={{ fontSize: 'var(--et-dobra-texto)' }} onClick={() => definirRecarga((n) => n + 1)}>
          Atualizar
        </button>
        <button type="button" className={acao} style={{ fontSize: 'var(--et-dobra-texto)' }} onClick={() => void abrirArquivo(caminho)}>
          Abrir no navegador
        </button>
        <button
          type="button"
          aria-label="Fechar o artefato"
          title="Fechar"
          onClick={aoFechar}
          className="text-text-secondary hover:text-text-primary shrink-0 flex items-center justify-center"
          style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', marginRight: -8 }}
        >
          <Icone nome="adicionar" tamanho={18} style={{ transform: 'rotate(45deg)' }} />
        </button>
      </div>
      <div className="flex-1 min-h-0 relative">
        {doc === undefined && (
          <div className="text-text-secondary" style={{ padding: 'var(--art-px)', fontSize: 'var(--et-dobra-texto)' }}>
            Abrindo…
          </div>
        )}
        {doc === null && (
          <div className="text-[var(--erro)]" style={{ padding: 'var(--art-px)', fontSize: 'var(--et-dobra-texto)' }}>
            Não consegui abrir este artefato: ele saiu da pasta ou o servidor não respondeu.
          </div>
        )}
        {doc && (
          <iframe
            key={`${versao}-${recarga}`}
            title={nome(caminho)}
            srcDoc={doc}
            // Roda o script dele, abre link em outra janela, mas não é da
            // mesma origem do Solis: não lê nada daqui.
            sandbox="allow-scripts allow-popups allow-forms allow-modals"
            className="absolute inset-0 w-full h-full"
            style={{ border: 0, background: '#fff' }}
          />
        )}
      </div>
    </aside>
  );
}
