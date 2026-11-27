import { ITENS_NAV, type ItemNav } from '../nav-items';
import { Icone } from './icons';
import { ListaConversas, type PropsLista } from './ListaConversas';
import { SimboloDoLogo } from './SimboloDoLogo';

/** A barra lateral do visual novo.
 *
 *  PROVISÓRIO — desenho próprio (27/11/2026), a direção B que o Matheus escolheu
 *  no canvas, com o Claude como base: o logo pequeno à esquerda, "Nova conversa"
 *  numa caixa de borda logo embaixo, os itens em linhas de 36 sem indicador (o
 *  ativo só ganha o véu), as conversas recentes, e Configurações e o perfil no
 *  pé. Medidas em layout.visualNovo.sidebar; a largura (264) é a do Claude.
 *
 *  A lista de itens continua vindo de nav-items (a fonte única, regra 4 do
 *  CLAUDE.md): Configurações só muda de lugar, pro pé da barra.
 *
 *  O fundo NÃO é uma superfície própria — nos 3 temas ele é o mesmo do canvas,
 *  e o que separa é a divisória de 1px. */
export function Sidebar({
  ativo = 'conversa',
  aoTrocar,
  conversas,
}: {
  ativo?: string;
  aoTrocar?: (id: string) => void;
  /** A lista de conversas, que vive aqui dentro como no Claude. */
  conversas?: PropsLista;
}) {
  const principais = ITENS_NAV.filter((i) => i.id !== 'configuracoes');
  const configuracoes = ITENS_NAV.find((i) => i.id === 'configuracoes');
  return (
    <nav
      className="shrink-0 min-h-0 overflow-hidden border-r border-divider flex flex-col"
      style={{ width: 'var(--sidebar-width)', padding: 'var(--vn-sb-topo) var(--vn-sb-px) 8px' }}
      aria-label="Navegação principal"
    >
      {/* O logo: o símbolo (que ganha o brilho da voz enquanto o Solis ouve) e o
          SOLIS lado a lado, pequenos, como o logo do Claude na barra dele. */}
      <div className="flex items-center shrink-0" style={{ gap: 10, padding: '6px 8px 14px' }}>
        <SimboloDoLogo className="text-text-primary opacity-90" style={{ width: 'var(--vn-sb-logo)' }} />
        <span
          className="font-wordmark text-text-primary"
          style={{ fontSize: 'var(--vn-sb-marca)', letterSpacing: 'var(--vn-sb-marca-espaco)', lineHeight: 1, fontWeight: 500 }}
        >
          SOLIS
        </span>
      </div>

      {conversas && (
        <button
          type="button"
          onClick={conversas.aoNova}
          className="flex items-center shrink-0 text-text-primary hover:bg-[var(--mem-hover)]"
          style={{
            height: 'var(--vn-sb-nova-h)',
            borderRadius: 'var(--vn-sb-nova-raio)',
            border: '1px solid var(--vn-caixa-borda)',
            padding: '0 var(--vn-sb-item-px)',
            gap: 10,
            fontSize: 'var(--vn-sb-rotulo)',
            fontWeight: 500,
          }}
        >
          <Icone nome="adicionar" tamanho={18} className="text-accent" tracoFixo="2" />
          Nova conversa
        </button>
      )}

      {/* min-h-0 e overflow-y: numa janela curta a navegação rola sozinha, em vez
          de empurrar a coluna e fazer a página inteira rolar. */}
      <ul className="min-h-0 overflow-y-auto flex flex-col" style={{ marginTop: 'var(--vn-sb-nav-topo)', gap: 1 }}>
        {principais.map((item) => (
          <li key={item.id}>
            <ItemDaBarra item={item} ativo={item.id === ativo} aoTrocar={aoTrocar} />
          </li>
        ))}
      </ul>

      {/* As conversas ocupam o que sobra até o pé e rolam sozinhas; numa janela
          curta, quem encolhe primeiro são elas, até sobrar a busca. A lista tem
          o recuo dela (o da gaveta do modo ícones): aqui ele sai pela margem,
          pra que o texto caia na coluna dos ícones da barra. */}
      {conversas ? (
        <div
          className="flex flex-col overflow-hidden"
          style={{
            flex: '1 1 0',
            minHeight: 'calc(var(--rc-linha-h) * 2)',
            marginTop: 'var(--rc-topo)',
            marginInline: 'calc(-1 * var(--vn-sb-px))',
          }}
        >
          <ListaConversas {...conversas} semNova />
        </div>
      ) : (
        <div className="flex-1" />
      )}

      {configuracoes && (
        <div className="shrink-0" style={{ marginTop: 6 }}>
          <ItemDaBarra item={configuracoes} ativo={configuracoes.id === ativo} aoTrocar={aoTrocar} />
        </div>
      )}

      {/* O perfil: a inicial num círculo e o nome, sem caixa. */}
      <div className="shrink-0 flex items-center" style={{ gap: 10, padding: '8px var(--vn-sb-item-px)' }}>
        <div
          aria-hidden
          className="shrink-0 flex items-center justify-center text-accent"
          style={{
            width: 'var(--vn-sb-avatar)',
            height: 'var(--vn-sb-avatar)',
            borderRadius: 999,
            background: 'color-mix(in srgb, var(--accent) 16%, var(--canvas))',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          M
        </div>
        <span className="text-text-primary truncate" style={{ fontSize: 'var(--vn-sb-perfil)' }}>
          Matheus
        </span>
      </div>
    </nav>
  );
}

/** Um item da navegação. Continua sendo <a> com href: o item é navegação de
 *  verdade, e trocar por <button> tiraria "abrir em nova aba" e o papel de link
 *  das tecnologias assistivas. O preventDefault existe só porque a troca é
 *  estado local e não navegação de documento. */
function ItemDaBarra({ item, ativo, aoTrocar }: { item: ItemNav; ativo: boolean; aoTrocar?: (id: string) => void }) {
  return (
    <a
      href={item.rota}
      aria-current={ativo ? 'page' : undefined}
      onClick={(e) => {
        if (!aoTrocar) return;
        e.preventDefault();
        aoTrocar(item.id);
      }}
      className={`flex items-center ${ativo ? 'text-text-primary' : 'text-[var(--vn-inativo)] hover:text-text-primary hover:bg-[var(--mem-hover)]'}`}
      style={{
        height: 'var(--vn-sb-item-h)',
        borderRadius: 'var(--vn-sb-item-raio)',
        padding: '0 var(--vn-sb-item-px)',
        gap: 'var(--vn-sb-icone-gap)',
        fontSize: 'var(--vn-sb-rotulo)',
        background: ativo ? 'var(--vn-ativo)' : undefined,
      }}
    >
      <Icone nome={item.icone} tamanho="var(--vn-sb-icone)" className="shrink-0" />
      <span className="truncate">{item.rotulo}</span>
    </a>
  );
}
