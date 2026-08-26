import { TEMAS, type Tema } from './theme/theme';
import { useTheme } from './theme/useTheme';
import { ITENS_NAV } from './nav-items';

/** BANCADA DE VERIFICAÇÃO — não é tela de produto.
 *
 *  Não existe referência visual pra esta página, e por isso ela NÃO segue a
 *  Regra 1: ela não representa nenhuma tela do Solis. Existe só pra provar que
 *  o scaffold sobe, que a troca de tema funciona sem remontar nada e que os
 *  tokens chegaram no CSS. A primeira tela de produto é Conversa, construída
 *  contra referencias/telas/ (CLAUDE.md, fluxo obrigatório, item 2). */
export default function App() {
  const { tema, setTema, cena, setCena } = useTheme();

  return (
    <div className="min-h-full bg-canvas text-text-primary font-sans p-2xl">
      <p className="text-caption uppercase tracking-widest text-text-secondary">
        Bancada de verificação — não é tela de produto
      </p>

      <h1 className="font-display text-hero mt-lg">Olá, Matheus.</h1>
      <p className="text-title2 text-text-secondary mt-sm">Como posso te ajudar hoje?</p>

      <section className="mt-2xl">
        <h2 className="text-caption uppercase tracking-widest text-text-secondary">Tema</h2>
        <div className="flex gap-sm mt-md">
          {TEMAS.map((t: Tema) => (
            <button
              key={t}
              onClick={() => setTema(t)}
              aria-pressed={t === tema}
              className={`h-chip px-xl rounded-md border text-body ${
                t === tema
                  ? 'border-accent text-accent'
                  : 'border-divider text-text-secondary'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-xl">
        <label className="flex items-center gap-md text-body">
          <input type="checkbox" checked={cena} onChange={(e) => setCena(e.target.checked)} />
          Exibir imagem de fundo
          <span className="text-text-secondary text-caption">
            (desligado = versão sólida da paleta do mesmo tema)
          </span>
        </label>
      </section>

      <section className="mt-xl">
        <h2 className="text-caption uppercase tracking-widest text-text-secondary">
          Navegação — fonte única, {ITENS_NAV.length} itens
        </h2>
        <ul className="mt-md" style={{ width: 'var(--sidebar-width)' }}>
          {ITENS_NAV.map((item) => (
            <li
              key={item.id}
              className="text-[length:var(--sidebar-label)] flex items-center border-b border-divider"
              style={{ height: 'var(--sidebar-pitch)', paddingLeft: 'var(--sidebar-label-inset)' }}
            >
              {item.rotulo}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-xl max-w-composer">
        <div
          className="w-full border border-divider rounded-composer flex items-center px-xl text-text-placeholder"
          style={{ height: 'var(--composer-height)' }}
        >
          Fale com o Solis…
        </div>
      </section>
    </div>
  );
}
