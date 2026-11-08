import { useEffect, useState, type ReactNode } from 'react';
import { Icone } from '../components/icons';
import { listarCerebros, ordenarCerebros, retomarCerebro, type Cerebro } from '../servidor';
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
    // Quem rola é a div de dentro, não o main: no modo de ícones o main reserva
    // o topo e a barra flutuante com padding (index.css), e um main que rola
    // leva o conteúdo por baixo dos dois. Com dois cartões a tela passou a rolar.
    <main className="relative flex-1 flex flex-col overflow-hidden bg-canvas" style={{ zIndex: 1 }}>
      <div
        className="flex-1 min-h-0 overflow-y-auto"
        style={{ paddingLeft: 'var(--cfg-inset-l)', paddingRight: 'var(--cfg-inset-r)', paddingTop: 'var(--mem-titulo-top)' }}
      >
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
              <Interruptor ligado={cena} rotulo="Exibir imagem de fundo" aoTrocar={aoTrocarCena} />
            </Linha>
          </div>
        </section>

        <CartaoCerebros />
      </div>
    </main>
  );
}

function Interruptor({
  ligado,
  rotulo,
  aoTrocar,
}: {
  ligado: boolean;
  rotulo: string;
  /** Sem ele, o interruptor é só leitura (o modelo local, que nunca desliga). */
  aoTrocar?: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={ligado}
      aria-label={rotulo}
      aria-disabled={!aoTrocar || undefined}
      onClick={() => aoTrocar?.(!ligado)}
      className={`shrink-0 flex items-center ${ligado ? 'bg-accent' : 'bg-divider'}`}
      style={{
        width: 'var(--cfg-sw-l)',
        height: 'var(--cfg-sw-h)',
        borderRadius: 999,
        padding: 4,
        justifyContent: ligado ? 'flex-end' : 'flex-start',
        transition: 'background-color 160ms var(--ease)',
        opacity: aoTrocar ? 1 : 0.45,
        cursor: aoTrocar ? undefined : 'default',
      }}
    >
      {/* Desligado, a bolinha não pode ser da cor do fundo: no dark ela some no
          trilho escuro (visto no print dos Cérebros). */}
      <span
        className={`block ${ligado ? 'bg-canvas' : 'bg-text-secondary'}`}
        style={{
          width: 'calc(var(--cfg-sw-h) - 8px)',
          height: 'calc(var(--cfg-sw-h) - 8px)',
          borderRadius: 999,
        }}
      />
    </button>
  );
}

/* ── Cérebros ─────────────────────────────────────────────────────────────
 * Desenho próprio, sem referência (layout.configuracoes.cerebros), aprovado
 * pelo Matheus pelos prints em 08/11/2026 (design/cerebros-validacao.png). */

const HORA = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' });
const DIA_HORA = new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/** "até 14:30" hoje; com o dia quando a pausa passa da meia-noite (a cota
 *  semanal do Claude volta em dias, não em horas). */
function ate(epoch: number) {
  const quando = new Date(epoch * 1000);
  const hoje = quando.toDateString() === new Date().toDateString();
  return `até ${(hoje ? HORA : DIA_HORA).format(quando)}`;
}

const CLI: Record<string, string> = { claude: 'Claude Code', codex: 'Codex' };

function estadoDe(c: Cerebro): string {
  if (c.nome === 'local') return 'Ollama, aqui no computador. Sempre ligado: o que é privado só passa por ele.';
  if (!c.instalado) return `Não instalado. Instale o CLI do ${CLI[c.nome]} e entre com a sua conta.`;
  if (!c.ligado) return `Desligado. Só responde se chamado com /${c.nome}.`;
  // Motivo vindo do CLI pode ser longo (um JSON de erro): a linha não vira um log.
  if (c.pausa) return `Fora ${ate(c.pausa.ate)}: ${c.pausa.motivo.slice(0, 120) || 'falhou'}.`;
  return `${CLI[c.nome]}, pela sua assinatura.`;
}

function BotaoSeta({ sobe, rotulo, aoClicar }: { sobe: boolean; rotulo: string; aoClicar?: () => void }) {
  return (
    <button
      type="button"
      aria-label={rotulo}
      disabled={!aoClicar}
      onClick={aoClicar}
      className="flex items-center justify-center text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:hover:text-text-secondary"
      style={{ width: 'var(--cer-seta-alvo)', height: 'var(--cer-seta-alvo)', borderRadius: 'var(--mac-botao-raio)' }}
    >
      <Icone nome="chevron" tamanho="var(--cer-seta)" style={sobe ? { transform: 'rotate(180deg)' } : undefined} />
    </button>
  );
}

