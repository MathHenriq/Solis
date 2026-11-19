import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Botao } from '../components/Controles';
import {
  conferirServidorMcp,
  lerServidorMcp,
  listarServidoresMcp,
  removerServidorMcp,
  salvarServidorMcp,
  type FerramentasMcp,
  type ServidorMcp,
  type ServidorMcpInteiro,
} from '../servidor';

/** Configurações → Servidores MCP: ferramentas de fora (um servidor do Notion,
 *  do GitHub, um do Matheus) pros cérebros do Solis, como os servidores MCP do
 *  Claude Code (backend/solis/servidores_mcp.py). Cada um diz pra quem vale,
 *  como as skills; o que vale pro Claude vale também pros cérebros por API
 *  (Groq, Gemini..., pelo corpo do Solis: backend/solis/corpo.py). O que só lê
 *  é livre e o resto pede cartão; no GPT, só o que lê roda. O texto dizia "pro
 *  Claude e pro GPT"; atualizado a pedido do Matheus (19/11/2026).
 *
 *  Aprovado pelo Matheus em 15/11/2026 nos 3 temas e 2 navs — desenho próprio:
 *  o cartão e as linhas do de Cérebros (layout.configuracoes.cerebros), os
 *  grupos e o formulário das Skills (--skl-*, --agd-*, --mac-*). Medida nova em
 *  layout.configuracoes.mcp. */

const CAMPO =
  'bg-transparent outline-none text-text-primary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

type Para = ServidorMcpInteiro['para'];
const PARA: [string, Para, string][] = [
  ['os-dois', ['claude', 'codex'], 'Todos os cérebros'],
  ['claude', ['claude'], 'Todos, menos o GPT'],
  ['codex', ['codex'], 'Só o GPT (Codex)'],
];
const chaveDe = (para: Para) => (para.length === 2 ? 'os-dois' : para[0]);
const paraQuem = (para: Para) => PARA.find(([c]) => c === chaveDe(para))?.[2] ?? '';

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

function estadoDe(f: FerramentasMcp | null | undefined, conferindo: boolean): string {
  if (conferindo) return 'Vendo as ferramentas…';
  if (!f) return 'Ainda não conferido.';
  if (f.erro) return `Não respondeu: ${f.erro}`;
  const n = `${f.total} ${f.total === 1 ? 'ferramenta' : 'ferramentas'}`;
  return f.so_leem ? `${n}, ${f.so_leem} só ${f.so_leem === 1 ? 'lê' : 'leem'}` : n;
}

