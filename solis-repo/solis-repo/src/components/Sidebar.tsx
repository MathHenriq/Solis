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
      <div className="flex flex-col items-center" style={{ paddingTop: 'var(--sidebar-padding-top)' }}>
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

      {/* A tinta do primeiro rótulo cai em --sidebar-nav-ink, medido na referência.
          Este respiro é o que sobra depois do bloco do logo, então ele é CALCULADO:
          padding + 91,87% de --sidebar-logo (altura do símbolo 57,37% + folga 14,5%
          + caixa do wordmark 20%), menos os 23px entre o topo da caixa do item e o
          topo da tinta do rótulo (metade da folga do passo, mais a diferença entre a
          caixa da fonte e a altura de caixa alta). Assim mexer no tamanho do logo
          não desloca a navegação. */}
      <ul
        style={{
          marginTop:
            'calc(var(--sidebar-nav-ink) - 23px - var(--sidebar-padding-top) - var(--sidebar-logo) * 0.9187)',
        }}
      >
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

      {/* Perfil. Todas as medidas vêm da referência espacial, normalizadas pela
          LARGURA da janela e com o vertical contado a partir da BASE — a referência
          tem 1020px de altura útil e o alvo tem 930, então normalizar y pelo topo
          erra o bloco inteiro. Ver solis-tokens.json → layout.sidebar._profile.

          O conteúdo fica no ALTO do bloco, não centrado: na referência sobram ~62px
          de canvas vazio abaixo do avatar. */}
      <div
        className="mt-auto border-t border-divider flex items-start"
        style={{
          height: 'var(--perfil-altura)',
          paddingLeft: 'var(--perfil-avatar-x)',
          paddingTop: 'var(--perfil-avatar-y)',
        }}
      >
        <div
          className="rounded-pill shrink-0 bg-divider"
          style={{ width: 'var(--perfil-avatar)', height: 'var(--perfil-avatar)' }}
          aria-hidden
        />
        <div className="ml-md leading-tight">
          <div className="text-text-primary" style={{ fontSize: 'var(--perfil-nome)' }}>Matheus</div>
          <div
            className="text-text-secondary flex items-center gap-xs"
            style={{ fontSize: 'var(--perfil-status)', marginTop: 3 }}
          >
            <span
              aria-hidden
              style={{
                width: 'var(--perfil-ponto)',
                height: 'var(--perfil-ponto)',
                borderRadius: 99,
                background: '#8FBF6D',
              }}
            />
            Online
          </div>
        </div>
        <span className="ml-auto mr-lg text-text-secondary" style={{ marginTop: 6 }}>
          <Icone nome="chevron" tamanho={14} />
        </span>
      </div>
    </nav>
  );
}
