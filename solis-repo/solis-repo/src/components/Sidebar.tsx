import { ITENS_NAV } from '../nav-items';
import { Icone } from './icons';
import { SolisSimbolo } from './SolisSimbolo';

/** Sidebar compacta da Fase 2.
 *
 *  Todas as medidas vêm de docs/MEDICOES_FASE2.md, normalizadas pra janela de
 *  1440px: 200px de largura (13,9%), ícone 17px, passo 55px entre itens,
 *  rótulo 14px, indicador ativo de 3px a 12px da borda.
 *
 *  O fundo NÃO é uma superfície própria — nos 3 temas ele é o mesmo do canvas,
 *  e o que separa é a divisória de 1px. Por isso aqui não há bg. */
export function Sidebar({ ativo = 'conversa' }: { ativo?: string }) {
  return (
    <nav
      className="shrink-0 border-r border-divider flex flex-col"
      style={{ width: 'var(--sidebar-width)' }}
      aria-label="Navegação principal"
    >
      {/* Logo — símbolo 71px de largura a 82px do topo, wordmark logo abaixo.
          O símbolo herda a cor do texto porque o SVG usa currentColor. */}
      <div className="flex flex-col items-center" style={{ paddingTop: 87 }}>
        <SolisSimbolo largura={71} className="text-text-primary opacity-90" style={{ marginLeft: -8 }} />
        <span
          className="text-text-primary"
          style={{ marginTop: 12, fontSize: 11, letterSpacing: '0.34em', paddingLeft: '0.34em' }}
        >
          SOLIS
        </span>
      </div>

      {/* Primeiro item a 231px do topo da janela; o logo ocupa até ~143. */}
      <ul style={{ marginTop: 58 }}>
        {ITENS_NAV.map((item) => {
          const ehAtivo = item.id === ativo;
          return (
            <li key={item.id}>
              <a
                href={item.rota}
                aria-current={ehAtivo ? 'page' : undefined}
                className={`relative flex items-center ${
                  ehAtivo ? 'text-accent' : 'text-text-primary'
                }`}
                style={{ height: 'var(--sidebar-pitch)' }}
              >
                {ehAtivo && (
                  <span
                    aria-hidden
                    className="absolute bg-accent"
                    style={{ left: 12, top: 14, bottom: 14, width: 3, borderRadius: 2 }}
                  />
                )}
                <span className="absolute" style={{ left: 'var(--sidebar-icon-inset)' }}>
                  <Icone nome={item.icone} />
                </span>
                <span style={{ paddingLeft: 'var(--sidebar-label-inset)', fontSize: 'var(--sidebar-label)' }}>
                  {item.rotulo}
                </span>
              </a>
            </li>
          );
        })}
      </ul>

      {/* Perfil: divisória a 38px da base da janela, bloco abaixo dela. */}
      <div className="mt-auto border-t border-divider flex items-center" style={{ height: 76, paddingLeft: 19 }}>
        <div
          className="rounded-pill shrink-0 bg-divider"
          style={{ width: 32, height: 32 }}
          aria-hidden
        />
        <div className="ml-md leading-tight">
          <div className="text-text-primary" style={{ fontSize: 13 }}>Matheus</div>
          <div className="text-text-secondary flex items-center gap-xs" style={{ fontSize: 11 }}>
            <span aria-hidden style={{ width: 6, height: 6, borderRadius: 99, background: '#8FBF6D' }} />
            Online
          </div>
        </div>
        <span className="ml-auto mr-lg text-text-secondary">
          <Icone nome="chevron" tamanho={14} />
        </span>
      </div>
    </nav>
  );
}
