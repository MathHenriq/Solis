import { useEffect, useRef, useState } from 'react';
import { Botao, Interruptor } from '../components/Controles';
import { Icone } from '../components/icons';
import {
  apagarChave,
  guardarChave,
  listarCerebros,
  ordenarCerebros,
  retomarCerebro,
  type Cerebro,
  type ResultadoChave,
} from '../servidor';

/** Configurações → Cérebros: quem responde as mensagens, em que ordem.
 *
 *  Desenho próprio, sem referência (layout.configuracoes.cerebros), aprovado
 *  pelo Matheus pelos prints em 08/11/2026 (design/cerebros-validacao.png). As
 *  linhas dos cérebros por API (chave, campo de colar) vieram depois e seguem o
 *  mesmo desenho; o campo e os botões são os da edição da Memória. */

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
  if (c.tipo === 'local') return 'Ollama, aqui no computador. Sempre ligado: o que é privado só passa por ele.';
  if (!c.instalado) {
    return c.tipo === 'api'
      ? `Sem chave. ${c.nota ?? ''}`
      : `Não instalado. Instale o CLI do ${CLI[c.nome]} e entre com a sua conta.`;
  }
  if (!c.ligado) return `Desligado. Só responde se chamado com /${c.nome}.`;
  // Motivo vindo do serviço pode ser longo (um JSON de erro): a linha não vira um log.
  if (c.pausa) return `Fora ${ate(c.pausa.ate)}: ${c.pausa.motivo.slice(0, 120) || 'falhou'}.`;
  if (c.tipo === 'api') return `${c.modelo}. ${c.nota ?? ''}`;
  return `${CLI[c.nome]}, pela sua assinatura.`;
}

const ERRO_CHAVE: Record<Exclude<ResultadoChave['estado'], 'ok'>, (rotulo: string) => string> = {
  recusada: (r) => `O ${r} recusou essa chave. Confira se ela foi copiada inteira.`,
  vazia: () => 'Cole a chave antes de salvar.',
  'servico-fora': (r) => `Não consegui falar com o ${r} agora. Tente de novo daqui a pouco.`,
  'sem-servidor': () => 'Servidor do Solis desligado. Iniciar com npm run backend.',
};

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

/** Ação em texto dentro da linha ("Colar chave", "Tentar agora"). */
function Acao({ destaque, ...resto }: React.ButtonHTMLAttributes<HTMLButtonElement> & { destaque?: boolean }) {
  return (
    <button
      type="button"
      {...resto}
      className={destaque ? 'text-accent hover:underline' : 'text-text-secondary hover:text-text-primary hover:underline'}
    />
  );
}

/** O campo de colar a chave, aberto na própria linha — sem janela por cima. */
function CampoChave({
  c,
  aoSalvar,
  aoCancelar,
}: {
  c: Cerebro;
  aoSalvar: (lista: Cerebro[]) => void;
  aoCancelar: () => void;
}) {
  const [chave, definirChave] = useState('');
  const [conferindo, definirConferindo] = useState(false);
  const [erro, definirErro] = useState<string | null>(null);
  const campo = useRef<HTMLInputElement>(null);

  useEffect(() => campo.current?.focus(), []);

  async function salvar() {
    definirConferindo(true);
    definirErro(null);
    const r = await guardarChave(c.nome, chave);
    definirConferindo(false);
    if (r.estado === 'ok') aoSalvar(r.cerebros);
    else definirErro(ERRO_CHAVE[r.estado](c.rotulo));
  }

  return (
    <div style={{ marginTop: 'var(--mac-botao-top)', maxWidth: 'var(--cer-texto-max)' }}>
      <input
        ref={campo}
        type="password"
        value={chave}
        autoComplete="off"
        spellCheck={false}
        onChange={(e) => definirChave(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && chave.trim()) salvar();
          else if (e.key === 'Escape') aoCancelar();
        }}
        placeholder={`Cole a chave do ${c.rotulo}`}
        aria-label={`Chave do ${c.rotulo}`}
        className="block w-full bg-transparent outline-none text-text-primary placeholder:text-text-secondary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
        style={{
          fontSize: 'var(--cfg-dica)',
          borderRadius: 'var(--mac-campo-raio)',
          padding: 'var(--mac-campo-py) var(--mac-campo-px)',
        }}
      />
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
        <Botao tipo="destaque" onClick={salvar} disabled={conferindo || !chave.trim()}>
          {/* Conferindo: o servidor testa a chave no serviço antes de guardar. */}
          {conferindo ? 'Conferindo…' : 'Salvar'}
        </Botao>
        <Botao onClick={aoCancelar}>Cancelar</Botao>
        {c.site && (
          <a
            href={c.site}
            target="_blank"
            rel="noreferrer"
            className="text-accent hover:underline"
            style={{ fontSize: 'var(--mac-botao-texto)', marginLeft: 'var(--mac-botao-px)' }}
          >
            Criar uma chave grátis
          </a>
        )}
      </div>
      {erro && (
        <p className="text-[var(--erro)]" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mac-botao-top)' }}>
          {erro}
        </p>
      )}
    </div>
  );
}

