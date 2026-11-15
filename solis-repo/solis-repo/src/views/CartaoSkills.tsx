import { useEffect, useState, type CSSProperties } from 'react';
import { Botao, Interruptor } from '../components/Controles';
import { apagarSkill, lerSkill, ligarSkill, listarSkills, salvarSkill, type Skill, type SkillInteira } from '../servidor';

/** Configurações → Skills: roteiros que o cérebro segue quando o pedido pede,
 *  como Configurações → Skills no Claude Desktop (backend/solis/skills.py). As
 *  suas dizem pra quem servem — uma skill escrita pro Claude não serve
 *  necessariamente pro GPT (o Matheus, 15/11/2026); as da conta do claude.ai
 *  chegam sozinhas e mudam lá.
 *
 *  PROVISÓRIO — desenho próprio (15/11/2026), precisa da aprovação do Matheus:
 *  o cartão e as linhas do de Cérebros (layout.configuracoes.cerebros), as
 *  ações em texto e o formulário das Tarefas agendadas (--agd-*, --mac-*), o
 *  interruptor da Aparência. Medidas novas em layout.configuracoes.skills. */

const CAMPO =
  'bg-transparent outline-none text-text-primary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

type Para = SkillInteira['para'];
const PARA: [string, Para, string][] = [
  ['os-dois', ['claude', 'codex'], 'Claude e GPT'],
  ['claude', ['claude'], 'Só o Claude'],
  ['codex', ['codex'], 'Só o GPT (Codex)'],
];
const chaveDe = (para: Para) => (para.length === 2 ? 'os-dois' : para[0]);
const paraQuem = (para: Para) => PARA.find(([c]) => c === chaveDe(para))?.[2] ?? '';