function Formulario({
  inicial,
  aoSalvar,
  aoCancelar,
}: {
  inicial?: ServidorMcpInteiro;
  aoSalvar: (s: ServidorMcp) => void;
  aoCancelar: () => void;
}) {
  const [nome, definirNome] = useState(inicial?.nome ?? '');
  const [tipo, definirTipo] = useState<'comando' | 'endereco'>(inicial?.tipo ?? 'comando');
  const [comando, definirComando] = useState(inicial?.comando ?? '');
  const [url, definirUrl] = useState(inicial?.url ?? '');
  const [variaveis, definirVariaveis] = useState(inicial?.variaveis ?? '');
  const [para, definirPara] = useState<Para>(inicial?.para ?? ['claude', 'codex']);
  const [salvando, definirSalvando] = useState(false);
  const [erro, definirErro] = useState('');

  const salvar = async () => {
    definirSalvando(true);
    definirErro('');
    const r = await salvarServidorMcp({ nome: nome.trim(), tipo, comando, url, variaveis, para }, inicial?.nome);
    definirSalvando(false);
    if ('erro' in r) definirErro(r.erro);
    else aoSalvar(r);
  };

  const texto: CSSProperties = {
    fontSize: 'var(--cfg-rotulo)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: 'var(--mac-campo-py) var(--mac-campo-px)',
    maxWidth: 'var(--cer-texto-max)',
  };
  const codigo: CSSProperties = { ...texto, fontSize: 'var(--cod-texto)' };
  const caixa = (largura: string): CSSProperties => ({
    height: 'var(--mac-botao-h)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: '0 var(--mac-campo-px)',
    fontSize: 'var(--mac-botao-texto)',
    width: largura,
  });
  const pronto = nome.trim() && (tipo === 'comando' ? comando.trim() : url.trim());

  return (
    <div className="border-t border-divider" style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' }}>
      <input
        value={nome}
        onChange={(e) => definirNome(e.target.value)}
        placeholder="Nome — ex.: notion"
        aria-label="Nome do servidor"
        autoFocus
        className={`block w-full placeholder:text-text-placeholder ${CAMPO}`}
        style={texto}
      />
      {tipo === 'comando' ? (
        <input
          value={comando}
          onChange={(e) => definirComando(e.target.value)}
          placeholder="O comando que sobe o servidor — ex.: npx -y @notionhq/notion-mcp-server"
          aria-label="Comando"
          spellCheck={false}
          className={`block w-full font-mono placeholder:font-sans placeholder:text-text-placeholder ${CAMPO}`}
          style={{ ...codigo, marginTop: 'var(--agd-campo-gap)' }}
        />
      ) : (
        <input
          value={url}
          onChange={(e) => definirUrl(e.target.value)}
          placeholder="O endereço — ex.: https://mcp.exemplo.com/mcp"
          aria-label="Endereço"
          spellCheck={false}
          className={`block w-full font-mono placeholder:font-sans placeholder:text-text-placeholder ${CAMPO}`}
          style={{ ...codigo, marginTop: 'var(--agd-campo-gap)' }}
        />
      )}
      {tipo === 'comando' && (
        <>
          <textarea
            value={variaveis}
            onChange={(e) => definirVariaveis(e.target.value)}
            placeholder="Variáveis, se o servidor pedir — uma por linha: CHAVE=valor"
            aria-label="Variáveis"
            rows={2}
            spellCheck={false}
            className={`block w-full resize-y font-mono placeholder:font-sans placeholder:text-text-placeholder ${CAMPO}`}
            style={{ ...codigo, marginTop: 'var(--agd-campo-gap)', lineHeight: 1.5 }}
          />
          <div className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' }}>
            Uma chave de API fica no cofre do Solis, criptografada; o Claude Code e o Codex a recebem só na hora de ligar o servidor.
          </div>
        </>
      )}
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
        <select
          value={tipo}
          onChange={(e) => definirTipo(e.target.value as 'comando' | 'endereco')}
          aria-label="Tipo"
          className={`solis-data text-text-secondary bg-canvas ${CAMPO}`}
          style={caixa('var(--mcp-tipo-l)')}
        >
          <option value="comando">Comando no PC</option>
          <option value="endereco">Endereço na internet</option>
        </select>
        <select
          value={chaveDe(para)}
          onChange={(e) => definirPara(PARA.find(([c]) => c === e.target.value)?.[1] ?? ['claude', 'codex'])}
          aria-label="Pra quem"
          className={`solis-data text-text-secondary bg-canvas ${CAMPO}`}
          style={caixa('var(--skl-para-l)')}
        >
          {PARA.map(([c, , rot]) => (
            <option key={c} value={c}>{rot}</option>
          ))}
        </select>
        <Botao tipo="destaque" onClick={() => void salvar()} disabled={salvando || !pronto}>
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

const GRUPOS: [ServidorMcp['origem'], string][] = [
  ['seu', 'Seus'],
  ['solis', 'Do Solis'],
  ['codex', 'Do Codex'],
];

export function CartaoServidoresMcp() {
  // undefined = lendo; null = servidor fora.
  const [lista, definirLista] = useState<ServidorMcp[] | null | undefined>(undefined);
  const [editando, definirEditando] = useState<'novo' | ServidorMcpInteiro | null>(null);
  const [removendo, definirRemovendo] = useState<string | null>(null);
  const [conferindo, definirConferindo] = useState<Set<string>>(new Set());
  const [erro, definirErro] = useState('');
  const vistos = useRef<Set<string>>(new Set());

  const conferir = async (nome: string) => {
    definirConferindo((c) => new Set(c).add(nome));
    const f = await conferirServidorMcp(nome);
    definirConferindo((c) => {
      const n = new Set(c);
      n.delete(nome);
      return n;
    });
    if (f) definirLista((l) => l?.map((s) => (s.nome === nome ? { ...s, ferramentas: f } : s)));
  };

  const ler = () =>
    void listarServidoresMcp().then(async (l) => {
      definirLista(l);
      // Os nunca conferidos (os internos do Codex sobem com o ambiente dele: não),
      // um de cada vez: cada um sobe um processo.
      for (const s of l ?? []) {
        if (!s.ferramentas && s.origem !== 'codex' && !vistos.current.has(s.nome)) {
          vistos.current.add(s.nome);
          await conferir(s.nome);
        }
      }
    });
  useEffect(ler, []);

  const editar = async (nome: string) => {
    definirErro('');
    const s = await lerServidorMcp(nome);
    if (s) definirEditando(s);
    else definirErro('Não consegui abrir esse servidor agora.');
  };
  const remover = async (nome: string) => {
    definirRemovendo(null);
    if (await removerServidorMcp(nome)) definirLista((l) => l?.filter((s) => s.nome !== nome));
    else definirErro('Não consegui remover agora.');
  };
  const salvo = (s: ServidorMcp) => {
    definirEditando(null);
    vistos.current.delete(s.nome);
    ler();
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;
  const seus = lista?.filter((s) => s.origem === 'seu') ?? [];

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
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Servidores MCP</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        Ferramentas de fora, como um servidor do Notion, do GitHub ou um seu, pro Claude, o GPT e os cérebros por API
        (Groq, Gemini...). O que só lê é livre e o resto pede você antes; no GPT, só o que lê roda. Valem também no
        Claude Code e no Codex do terminal.
      </p>

      {lista === undefined && <p className="text-text-secondary" style={{ ...dica, ...linha }}>Vendo…</p>}
      {lista === null && (
        <p className="text-text-secondary" style={{ ...dica, ...linha }}>
          Servidor do Solis desligado. Iniciar com npm run backend.
        </p>
      )}

      {lista &&
        GRUPOS.map(([origem, titulo]) => {
          const doGrupo = lista.filter((s) => s.origem === origem);
          if (origem !== 'seu' && !doGrupo.length) return null;
          return (
            <div key={origem} style={{ marginTop: 'var(--cer-cartao-gap)' }}>
              <div className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>{titulo}</div>
              {doGrupo.map((s) => {
                if (editando && editando !== 'novo' && editando.nome === s.nome) {
                  return <Formulario key={s.nome} inicial={editando} aoCancelar={() => definirEditando(null)} aoSalvar={salvo} />;
                }
                const f = s.ferramentas;
                return (
                  <div key={s.nome} className="border-t border-divider" style={linha}>
                    <div className="text-text-primary truncate" style={{ fontSize: 'var(--cfg-rotulo)', maxWidth: 'var(--cer-texto-max)' }}>
                      {s.nome}
                    </div>
                    <div
                      className="text-text-secondary font-mono truncate"
                      title={s.comando || s.url}
                      style={{ ...dica, fontSize: 'var(--cod-texto)' }}
                    >
                      {s.comando || s.url}
                    </div>
                    <div className="flex items-center flex-wrap" style={{ gap: 'var(--agd-acoes-gap)', marginTop: 'var(--cfg-dica-top)' }}>
                      <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>
                        {paraQuem(s.para)}
                        {s.desligado_no_codex ? ' · desligado no Codex' : ''}
                      </span>
                      {s.origem !== 'codex' && (
                        <span
                          className={f?.erro && !conferindo.has(s.nome) ? 'text-[var(--erro)]' : 'text-text-secondary'}
                          style={{ fontSize: 'var(--cfg-dica)' }}
                        >
                          {estadoDe(f, conferindo.has(s.nome))}
                        </span>
                      )}
                      {s.editavel &&
                        (removendo === s.nome ? (
                          <>
                            <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>Remover este servidor?</span>
                            <Acao perigo onClick={() => void remover(s.nome)}>Remover</Acao>
                            <Acao onClick={() => definirRemovendo(null)}>Cancelar</Acao>
                          </>
                        ) : (
                          <>
                            {!conferindo.has(s.nome) && <Acao onClick={() => void conferir(s.nome)}>Conferir</Acao>}
                            <Acao onClick={() => void editar(s.nome)}>Editar</Acao>
                            <Acao onClick={() => definirRemovendo(s.nome)}>Remover</Acao>
                          </>
                        ))}
                    </div>
                  </div>
                );
              })}
              {origem === 'seu' &&
                (editando === 'novo' ? (
                  <Formulario aoCancelar={() => definirEditando(null)} aoSalvar={salvo} />
                ) : (
                  <div className={seus.length ? 'border-t border-divider' : ''} style={seus.length ? linha : { marginTop: 'var(--cfg-dica-top)' }}>
                    {!seus.length && (
                      <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginBottom: 'var(--cer-linha-pad)', maxWidth: 'var(--cer-texto-max)' }}>
                        Nenhum ainda. O site de cada servidor diz o comando ou o endereço.
                      </p>
                    )}
                    <Botao tipo="destaque" onClick={() => definirEditando('novo')}>Novo servidor</Botao>
                  </div>
                ))}
            </div>
          );
        })}

      {erro && (
        <div className="text-[var(--erro)]" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
          {erro}
        </div>
      )}
    </section>
  );
}