export function CartaoCerebros() {
  // undefined = perguntando; null = servidor desligado.
  const [lista, definirLista] = useState<Cerebro[] | null | undefined>(undefined);
  // A linha com o campo de chave aberto (uma por vez).
  const [colando, definirColando] = useState<string | null>(null);

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
        Pra chamar um direto, comece a mensagem com o nome dele: /claude, /groq, /local…
      </p>

      {lista === null && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cer-linha-pad)' }}>
          Servidor do Solis desligado: a ordem fica guardada nele. Iniciar com npm run backend.
        </p>
      )}

      {lista && (
        <ol>
          {lista.map((c, i) => (
            <li
              key={c.nome}
              className="flex items-center border-t border-divider first:border-t-0"
              style={{ paddingTop: 'var(--cer-linha-pad)', paddingBottom: 'var(--cer-linha-pad)' }}
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
                <div
                  className="text-text-secondary"
                  style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' }}
                >
                  {estadoDe(c)}
                  {c.pausa && c.ligado && c.instalado && (
                    <>
                      {' '}
                      <Acao destaque onClick={async () => definirLista((await retomarCerebro(c.nome)) ?? lista)}>
                        Tentar agora
                      </Acao>
                    </>
                  )}
                </div>
                {c.tipo === 'api' && colando !== c.nome && (
                  <div
                    className="flex"
                    style={{ gap: 'var(--cer-controles-gap)', fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}
                  >
                    {c.instalado ? (
                      <>
                        <Acao onClick={() => definirColando(c.nome)}>Trocar chave</Acao>
                        <Acao onClick={async () => definirLista((await apagarChave(c.nome)) ?? lista)}>Remover chave</Acao>
                      </>
                    ) : (
                      <Acao destaque onClick={() => definirColando(c.nome)}>
                        Colar chave
                      </Acao>
                    )}
                  </div>
                )}
                {colando === c.nome && (
                  <CampoChave
                    c={c}
                    aoSalvar={(l) => {
                      definirLista(l);
                      definirColando(null);
                    }}
                    aoCancelar={() => definirColando(null)}
                  />
                )}
              </div>
              <div className="flex shrink-0" style={{ marginLeft: 'var(--cer-controles-gap)' }}>
                <BotaoSeta sobe rotulo={`Subir ${c.rotulo}`} aoClicar={i > 0 ? () => mover(i, i - 1) : undefined} />
                <BotaoSeta
                  sobe={false}
                  rotulo={`Descer ${c.rotulo}`}
                  aoClicar={i < lista.length - 1 ? () => mover(i, i + 1) : undefined}
                />
              </div>
              <div className="shrink-0" style={{ marginLeft: 'var(--cer-controles-gap)' }}>
                <Interruptor
                  ligado={c.ligado}
                  rotulo={c.tipo === 'local' ? `${c.rotulo}: sempre ligado` : `Usar ${c.rotulo}`}
                  aoTrocar={
                    // O local nunca desliga; por API sem chave não tem como ligar.
                    c.tipo === 'local' || (c.tipo === 'api' && !c.instalado)
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
