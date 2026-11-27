import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { apagarConversa, listarConversas, renomearConversa, type ResumoConversa } from '../servidor';
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
  /** A conversa foi apagada (se era a aberta, o app vai pra uma nova). */
  aoApagada?: (id: number) => void;
  /** Sem a linha "Nova conversa": a barra lateral nova tem o botão dela no topo. */
  semNova?: boolean;
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

/** Uma conversa da lista, com o "…" no hover (Renomear, Apagar), como no
 *  Claude. Renomear vira um campo na própria linha; apagar pede confirmação ali.
 *
 *  Aprovado pelo Matheus em 15/11/2026 — desenho próprio, base na lista do Claude: o
 *  botão de 3 pontos no lugar do fim do título, o menu na caixa dos menus do
 *  Conhecimento (--kn-menu-*), a confirmação na linha em --rc-texto
 *  (layout.recentes._acoes no solis-tokens.json). */
// Duas opções de 36 + o padding da caixa: a conta de abrir pra cima.
const MENU_ALTURA = 92;

function LinhaConversa({
  c,
  ativa,
  aoAbrir,
  aoRenomeada,
  aoApagada,
}: {
  c: ResumoConversa;
  ativa: boolean;
  aoAbrir: () => void;
  aoRenomeada: (titulo: string) => void;
  aoApagada: () => void;
}) {
  const [modo, definirModo] = useState<'normal' | 'menu' | 'renomear' | 'apagar'>('normal');
  const [titulo, definirTitulo] = useState(c.titulo);
  const [aviso, definirAviso] = useState<string | null>(null);
  const caixa = useRef<HTMLLIElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  // Onde o menu abre: embaixo do botão, alinhado à direita dele (fixo na tela:
  // dentro da lista, que rola, ele era cortado).
  const [ancora, definirAncora] = useState<{ top?: number; bottom?: number; right: number } | null>(null);

  useEffect(() => {
    if (modo !== 'menu') return;
    const fora = (e: MouseEvent) =>
      !caixa.current?.contains(e.target as Node) && !menuRef.current?.contains(e.target as Node) && definirModo('normal');
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && definirModo('normal');
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc);
    };
  }, [modo]);

  const salvar = async () => {
    const novo = titulo.trim();
    if (!novo || novo === c.titulo) return definirModo('normal');
    const r = await renomearConversa(c.id, novo);
    if (r) aoRenomeada(r);
    definirModo('normal');
  };

  if (modo === 'renomear')
    return (
      <li style={{ padding: '2px 0' }}>
        <input
          autoFocus
          value={titulo}
          onChange={(e) => definirTitulo(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void salvar();
            if (e.key === 'Escape') {
              definirTitulo(c.titulo);
              definirModo('normal');
            }
          }}
          onBlur={() => void salvar()}
          aria-label="Novo nome da conversa"
          className="w-full bg-transparent outline-none text-text-primary border border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
          style={{ ...estiloLinha, height: 'calc(var(--rc-linha-h) - 4px)' }}
        />
      </li>
    );

  if (modo === 'apagar')
    return (
      <li
        className="flex items-center bg-[var(--mem-hover-forte)]"
        style={{ ...estiloLinha, gap: 10 }}
        role="group"
        aria-label={`Apagar ${c.titulo}?`}
      >
        <span className="truncate min-w-0 flex-1 text-text-secondary" title={c.titulo}>{aviso ?? 'Apagar?'}</span>
        <button
          type="button"
          className="text-[var(--erro)] hover:underline shrink-0"
          onClick={async () => {
            const r = await apagarConversa(c.id);
            if (r === true) aoApagada();
            else definirAviso(r === 'respondendo' ? 'Espere a resposta acabar' : 'Não deu agora');
          }}
        >
          Apagar
        </button>
        <button type="button" className="text-text-secondary hover:text-text-primary hover:underline shrink-0" onClick={() => {
          definirAviso(null);
          definirModo('normal');
        }}>
          Cancelar
        </button>
      </li>
    );

  return (
    <li ref={caixa} className="group relative">
      <button
        type="button"
        onClick={aoAbrir}
        aria-current={ativa ? 'true' : undefined}
        title={c.titulo}
        // Visual novo (27/11/2026): fora a aberta, o título no tom apagado da
        // barra (--vn-inativo), como no Claude; o hover acende.
        className={`${linha} ${ativa ? 'bg-[var(--rc-ativo)]' : '!text-[var(--vn-inativo)] hover:!text-text-primary hover:bg-[var(--mem-hover-forte)]'}`}
        style={{ ...estiloLinha, paddingRight: 'calc(var(--rc-px) + var(--rc-acoes))' }}
      >
        <span className="truncate">{c.titulo}</span>
      </button>
      <button
        type="button"
        aria-label={`Ações de ${c.titulo}`}
        aria-haspopup="menu"
        aria-expanded={modo === 'menu'}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          // Perto do fim da tela, abre pra cima.
          const cabe = r.bottom + 2 + MENU_ALTURA < window.innerHeight;
          definirAncora(
            cabe
              ? { top: r.bottom + 2, right: window.innerWidth - r.right }
              : { bottom: window.innerHeight - r.top + 2, right: window.innerWidth - r.right },
          );
          definirModo((m) => (m === 'menu' ? 'normal' : 'menu'));
        }}
        className={`absolute flex items-center justify-center text-text-secondary hover:text-text-primary
                    ${modo === 'menu' ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus:opacity-100'}`}
        style={{ right: 4, top: 0, height: 'var(--rc-linha-h)', width: 'var(--rc-acoes)' }}
      >
        <Icone nome="mais" tamanho={16} />
      </button>
      {modo === 'menu' && ancora && createPortal(
        <div
          ref={menuRef}
          role="menu"
          className="fixed border border-divider bg-canvas font-sans"
          style={{
            zIndex: 60,
            right: ancora.right,
            top: ancora.top,
            bottom: ancora.bottom,
            width: 180,
            padding: 'var(--kn-menu-pad)',
            borderRadius: 'var(--kn-menu-raio)',
            boxShadow: '0 8px 24px rgb(0 0 0 / 0.25)',
          }}
        >
          {[
            { rotulo: 'Renomear', fazer: () => definirModo('renomear') },
            { rotulo: 'Apagar', fazer: () => definirModo('apagar'), perigo: true },
          ].map((a) => (
            <button
              key={a.rotulo}
              type="button"
              role="menuitem"
              onClick={a.fazer}
              className={`block w-full text-left hover:bg-[var(--mem-hover)] ${a.perigo ? 'text-[var(--erro)]' : 'text-text-primary'}`}
              style={{
                padding: '8px var(--kn-menu-item-px)',
                borderRadius: 'calc(var(--kn-menu-raio) - var(--kn-menu-pad))',
                fontSize: 'var(--mac-botao-texto)',
              }}
            >
              {a.rotulo}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </li>
  );
}

export function ListaConversas({ aberta, versao, aoAbrir, aoNova, aoApagada, semNova = false }: PropsLista) {
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
      {!semNova && (
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
      )}

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
        {conversas.map((c) => (
          <LinhaConversa
            key={c.id}
            c={c}
            ativa={c.id === aberta}
            aoAbrir={() => aoAbrir(c.id)}
            aoRenomeada={(titulo) => definirConversas((l) => l.map((x) => (x.id === c.id ? { ...x, titulo } : x)))}
            aoApagada={() => {
              definirConversas((l) => l.filter((x) => x.id !== c.id));
              aoApagada?.(c.id);
            }}
          />
        ))}
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
