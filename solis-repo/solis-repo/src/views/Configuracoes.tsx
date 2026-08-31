import type { ReactNode } from 'react';
import { TEMAS, type EstiloNav, type Tema } from '../theme/theme';

/** Configurações → Aparência.
 *
 *  Medidas de referencias/telas/11-configuracoes-aparencia.png, em
 *  solis-tokens.json → layout.configuracoes. Tipografia derivada pelas razões
 *  contra o corpo de 16px, não por px bruto da imagem — ver
 *  layout.memoria._escala para o porquê.
 *
 *  São TRÊS controles e só três. "Cor de destaque" foi removido do produto: o
 *  accent é fixo por tema, e desde que ele passou a ser derivado até 4,5:1 ele
 *  também não é mais uma escolha livre — deixar o usuário trocar reintroduziria
 *  o problema de contraste que a derivação resolveu. */

const NOME_TEMA: Record<Tema, string> = {
  espacial: 'Espacial',
  claro: 'Claro',
  dark: 'Dark',
};

function Linha({ rotulo, dica, children }: { rotulo: string; dica?: string; children?: ReactNode }) {
  return (
    <div
      className="flex items-center justify-between border-t border-divider first:border-t-0"
      style={{ paddingTop: 'var(--cfg-linha-pad)', paddingBottom: 'var(--cfg-linha-pad)' }}
    >
      <div>
        <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>{rotulo}</div>
        {dica && (
          <div
            className="text-text-secondary"
            style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}
          >
            {dica}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}

/** Miniatura do tema: uma prévia da PRÓPRIA tela, não um ícone de lua ou sol.
 *  É desenhada com as custom properties do tema que ela representa, dentro de um
 *  `data-theme` local — então ela não pode divergir do tema de verdade, porque
 *  lê exatamente os mesmos tokens. */
function Miniatura({ tema, ativo, aoEscolher }: { tema: Tema; ativo: boolean; aoEscolher: () => void }) {
  return (
    <button
      type="button"
      onClick={aoEscolher}
      aria-pressed={ativo}
      className="text-left shrink-0"
      style={{ width: 'var(--cfg-mini-l)' }}
    >
      <div
        data-theme={tema}
        className="relative overflow-hidden bg-canvas"
        style={{
          aspectRatio: 'var(--cfg-mini-razao)',
          borderRadius: 'var(--cfg-mini-raio)',
          border: ativo ? '2px solid var(--accent)' : '1px solid var(--divider)',
        }}
      >
        <div className="absolute inset-y-0 left-0 border-r border-divider" style={{ width: '14%' }} />
        <div className="absolute" style={{ left: '22%', right: '10%', top: '16%' }}>
          {[100, 74, 88].map((l, i) => (
            <div
              key={i}
              className="bg-text-primary"
              style={{ height: 3, width: `${l}%`, marginTop: i ? 9 : 0, opacity: i ? 0.35 : 0.8 }}
            />
          ))}
        </div>
        {/* A cena aparece na miniatura pelo mesmo mecanismo da tela real: é a
            imagem do tema, ancorada embaixo. */}
        <div
          className="absolute inset-x-0 bottom-0"
          style={{
            height: '46%',
            backgroundImage: 'var(--solis-horizon-image, none)',
            backgroundSize: 'cover',
            backgroundPosition: '50% 66%',
            maskImage: 'linear-gradient(to bottom, transparent, #000 55%)',
            WebkitMaskImage: 'linear-gradient(to bottom, transparent, #000 55%)',
          }}
        />
      </div>
      <div
        className={ativo ? 'text-text-primary' : 'text-text-secondary'}
        style={{ fontSize: 'var(--cfg-rotulo)', marginTop: 'var(--cfg-mini-nome-top)', textAlign: 'center' }}
      >
        {NOME_TEMA[tema]}
      </div>
    </button>
  );
}

export function Configuracoes({
  tema,
  aoTrocarTema,
  cena,
  aoTrocarCena,
  nav,
  aoTrocarNav,
}: {
  tema: Tema;
  aoTrocarTema: (t: Tema) => void;
  cena: boolean;
  aoTrocarCena: (v: boolean) => void;
  nav: EstiloNav;
  aoTrocarNav: (e: EstiloNav) => void;
}) {
  return (
    <main className="relative flex-1 overflow-y-auto bg-canvas" style={{ zIndex: 1 }}>
      <div style={{ paddingLeft: 'var(--cfg-inset-l)', paddingRight: 'var(--cfg-inset-r)', paddingTop: 'var(--mem-titulo-top)' }}>
        <h1 className="font-display text-text-primary leading-none" style={{ fontSize: 'var(--mem-titulo)' }}>
          Configurações
        </h1>

        <section
          className="border border-divider"
          style={{
            marginTop: 'calc(var(--cfg-card-top) - var(--mem-titulo-top) - 34px)',
            borderRadius: 'var(--cfg-card-raio)',
            padding: 'var(--cfg-card-pad)',
          }}
        >
          <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Aparência</h2>

          <div style={{ marginTop: 'var(--cfg-linha-pad)' }}>
            <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Tema</div>
            <div className="flex" style={{ gap: 'var(--cfg-mini-gap)', marginTop: 'var(--cfg-linha-pad)' }}>
              {TEMAS.map((t) => (
                <Miniatura key={t} tema={t} ativo={t === tema} aoEscolher={() => aoTrocarTema(t)} />
              ))}
            </div>
          </div>

          <div style={{ marginTop: 'var(--cfg-linha-pad)' }}>
            <Linha rotulo="Navegação" dica="Onde os atalhos das telas ficam">
              {/* Segmentado, não dois botões soltos: são opções mutuamente
                  exclusivas do mesmo eixo, e a forma tem que dizer isso. */}
              <div
                className="flex overflow-hidden border border-divider shrink-0"
                style={{
                  width: 'var(--cfg-seg-l)',
                  height: 'var(--cfg-seg-h)',
                  borderRadius: 'var(--cfg-seg-raio)',
                }}
                role="group"
                aria-label="Estilo de navegação"
              >
                {([['sidebar', 'Sidebar'], ['icones', 'Barra de ícones']] as const).map(([id, rot]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => aoTrocarNav(id)}
                    aria-pressed={nav === id}
                    className={`flex-1 ${nav === id ? 'bg-accent text-canvas' : 'text-text-secondary'}`}
                    style={{ fontSize: 'var(--cfg-rotulo)' }}
                  >
                    {rot}
                  </button>
                ))}
              </div>
            </Linha>

            <Linha rotulo="Exibir imagem de fundo" dica="Desligado, o tema usa cor sólida">
              <button
                type="button"
                role="switch"
                aria-checked={cena}
                aria-label="Exibir imagem de fundo"
                onClick={() => aoTrocarCena(!cena)}
                className={`shrink-0 flex items-center ${cena ? 'bg-accent' : 'bg-divider'}`}
                style={{
                  width: 'var(--cfg-sw-l)',
                  height: 'var(--cfg-sw-h)',
                  borderRadius: 999,
                  padding: 4,
                  justifyContent: cena ? 'flex-end' : 'flex-start',
                  transition: 'background-color 160ms var(--ease)',
                }}
              >
                <span
                  className="block bg-canvas"
                  style={{
                    width: 'calc(var(--cfg-sw-h) - 8px)',
                    height: 'calc(var(--cfg-sw-h) - 8px)',
                    borderRadius: 999,
                  }}
                />
              </button>
            </Linha>
          </div>
        </section>
      </div>
    </main>
  );
}
