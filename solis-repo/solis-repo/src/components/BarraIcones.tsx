import { ITENS_NAV } from '../nav-items';
import { Icone } from './icons';

/** Navegação em cápsula flutuante — a ALTERNATIVA à sidebar, não um complemento
 *  dela. Com este modo a coluna lateral não existe: os mesmos 8 itens do
 *  `nav-items` migram pro rodapé, e o conteúdo passa a ocupar a janela inteira.
 *
 *  Medidas de referencias/telas/12-conversa-barra-icones.png, em
 *  solis-tokens.json → layout.iconBar.
 *
 *  A cápsula é centrada na JANELA, não numa área de conteúdo — neste modo não
 *  existe área de conteúdo separada, porque não existe divisória. */
export function BarraIcones({
  ativo = 'conversa',
  aoTrocar,
}: {
  ativo?: string;
  aoTrocar?: (id: string) => void;
}) {
  return (
    <nav
      aria-label="Navegação principal"
      className="fixed left-1/2 -translate-x-1/2 flex items-center justify-between
                 border border-divider bg-[var(--mem-hover)] backdrop-blur-sm"
      style={{
        bottom: 'var(--barra-base)',
        width: 'var(--barra-l)',
        height: 'var(--barra-h)',
        borderRadius: 'var(--barra-raio)',
        paddingLeft: 'calc(var(--barra-h) * 0.25)',
        paddingRight: 'calc(var(--barra-h) * 0.25)',
        zIndex: 2,
      }}
    >
      {ITENS_NAV.map((item) => {
        const ehAtivo = item.id === ativo;
        return (
          <a
            key={item.id}
            href={item.rota}
            title={item.rotulo}
            aria-label={item.rotulo}
            aria-current={ehAtivo ? 'page' : undefined}
            onClick={(e) => {
              if (!aoTrocar) return;
              e.preventDefault();
              aoTrocar(item.id);
            }}
            className={`flex items-center justify-center shrink-0 ${
              ehAtivo ? 'text-accent' : 'text-text-primary'
            }`}
            style={{
              width: 'var(--barra-ativo)',
              height: 'var(--barra-ativo)',
              borderRadius: 'var(--barra-ativo-raio)',
              // O ativo senta num quadradinho da cor de destaque com alpha baixo.
              // É o único item com fundo — os outros sete só têm o ícone.
              background: ehAtivo ? 'color-mix(in srgb, var(--accent) 16%, transparent)' : undefined,
            }}
          >
            <Icone nome={item.icone} tamanho="var(--barra-icone)" />
          </a>
        );
      })}
    </nav>
  );
}
