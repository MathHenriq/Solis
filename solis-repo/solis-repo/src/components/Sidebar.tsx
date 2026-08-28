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
      {/* Logo — o símbolo herda a cor do texto porque o SVG usa currentColor.
          A largura vem do token, e todo o resto do bloco (folga e wordmark) é
          proporcional a ela: mexer no token reescala o bloco inteiro sem tocar em
          mais nada. Ver solis-tokens.json → layout.sidebar._blocoDoLogo. */}
      <div className="flex flex-col items-center" style={{ paddingTop: 87 }}>
        <SolisSimbolo
          className="text-text-primary opacity-90"
          style={{
            width: 'var(--sidebar-logo)',
            height: 'auto',
            // Deslocamento óptico medido na referência: o símbolo não fica no
            // centro geométrico da coluna, fica um pouco à esquerda. Proporcional
            // à largura pra não virar um valor solto quando o logo mudar.
            marginLeft: 'calc(var(--sidebar-logo) * -0.0727)',
          }}
        />
        {/* Wordmark em DM Sans 500 — a fonte escolhida na folha de candidatas. O
            system-ui que estava aqui era substituto e saía pequeno: cap de 8px
            contra os 10,3px medidos na referência, e 30% mais estreito.

            O tamanho sai da PROPORÇÃO com o símbolo, não de um px absoluto: na
            referência o cap do wordmark é 14,5% da largura do símbolo, e é isso
            que mantém o bloco coerente com o símbolo no tamanho que o Matheus
            escolheu. O paddingLeft compensa o letter-spacing, que o CSS aplica
            também depois da última letra e descentraria o bloco. */}
        <span
          className="font-wordmark text-text-primary"
          style={{
            marginTop: 'calc(var(--sidebar-logo) * 0.145)',
            fontSize: 'calc(var(--sidebar-logo) * 0.200)',
            letterSpacing: 'var(--wordmark-tracking)',
            paddingLeft: 'var(--wordmark-tracking)',
            lineHeight: 1,
          }}
        >
          SOLIS
        </span>
      </div>

      {/* O primeiro item da nav fica a 225px do topo da janela. Este respiro é o
          que sobra depois do bloco do logo, então ele é CALCULADO a partir de
          --sidebar-logo: 87 de padding + 57,37% (altura do símbolo) + 14,5%
          (folga) + 20% (caixa do wordmark). Assim redimensionar o logo não
          empurra a navegação. */}
      <ul style={{ marginTop: 'calc(225px - 87px - var(--sidebar-logo) * 0.9187)' }}>
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
                  <Icone nome={item.icone} tamanho="var(--sidebar-icon)" />
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
