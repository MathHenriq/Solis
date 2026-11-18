import { useEffect, useState, type CSSProperties } from 'react';
import { Botao } from '../components/Controles';
import { listarHooks, removerHook, salvarHook, type EventoHook, type Hook } from '../servidor';

/** Configurações → Hooks: regras automáticas do Claude ("antes de rodar um
 *  comando, faça X", "quando a resposta terminar, avise"), como os hooks do
 *  Claude Code (backend/solis/hooks.py). Moram na configuração de usuário dele
 *  (~/.claude/settings.json): valem no Solis e no Claude Code do terminal, e só
 *  pro Claude. A tela oferece só os eventos vistos disparando no Solis.
 *  Decisão do Matheus (17/11/2026): fazer a tela.
 *
 *  PROVISÓRIO — desenho próprio (17/11/2026), com o Claude como base: o cartão,
 *  as linhas, as ações em texto e o formulário do de Servidores MCP
 *  (layout.configuracoes.mcp). Nenhum valor novo (layout.configuracoes.hooks). */

const CAMPO =
  'bg-transparent outline-none text-text-primary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

function Acao({ children, onClick, perigo }: { children: string; onClick: () => void; perigo?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${perigo ? 'text-[var(--erro)]' : 'text-text-secondary hover:text-text-primary'} hover:underline`}
      style={{ fontSize: 'var(--cfg-dica)' }}
    >
      {children}
    </button>
  );
}

function Formulario({
  eventos,
  inicial,
  aoSalvar,
  aoCancelar,
}: {
  eventos: EventoHook[];
  inicial?: Hook;
  aoSalvar: () => void;
  aoCancelar: () => void;
}) {
  const [evento, definirEvento] = useState(inicial?.evento ?? 'PreToolUse');
  const [ferramenta, definirFerramenta] = useState(inicial?.ferramenta ?? '');
  const [comando, definirComando] = useState(inicial?.comando ?? '');
  const [salvando, definirSalvando] = useState(false);
  const [erro, definirErro] = useState('');
  const comFerramenta = eventos.find((e) => e.id === evento)?.ferramenta ?? false;

  const salvar = async () => {
    definirSalvando(true);
    definirErro('');
    // O tempo máximo não tem campo: vale o que já estava (ou o padrão do Claude Code).
    const r = await salvarHook({ evento, ferramenta: comFerramenta ? ferramenta : '', comando, tempo: inicial?.tempo ?? null }, inicial?.id);
    definirSalvando(false);
    if ('erro' in r) definirErro(r.erro);
    else aoSalvar();
  };

  const codigo: CSSProperties = {
    fontSize: 'var(--cod-texto)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: 'var(--mac-campo-py) var(--mac-campo-px)',
    maxWidth: 'var(--cer-texto-max)',
  };
  const caixa: CSSProperties = {
    height: 'var(--mac-botao-h)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: '0 var(--mac-campo-px)',
    fontSize: 'var(--mac-botao-texto)',
  };

  return (
    <div className="border-t border-divider" style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' }}>
      {/* Na largura do comando, embaixo: a ferramenta ocupa o que sobra ao lado do evento. */}
      <div className="flex items-center" style={{ gap: 'var(--mac-botao-gap)', maxWidth: 'var(--cer-texto-max)' }}>
        <select
          value={evento}
          onChange={(e) => definirEvento(e.target.value)}
          aria-label="Quando roda"
          autoFocus
          className={`solis-data text-text-secondary bg-canvas shrink-0 ${CAMPO}`}
          style={caixa}
        >
          {eventos.map((e) => (
            <option key={e.id} value={e.id}>{e.rotulo}</option>
          ))}
        </select>
        {comFerramenta && (
          <input
            value={ferramenta}
            onChange={(e) => definirFerramenta(e.target.value)}
            placeholder="Ferramenta — ex.: Bash (vazio: todas)"
            aria-label="Ferramenta"
            spellCheck={false}
            className={`flex-1 font-mono placeholder:font-sans placeholder:text-text-placeholder ${CAMPO}`}
            style={{ ...caixa, fontSize: 'var(--cod-texto)', minWidth: 0 }}
          />
        )}
      </div>
      <input
        value={comando}
        onChange={(e) => definirComando(e.target.value)}
        placeholder="O comando — ex.: powershell -File C:\scripts\avisar.ps1"
        aria-label="Comando"
        spellCheck={false}
        className={`block w-full font-mono placeholder:font-sans placeholder:text-text-placeholder ${CAMPO}`}
        style={{ ...codigo, marginTop: 'var(--agd-campo-gap)' }}
      />
      <div className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)', textWrap: 'pretty' }}>
        O comando recebe o que aconteceu em JSON na entrada. Se ele sair com código 2, o Claude para: a ferramenta não roda,
        ou a mensagem não vai.
      </div>
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
        <Botao tipo="destaque" onClick={() => void salvar()} disabled={salvando || !comando.trim()}>
          {salvando ? 'Salvando…' : inicial ? 'Salvar' : 'Adicionar'}
        </Botao>
        <Botao onClick={aoCancelar}>Cancelar</Botao>
      </div>
      {erro && (
        <div className="text-[var(--erro)]" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
          {erro}
        </div>
      )}
    </div>
  );
}

export function CartaoHooks() {
  // undefined = lendo; null = servidor fora.
  const [dados, definirDados] = useState<Awaited<ReturnType<typeof listarHooks>> | undefined>(undefined);
  const [editando, definirEditando] = useState<'novo' | Hook | null>(null);
  const [removendo, definirRemovendo] = useState<string | null>(null);
  const [erro, definirErro] = useState('');

  const ler = () => void listarHooks().then(definirDados);
  useEffect(ler, []);

  const remover = async (id: string) => {
    definirRemovendo(null);
    if (await removerHook(id)) ler();
    else definirErro('Não consegui remover agora.');
  };
  const salvo = () => {
    definirEditando(null);
    ler();
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;
  const ok = dados && !('erro' in dados) ? dados : null;
  const lista = ok?.hooks ?? [];

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
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Hooks</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        Regras automáticas do Claude: um comando seu que roda sozinho, sem pedir, toda vez que algo acontece — antes de
        ele usar uma ferramenta, quando a resposta termina. Valem também no Claude Code do terminal, e só pro Claude.
      </p>

      {dados === undefined && <p className="text-text-secondary" style={{ ...dica, ...linha }}>Vendo…</p>}
      {dados === null && (
        <p className="text-text-secondary" style={{ ...dica, ...linha }}>
          Servidor do Solis desligado. Iniciar com npm run backend.
        </p>
      )}
      {dados && 'erro' in dados && (
        <p className="text-[var(--erro)]" style={{ ...dica, ...linha }}>
          {dados.erro}
        </p>
      )}

      {ok && (
        <>
          {lista.map((h) => {
            if (editando && editando !== 'novo' && editando.id === h.id) {
              return <Formulario key={h.id} eventos={ok.eventos} inicial={editando} aoCancelar={() => definirEditando(null)} aoSalvar={salvo} />;
            }
            return (
              <div key={h.id} className="border-t border-divider" style={linha}>
                <div className="text-text-primary truncate" style={{ fontSize: 'var(--cfg-rotulo)', maxWidth: 'var(--cer-texto-max)' }}>
                  {h.rotulo}
                  {h.ferramenta && <span className="text-text-secondary"> · {h.ferramenta}</span>}
                </div>
                <div className="text-text-secondary font-mono truncate" title={h.comando} style={{ ...dica, fontSize: 'var(--cod-texto)' }}>
                  {h.comando}
                </div>
                <div className="flex items-center flex-wrap" style={{ gap: 'var(--agd-acoes-gap)', marginTop: 'var(--cfg-dica-top)' }}>
                  {h.tempo !== null && (
                    <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>até {h.tempo} s</span>
                  )}
                  {!h.editavel ? (
                    <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>
                      Muda-se no Claude Code: {h.tipo !== 'command' ? `tipo ${h.tipo}` : 'evento que o Solis ainda não oferece'}
                    </span>
                  ) : removendo === h.id ? (
                    <>
                      <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>Remover este hook?</span>
                      <Acao perigo onClick={() => void remover(h.id)}>Remover</Acao>
                      <Acao onClick={() => definirRemovendo(null)}>Cancelar</Acao>
                    </>
                  ) : (
                    <>
                      <Acao onClick={() => definirEditando(h)}>Editar</Acao>
                      <Acao onClick={() => definirRemovendo(h.id)}>Remover</Acao>
                    </>
                  )}
                </div>
              </div>
            );
          })}
          {editando === 'novo' ? (
            <Formulario eventos={ok.eventos} aoCancelar={() => definirEditando(null)} aoSalvar={salvo} />
          ) : (
            <div className={lista.length ? 'border-t border-divider' : ''} style={lista.length ? linha : { marginTop: 'var(--cer-linha-pad)' }}>
              {!lista.length && (
                <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginBottom: 'var(--cer-linha-pad)', maxWidth: 'var(--cer-texto-max)' }}>
                  Nenhum ainda.
                </p>
              )}
              <Botao tipo="destaque" onClick={() => definirEditando('novo')}>Novo hook</Botao>
            </div>
          )}
        </>
      )}

      {erro && (
        <div className="text-[var(--erro)]" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
          {erro}
        </div>
      )}
    </section>
  );
}