/** 'Resumo de reunião' → 'resumo-de-reuniao' (o mesmo de skills.nome_de). */
function nomeDe(texto: string): string {
  return texto
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
    .replace(/-+$/, '');
}

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
  inicial,
  aoSalvar,
  aoCancelar,
}: {
  inicial?: SkillInteira;
  aoSalvar: (s: Skill) => void;
  aoCancelar: () => void;
}) {
  const [nome, definirNome] = useState(inicial?.nome ?? '');
  const [descricao, definirDescricao] = useState(inicial?.descricao ?? '');
  const [instrucoes, definirInstrucoes] = useState(inicial?.instrucoes ?? '');
  const [para, definirPara] = useState<Para>(inicial?.para ?? ['claude', 'codex']);
  const [salvando, definirSalvando] = useState(false);
  const [erro, definirErro] = useState('');
  const slug = nomeDe(nome);

  const salvar = async () => {
    definirSalvando(true);
    definirErro('');
    const r = await salvarSkill({ nome: slug, descricao, instrucoes, para }, inicial?.nome);
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

  return (
    <div className="border-t border-divider" style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' }}>
      <input
        value={nome}
        onChange={(e) => definirNome(e.target.value)}
        placeholder="Nome — ex.: Resumo de reunião"
        aria-label="Nome da skill"
        autoFocus
        className={`block w-full placeholder:text-text-placeholder ${CAMPO}`}
        style={texto}
      />
      {nome && slug !== nome && (
        <div className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
          Fica salva como {slug || '…'}
        </div>
      )}
      <textarea
        value={descricao}
        onChange={(e) => definirDescricao(e.target.value)}
        placeholder="Quando usar — ex.: quando eu colar a transcrição de uma reunião e pedir um resumo"
        aria-label="Quando usar"
        rows={2}
        className={`block w-full resize-y placeholder:text-text-placeholder ${CAMPO}`}
        style={{ ...texto, marginTop: 'var(--agd-campo-gap)', lineHeight: 1.5 }}
      />
      <textarea
        value={instrucoes}
        onChange={(e) => definirInstrucoes(e.target.value)}
        placeholder="As instruções — o que fazer, em que ordem, como entregar"
        aria-label="Instruções"
        className={`block w-full resize-y placeholder:text-text-placeholder ${CAMPO}`}
        style={{ ...texto, marginTop: 'var(--agd-campo-gap)', lineHeight: 1.5, minHeight: 'var(--skl-instrucoes-h)' }}
      />
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
        <select
          value={chaveDe(para)}
          onChange={(e) => definirPara(PARA.find(([c]) => c === e.target.value)?.[1] ?? ['claude', 'codex'])}
          aria-label="Pra quem"
          className={`solis-data text-text-secondary bg-canvas ${CAMPO}`}
          style={{
            height: 'var(--mac-botao-h)',
            borderRadius: 'var(--mac-campo-raio)',
            padding: '0 var(--mac-campo-px)',
            fontSize: 'var(--mac-botao-texto)',
            width: 'var(--skl-para-l)',
          }}
        >
          {PARA.map(([c, , rot]) => (
            <option key={c} value={c}>{rot}</option>
          ))}
        </select>
        <Botao tipo="destaque" onClick={() => void salvar()} disabled={salvando || !slug || !descricao.trim() || !instrucoes.trim()}>
          {salvando ? 'Salvando…' : inicial ? 'Salvar' : 'Criar skill'}
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

const GRUPOS: [Skill['origem'], string][] = [
  ['solis', 'Suas'],
  ['conta', 'Da sua conta do claude.ai'],
  ['anthropic', 'Da Anthropic'],
];

export function CartaoSkills() {
  // undefined = lendo; null = servidor fora.
  const [lista, definirLista] = useState<Skill[] | null | undefined>(undefined);
  // 'nova', o nome em edição (com a skill inteira), ou nada.
  const [editando, definirEditando] = useState<'nova' | SkillInteira | null>(null);
  const [apagando, definirApagando] = useState<string | null>(null);
  const [erro, definirErro] = useState('');

  const ler = () => void listarSkills().then(definirLista);
  useEffect(ler, []);

  const editar = async (nome: string) => {
    definirErro('');
    const s = await lerSkill(nome);
    if (s) definirEditando(s);
    else definirErro('Não consegui abrir essa skill agora.');
  };
  const apagar = async (nome: string) => {
    definirApagando(null);
    if (await apagarSkill(nome)) definirLista((l) => l?.filter((s) => s.nome !== nome));
    else definirErro('Não consegui apagar agora.');
  };
  const trocar = async (s: Skill, ligada: boolean) => {
    definirLista((l) => l?.map((x) => (x.nome === s.nome ? { ...x, ligada } : x)));
    if (!(await ligarSkill(s.nome, ligada))) {
      definirLista((l) => l?.map((x) => (x.nome === s.nome ? { ...x, ligada: !ligada } : x)));
      definirErro('Não consegui trocar agora: o servidor do Solis não respondeu.');
    }
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;
  const suas = lista?.filter((s) => s.origem === 'solis') ?? [];

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
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Skills</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        Roteiros que o Claude ou o GPT seguem quando o pedido pede: escreva uma vez como você quer algo feito. As
        suas valem também no Claude Code e no Codex do terminal; as da sua conta do claude.ai chegam sozinhas e
        mudam lá. Desligar tira a skill do Claude.
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
          if (origem !== 'solis' && !doGrupo.length) return null;
          return (
            <div key={origem} style={{ marginTop: 'var(--cer-cartao-gap)' }}>
              <div className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>{titulo}</div>
              {doGrupo.map((s) =>
                editando && editando !== 'nova' && editando.nome === s.nome ? (
                  <Formulario
                    key={s.nome}
                    inicial={editando}
                    aoCancelar={() => definirEditando(null)}
                    aoSalvar={() => {
                      definirEditando(null);
                      ler();
                    }}
                  />
                ) : (
                  <div
                    key={s.nome}
                    className="flex items-center justify-between border-t border-divider"
                    style={{ ...linha, gap: 'var(--cer-controles-gap)' }}
                  >
                    <div className="min-w-0">
                      <div className="text-text-primary truncate" style={{ fontSize: 'var(--cfg-rotulo)', maxWidth: 'var(--cer-texto-max)' }}>
                        {s.nome}
                      </div>
                      <div className="text-text-secondary line-clamp-2" title={s.descricao} style={dica}>
                        {s.descricao}
                      </div>
                      {s.editavel && (
                        <div className="flex items-center flex-wrap" style={{ gap: 'var(--agd-acoes-gap)', marginTop: 'var(--cfg-dica-top)' }}>
                          <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>{paraQuem(s.para)}</span>
                          {apagando === s.nome ? (
                            <>
                              <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>
                                Apagar esta skill? Ela vai pra lixeira do Solis.
                              </span>
                              <Acao perigo onClick={() => void apagar(s.nome)}>Apagar</Acao>
                              <Acao onClick={() => definirApagando(null)}>Cancelar</Acao>
                            </>
                          ) : (
                            <>
                              <Acao onClick={() => void editar(s.nome)}>Editar</Acao>
                              <Acao onClick={() => definirApagando(s.nome)}>Apagar</Acao>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                    {s.para.includes('claude') && (
                      <Interruptor ligado={s.ligada} rotulo={`Ligar ${s.nome}`} aoTrocar={(v) => void trocar(s, v)} />
                    )}
                  </div>
                ),
              )}
              {origem === 'solis' &&
                (editando === 'nova' ? (
                  <Formulario
                    aoCancelar={() => definirEditando(null)}
                    aoSalvar={() => {
                      definirEditando(null);
                      ler();
                    }}
                  />
                ) : (
                  <div className={suas.length ? 'border-t border-divider' : ''} style={suas.length ? linha : { marginTop: 'var(--cfg-dica-top)' }}>
                    {!suas.length && (
                      <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginBottom: 'var(--cer-linha-pad)', maxWidth: 'var(--cer-texto-max)' }}>
                        Nenhuma ainda. Ex.: como você quer o resumo de uma reunião, o roteiro do seu relatório semanal.
                      </p>
                    )}
                    <Botao tipo="destaque" onClick={() => definirEditando('nova')}>Nova skill</Botao>
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