function CartaoCerebros() {
  // undefined = perguntando; null = servidor desligado.
  const [lista, definirLista] = useState<Cerebro[] | null | undefined>(undefined);

  useEffect(() => {
    let vivo = true;
    listarCerebros().then((l) => vivo && definirLista(l));
    return () => {
      vivo = false;
    };
  }, []);

  // Mostra a mudança na hora e fica com o que o servidor guardou; se ele não
  // guardou, volta ao que era — a tela nunca mostra uma ordem que não vale.
  async function guardar(nova: Cerebro[]) {
    const antes = lista;
    definirLista(nova);
    const r = await ordenarCerebros(nova);
    definirLista(r ?? antes);
  }

  function mover(de: number, para: number) {
    if (!lista) return;
    const nova = [...lista];
    const [item] = nova.splice(de, 1);
    nova.splice(para, 0, item);
    guardar(nova);
  }

  return (
    <section
      className="border border-divider"
      style={{
        marginTop: 'var(--cer-cartao-gap)',
        marginBottom: 'var(--cer-cartao-gap)',
        borderRadius: 'var(--cfg-card-raio)',
        padding: 'var(--cfg-card-pad)',
      }}
    >
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Cérebros</h2>
      <p
        className="text-text-secondary"
        // pretty: sem uma palavra sozinha na última linha ("/local." ficava órfão).
        style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)', textWrap: 'pretty' }}
      >
        Quem responde as suas mensagens, nesta ordem. Se um falhar ou ficar sem cota, o próximo responde.
        Pra chamar um direto, comece a mensagem com /claude, /codex ou /local.
      </p>

      {lista === null && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-linha-pad)' }}>
          Servidor do Solis desligado: a ordem fica guardada nele. Iniciar com npm run backend.
        </p>
      )}

      {lista && (
        <ol>
          {lista.map((c, i) => (
            <li
              key={c.nome}
              className="flex items-center border-t border-divider first:border-t-0"
              style={{ paddingTop: 'var(--cfg-linha-pad)', paddingBottom: 'var(--cfg-linha-pad)' }}
            >
              {/* self-start: o número fica na linha do nome, não no meio das duas. */}
              <span
                className="text-text-secondary shrink-0 self-start"
                style={{ width: 'var(--cer-posicao)', fontSize: 'var(--cfg-rotulo)', fontVariantNumeric: 'tabular-nums' }}
                aria-hidden="true"
              >
                {i + 1}
              </span>
              <div className="flex-1 min-w-0">
                <div
                  className={c.ligado ? 'text-text-primary' : 'text-text-secondary'}
                  style={{ fontSize: 'var(--cfg-rotulo)' }}
                >
                  {c.rotulo}
                </div>
                <div className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
                  {estadoDe(c)}
                  {c.pausa && c.ligado && c.instalado && (
                    <>
                      {' '}
                      <button
                        type="button"
                        className="text-accent hover:underline"
                        onClick={async () => definirLista((await retomarCerebro(c.nome)) ?? lista)}
                      >
                        Tentar agora
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="flex shrink-0" style={{ marginLeft: 'var(--cer-controles-gap)' }}>
                <BotaoSeta
                  sobe
                  rotulo={`Subir ${c.rotulo}`}
                  aoClicar={i > 0 ? () => mover(i, i - 1) : undefined}
                />
                <BotaoSeta
                  sobe={false}
                  rotulo={`Descer ${c.rotulo}`}
                  aoClicar={i < lista.length - 1 ? () => mover(i, i + 1) : undefined}
                />
              </div>
              <div className="shrink-0" style={{ marginLeft: 'var(--cer-controles-gap)' }}>
                <Interruptor
                  ligado={c.ligado}
                  rotulo={c.nome === 'local' ? `${c.rotulo}: sempre ligado` : `Usar ${c.rotulo}`}
                  aoTrocar={
                    c.nome === 'local'
                      ? undefined
                      : (v) => guardar(lista.map((x) => (x.nome === c.nome ? { ...x, ligado: v } : x)))
                  }
                />
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
