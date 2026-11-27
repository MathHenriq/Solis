import { useEffect, useState, type CSSProperties } from 'react';
import { Botao } from '../components/Controles';
import { apagarEstilo, escolherEstilo, listarEstilos, salvarEstilo, type Estilo, type Estilos } from '../servidor';

/** Configurações → Estilos de resposta: os prontos (Normal, Conciso,
 *  Explicativo, Formal) e os do Matheus — como "Criar e editar estilos" do
 *  claude.ai (backend/solis/estilos.py). Escolher também se faz no campo de
 *  digitar.
 *
 *  Aprovado pelo Matheus em 15/11/2026 nos 3 temas e 2 navs — desenho próprio:
 *  o cartão, os grupos e as linhas das Skills (layout.configuracoes.skills),
 *  o formulário das Tarefas agendadas (--agd-*, --mac-*). Ver
 *  layout.thread.estilo. */

const CAMPO =
  'bg-transparent outline-none text-text-primary border border-[var(--vn-caixa-borda)] focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

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

function Formulario({ inicial, aoSalvar, aoCancelar }: { inicial?: Estilo; aoSalvar: () => void; aoCancelar: () => void }) {
  const [nome, definirNome] = useState(inicial?.nome ?? '');
  const [instrucoes, definirInstrucoes] = useState(inicial?.instrucoes ?? '');
  const [salvando, definirSalvando] = useState(false);
  const [erro, definirErro] = useState('');
  const texto: CSSProperties = {
    fontSize: 'var(--cfg-rotulo)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: 'var(--mac-campo-py) var(--mac-campo-px)',
    maxWidth: 'var(--cer-texto-max)',
  };
  const salvar = async () => {
    definirSalvando(true);
    definirErro('');
    const r = await salvarEstilo(nome, instrucoes, inicial?.id);
    definirSalvando(false);
    if ('erro' in r) definirErro(r.erro);
    else aoSalvar();
  };
  return (
    <div className="border-t border-divider" style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' }}>
      <input
        value={nome}
        onChange={(e) => definirNome(e.target.value)}
        placeholder="Nome — ex.: Como um amigo"
        aria-label="Nome do estilo"
        autoFocus
        className={`block w-full placeholder:text-text-placeholder ${CAMPO}`}
        style={texto}
      />
      <textarea
        value={instrucoes}
        onChange={(e) => definirInstrucoes(e.target.value)}
        placeholder="Como escrever — ex.: leve e próximo, frases curtas, sem formalidade"
        aria-label="Como escrever"
        rows={3}
        className={`block w-full resize-y placeholder:text-text-placeholder ${CAMPO}`}
        style={{ ...texto, marginTop: 'var(--agd-campo-gap)', lineHeight: 1.5 }}
      />
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
        <Botao tipo="destaque" onClick={() => void salvar()} disabled={salvando || !nome.trim() || !instrucoes.trim()}>
          {salvando ? 'Salvando…' : inicial ? 'Salvar' : 'Criar estilo'}
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

export function CartaoEstilos() {
  const [estilos, definirEstilos] = useState<Estilos | null | undefined>(undefined);
  const [editando, definirEditando] = useState<'novo' | string | null>(null);
  const [apagando, definirApagando] = useState<string | null>(null);
  const [erro, definirErro] = useState('');

  const ler = () => void listarEstilos().then(definirEstilos);
  useEffect(ler, []);

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;
  const seus = estilos?.estilos.filter((e) => e.seu) ?? [];

  const usar = async (id: string) => {
    const r = await escolherEstilo(id);
    if (r) definirEstilos(r);
    else definirErro('Não consegui trocar agora: o servidor do Solis não respondeu.');
  };
  const apagar = async (id: string) => {
    definirApagando(null);
    if (await apagarEstilo(id)) ler();
    else definirErro('Não consegui apagar agora.');
  };

  const Linha = ({ e }: { e: Estilo }) => (
    <div className="border-t border-divider" style={linha}>
      <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>{e.nome}</div>
      <div className="text-text-secondary line-clamp-2" style={dica}>
        {e.instrucoes || 'Como o cérebro escreve normalmente, sem instrução de estilo.'}
      </div>
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--agd-acoes-gap)', marginTop: 'var(--cfg-dica-top)' }}>
        {estilos?.atual === e.id ? (
          <span className="text-accent" style={{ fontSize: 'var(--cfg-dica)' }}>Em uso</span>
        ) : (
          <Acao onClick={() => void usar(e.id)}>Usar</Acao>
        )}
        {e.seu &&
          (apagando === e.id ? (
            <>
              <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>Apagar este estilo?</span>
              <Acao perigo onClick={() => void apagar(e.id)}>Apagar</Acao>
              <Acao onClick={() => definirApagando(null)}>Cancelar</Acao>
            </>
          ) : (
            <>
              <Acao onClick={() => definirEditando(e.id)}>Editar</Acao>
              <Acao onClick={() => definirApagando(e.id)}>Apagar</Acao>
            </>
          ))}
      </div>
    </div>
  );

  return (
    <section className="cfg-cartao">
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Estilos de resposta</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        Como o Solis escreve, com qualquer cérebro: curto, explicando com calma, formal, ou um jeito seu. Vale pra toda
        resposta até você trocar; dá pra trocar também no campo de digitar.
      </p>

      {estilos === undefined && <p className="text-text-secondary" style={{ ...dica, ...linha }}>Vendo…</p>}
      {estilos === null && (
        <p className="text-text-secondary" style={{ ...dica, ...linha }}>
          Servidor do Solis desligado. Iniciar com npm run backend.
        </p>
      )}

      {estilos && (
        <>
          <div style={{ marginTop: 'var(--cer-cartao-gap)' }}>
            <div className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>Prontos</div>
            {estilos.estilos.filter((e) => !e.seu).map((e) => <Linha key={e.id} e={e} />)}
          </div>
          <div style={{ marginTop: 'var(--cer-cartao-gap)' }}>
            <div className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>Seus</div>
            {seus.map((e) =>
              editando === e.id ? (
                <Formulario key={e.id} inicial={e} aoCancelar={() => definirEditando(null)} aoSalvar={() => { definirEditando(null); ler(); }} />
              ) : (
                <Linha key={e.id} e={e} />
              ),
            )}
            {editando === 'novo' ? (
              <Formulario aoCancelar={() => definirEditando(null)} aoSalvar={() => { definirEditando(null); ler(); }} />
            ) : (
              <div className={seus.length ? 'border-t border-divider' : ''} style={seus.length ? linha : { marginTop: 'var(--cfg-dica-top)' }}>
                {!seus.length && (
                  <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginBottom: 'var(--cer-linha-pad)', maxWidth: 'var(--cer-texto-max)' }}>
                    Nenhum ainda. Ex.: como um amigo, ou do jeito que você escreve no trabalho.
                  </p>
                )}
                <Botao tipo="destaque" onClick={() => definirEditando('novo')}>Novo estilo</Botao>
              </div>
            )}
          </div>
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
