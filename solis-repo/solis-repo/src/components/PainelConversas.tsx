import { useEffect, useState } from 'react';
import { listarConversas, type ResumoConversa } from '../servidor';
import { Icone } from './icons';

/** Painel de conversas: "Nova conversa", busca e as conversas por data.
 *  Referência: referencias/telas/19-conversa-lista.png; medidas em
 *  layout.painelConversas (solis-tokens.json).
 *
 *  Vive dentro da tela de Conversa, e não na sidebar: a sidebar já tem os 8
 *  itens de navegação, e um painel próprio funciona igual nos dois modos de
 *  navegação (decisão em docs/PEDIDO_REFERENCIAS.md, item 5). */

const DIA = 24 * 60 * 60 * 1000;

/** O grupo da conversa pela data da última mensagem, na hora local. A
 *  referência mostra os três primeiros; os dois últimos seguem o mesmo
 *  desenho, pra conversa velha não ficar sem grupo. */
function grupo(atualizada: string, hoje: Date): string {
  const inicioDeHoje = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate()).getTime();
  const t = new Date(atualizada).getTime();
  if (t >= inicioDeHoje) return 'Hoje';
  if (t >= inicioDeHoje - DIA) return 'Ontem';
  if (t >= inicioDeHoje - 7 * DIA) return 'Últimos 7 dias';
  if (t >= inicioDeHoje - 30 * DIA) return 'Últimos 30 dias';
  return 'Mais antigas';
}

function emGrupos(conversas: ResumoConversa[]): [string, ResumoConversa[]][] {
  const hoje = new Date();
  const grupos = new Map<string, ResumoConversa[]>();
  // A lista já vem da mais recente pra mais antiga: os grupos saem em ordem.
  for (const c of conversas) {
    const g = grupo(c.atualizada, hoje);
    grupos.set(g, [...(grupos.get(g) ?? []), c]);
  }
  return [...grupos];
}

export function PainelConversas({
  aberta,
  versao,
  aoAbrir,
  aoNova,
}: {
  /** A conversa na thread agora; null numa conversa nova, ainda sem mensagem. */
  aberta: number | null;
  /** Muda quando a lista ficou velha (uma mensagem nova). */
  versao: number;
  aoAbrir: (id: number) => void;
  aoNova: () => void;
}) {
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
    <aside
      aria-label="Conversas"
      className="relative shrink-0 flex flex-col border-r border-divider bg-canvas"
      style={{ width: 'var(--cv-largura)', zIndex: 1 }}
    >
      <div style={{ padding: 'var(--cv-topo) var(--cv-px) 0' }}>
        <button
          type="button"
          onClick={aoNova}
          className="relative flex items-center w-full text-text-primary hover:bg-[var(--mem-hover)]"
          style={{
            height: 'var(--cv-botao-h)',
            borderRadius: 'var(--cv-botao-raio)',
            border: '1px solid color-mix(in srgb, var(--text-primary) var(--cv-botao-borda), transparent)',
            fontSize: 'var(--cv-botao-texto)',
          }}
        >
          {/* Posições absolutas medidas da borda, como na referência: o texto
              a 56px não depende da largura do ícone. */}
          <Icone nome="lapis" tamanho="var(--cv-botao-icone)" className="absolute" style={{ left: 'var(--cv-botao-icone-x)' }} />
          <span style={{ marginLeft: 'var(--cv-botao-texto-x)' }}>Nova conversa</span>
        </button>

        <label
          className="relative flex items-center text-text-primary"
          style={{
            marginTop: 'var(--cv-busca-gap)',
            height: 'var(--cv-busca-h)',
            borderRadius: 'var(--cv-busca-raio)',
            border: '1px solid color-mix(in srgb, var(--text-primary) var(--cv-busca-borda), transparent)',
          }}
        >
          <Icone nome="buscar" tamanho="var(--cv-busca-icone)" className="absolute" style={{ left: 'var(--cv-busca-icone-x)' }} />
          <input
            value={busca}
            onChange={(e) => definirBusca(e.target.value)}
            className="w-full h-full bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
            style={{ paddingLeft: 'var(--cv-busca-texto-x)', paddingRight: 'var(--cv-px)', fontSize: 'var(--cv-busca-texto)' }}
            placeholder="Buscar conversas…"
            aria-label="Buscar conversas"
          />
        </label>
      </div>

      {/* A lista rola sozinha; o botão e a busca ficam no lugar. */}
      <nav
        className="flex-1 overflow-y-auto"
        style={{ padding: '0 var(--cv-px) var(--cv-px)', marginTop: 'var(--cv-grupos-top)' }}
      >
        {busca && !conversas.length && (
          <p className="text-text-secondary" style={{ fontSize: 'var(--cv-rotulo)', paddingLeft: 'var(--cv-rotulo-x)' }}>
            Nenhuma conversa com “{busca.trim()}”.
          </p>
        )}
        {emGrupos(conversas).map(([nome, lista], i) => (
          <section key={nome} style={{ marginTop: i ? 'var(--cv-grupo-gap)' : 0 }}>
            <h2
              className="text-text-secondary"
              style={{ height: 'var(--cv-rotulo-h)', fontSize: 'var(--cv-rotulo)', paddingLeft: 'var(--cv-rotulo-x)' }}
            >
              {nome}
            </h2>
            <ul>
              {lista.map((c) => {
                const ativa = c.id === aberta;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => aoAbrir(c.id)}
                      aria-current={ativa ? 'true' : undefined}
                      title={c.titulo}
                      className={`relative flex items-center w-full text-left text-text-primary ${
                        ativa ? 'bg-[var(--cv-ativo)]' : 'hover:bg-[var(--mem-hover-forte)]'
                      }`}
                      style={{
                        height: 'var(--cv-item-h)',
                        borderRadius: 'var(--cv-item-raio)',
                        padding: '0 var(--cv-item-px)',
                        fontSize: 'var(--cv-item-texto)',
                      }}
                    >
                      {ativa && (
                        <span
                          aria-hidden
                          className="absolute left-0 bg-accent"
                          style={{
                            top: 'var(--cv-barra-recuo)',
                            bottom: 'var(--cv-barra-recuo)',
                            width: 'var(--cv-barra)',
                            borderRadius: 2,
                          }}
                        />
                      )}
                      <span className="truncate">{c.titulo}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </nav>
    </aside>
  );
}
