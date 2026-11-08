import { useEffect, useState, type ReactNode } from 'react';
import { listarConversas, type ResumoConversa } from '../servidor';
import { Icone } from './icons';

/** A lista de conversas no padrão do Claude: "Nova conversa", a busca e os
 *  "Recentes", em linhas sem caixa e sem borda, dentro da barra lateral.
 *  PROVISÓRIO — sem imagem de referência; medidas em layout.recentes.
 *
 *  Substitui o painel da referência 19 (uma segunda coluna, com divisória
 *  própria e botão e busca em caixas), que o Matheus achou pesado. Serve aos
 *  dois modos de navegação: dentro da Sidebar, e numa gaveta no modo barra de
 *  ícones (GavetaConversas). */

export type PropsLista = {
  /** A conversa aberta; null numa conversa nova, ainda sem mensagem. */
  aberta: number | null;
  /** Muda quando a lista ficou velha (uma mensagem nova, um título novo). */
  versao: number;
  aoAbrir: (id: number) => void;
  aoNova: () => void;
};

/** Uma linha: a caixa a --rc-recuo das bordas, o texto na coluna dos ícones
 *  da navegação. Hover só com fundo, como no Claude. */
const linha = 'relative flex items-center w-full text-left text-text-primary';
const estiloLinha = {
  height: 'var(--rc-linha-h)',
  borderRadius: 'var(--rc-raio)',
  padding: '0 var(--rc-px)',
  fontSize: 'var(--rc-texto)',
};

/** Coluna dos ícones: o texto da Nova conversa e o da busca começam juntos. */
function ColunaIcone({ children }: { children: ReactNode }) {
  return (
    <span
      className="shrink-0 flex items-center justify-center"
      style={{ width: 'var(--rc-mais)', marginRight: 'var(--rc-icone-gap)' }}
    >
      {children}
    </span>
  );
}

export function ListaConversas({ aberta, versao, aoAbrir, aoNova }: PropsLista) {
  const [busca, definirBusca] = useState('');
  const [conversas, definirConversas] = useState<ResumoConversa[]>([]);

  useEffect(() => {
    let vivo = true;
    // Espera a pessoa parar de digitar: sem isso cada letra ia ao banco.
    const espera = setTimeout(() => listarConversas(busca).then((c) => vivo && definirConversas(c)), busca ? 200 : 0);
    return () => {
      vivo = false;
      clearTimeout(espera);
    };
  }, [busca, versao]);

  return (
    <div className="flex flex-col min-h-0 flex-1" style={{ padding: '0 var(--rc-recuo)' }}>
      <button type="button" onClick={aoNova} className={`${linha} shrink-0 hover:bg-[var(--mem-hover-forte)]`} style={estiloLinha}>
        <ColunaIcone>
          {/* O + num círculo de accent cheio, como o "Novo chat" do Claude. */}
          <span
            className="flex items-center justify-center bg-accent text-canvas"
            style={{ width: 'var(--rc-mais)', height: 'var(--rc-mais)', borderRadius: 999 }}
          >
            <Icone nome="adicionar" tamanho={12} tracoFixo="2.2" />
          </span>
        </ColunaIcone>
        Nova conversa
      </button>

      <label
        className={`${linha} shrink-0 hover:bg-[var(--mem-hover-forte)] focus-within:bg-[var(--mem-hover-forte)]`}
        style={estiloLinha}
      >
        <ColunaIcone>
          <Icone nome="buscar" tamanho="var(--rc-icone)" className="text-text-secondary" />
        </ColunaIcone>
        <input
          value={busca}
          onChange={(e) => definirBusca(e.target.value)}
          className="flex-1 min-w-0 bg-transparent outline-none text-text-primary placeholder:text-text-secondary"
          style={{ fontSize: 'var(--rc-texto)' }}
          placeholder="Buscar conversas"
          aria-label="Buscar conversas"
        />
      </label>

      <h2
        className="shrink-0 text-text-secondary flex items-end"
        style={{
          marginTop: 'var(--rc-rotulo-top)',
          height: 'var(--rc-rotulo-h)',
          paddingLeft: 'var(--rc-px)',
          paddingBottom: 6,
          fontSize: 'var(--rc-rotulo)',
        }}
      >
        {busca.trim() ? 'Resultados' : 'Recentes'}
      </h2>

      {/* A lista rola sozinha; o resto da barra fica no lugar. */}
      <ul className="min-h-0 overflow-y-auto" style={{ paddingBottom: 8 }}>
        {busca.trim() && !conversas.length && (
          <li className="text-text-secondary" style={{ ...estiloLinha, display: 'flex', alignItems: 'center' }}>
            Nenhuma com “{busca.trim()}”
          </li>
        )}
        {conversas.map((c) => {
          const ativa = c.id === aberta;
          return (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => aoAbrir(c.id)}
                aria-current={ativa ? 'true' : undefined}
                title={c.titulo}
                className={`${linha} ${ativa ? 'bg-[var(--rc-ativo)]' : 'hover:bg-[var(--mem-hover-forte)]'}`}
                style={estiloLinha}
              >
                <span className="truncate">{c.titulo}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Modo barra de ícones: não há sidebar, então a lista abre numa gaveta da
 *  esquerda, pelo botão do topo. Escolher uma conversa (ou começar uma nova)
 *  fecha a gaveta; Esc e clicar fora também. */
export function GavetaConversas({
  visivel,
  aoFechar,
  ...lista
}: PropsLista & { visivel: boolean; aoFechar: () => void }) {
  useEffect(() => {
    if (!visivel) return;
    const tecla = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', tecla);
    return () => window.removeEventListener('keydown', tecla);
  }, [visivel, aoFechar]);

  if (!visivel) return null;
  return (
    <>
      {/* Clicar fora fecha. Sem véu escuro: a gaveta é leve, como a do Claude. */}
      <div className="fixed inset-0" style={{ zIndex: 4 }} onClick={aoFechar} aria-hidden />
      <aside
        aria-label="Conversas"
        className="fixed left-0 bottom-0 flex flex-col bg-canvas border-r border-divider"
        style={{ top: 'var(--topo-h)', width: 'var(--rc-gaveta)', zIndex: 5, paddingTop: 8 }}
      >
        <ListaConversas
          {...lista}
          aoAbrir={(id) => {
            lista.aoAbrir(id);
            aoFechar();
          }}
          aoNova={() => {
            lista.aoNova();
            aoFechar();
          }}
        />
      </aside>
    </>
  );
}
