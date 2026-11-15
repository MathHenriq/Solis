import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  apagarProjetoSolis,
  enviarArquivoProjeto,
  lerProjetoSolis,
  removerArquivoProjeto,
  salvarProjetoSolis,
  type ArquivoProjeto,
  type ProjetoSolis,
} from '../servidor';
import { Botao } from './Controles';
import { Icone } from './icons';

/** O editor de um projeto: nome, instruções, a pasta de código (se quiser) e
 *  os arquivos fixos — como as configurações de um projeto no claude.ai, com a
 *  pasta do Claude Code junto (decidido pelo Matheus, 13/11/2026).
 *
 *  PROVISÓRIO — desenho próprio (13/11/2026): uma caixa por cima da tela, no
 *  desenho dos cartões de Configurações (--cfg-card-*), os campos e botões da
 *  edição da Memória (layout.thread._project no solis-tokens.json). Precisa do
 *  aval do Matheus nos 3 temas e 2 navs. */

const tamanho = (b: number) => (b < 1024 ? `${b} B` : b < 1024 ** 2 ? `${Math.round(b / 1024)} KB` : `${(b / 1024 ** 2).toFixed(1)} MB`);

const campo =
  'w-full bg-transparent outline-none text-text-primary placeholder:text-text-secondary border border-divider ' +
  'focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

export function EditorProjeto({
  id,
  aoFechar,
  aoSalvar,
  aoApagar,
}: {
  /** null: projeto novo. */
  id: number | null;
  aoFechar: () => void;
  /** Salvou: o projeto como ficou, e se era novo. */
  aoSalvar: (p: ProjetoSolis, novo: boolean) => void;
  aoApagar: () => void;
}) {
  const [nome, definirNome] = useState('');
  const [instrucoes, definirInstrucoes] = useState('');
  const [pasta, definirPasta] = useState('');
  const [arquivos, definirArquivos] = useState<ArquivoProjeto[]>([]);
  // Num projeto novo, os arquivos sobem depois de criar.
  const [pendentes, definirPendentes] = useState<File[]>([]);
  const [salvando, definirSalvando] = useState(false);
  const [erro, definirErro] = useState<string | null>(null);
  const [carregando, definirCarregando] = useState(id !== null);
  const [confirmandoApagar, definirConfirmandoApagar] = useState(false);
  const seletor = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (id === null) return;
    void lerProjetoSolis(id).then((p) => {
      definirCarregando(false);
      if (!p) return definirErro('Não consegui abrir o projeto.');
      definirNome(p.nome);
      definirInstrucoes(p.instrucoes);
      definirPasta(p.pasta ?? '');
      definirArquivos(Array.isArray(p.arquivos) ? p.arquivos : []);
    });
  }, [id]);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && !salvando && aoFechar();
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [aoFechar, salvando]);

  const adicionar = async (lista: FileList) => {
    const novos = Array.from(lista);
    if (id === null) return definirPendentes((p) => [...p, ...novos]);
    for (const f of novos) {
      const a = await enviarArquivoProjeto(id, f);
      if (a) definirArquivos((x) => [...x, a]);
      else definirErro(`Não consegui guardar ${f.name}.`);
    }
  };

  const salvar = async () => {
    definirSalvando(true);
    definirErro(null);
    const r = await salvarProjetoSolis({ id: id ?? undefined, nome, instrucoes, pasta: pasta.trim() || null });
    if (r === 'sem-nome' || r === 'pasta-inexistente' || r === null) {
      definirSalvando(false);
      return definirErro(
        r === 'sem-nome' ? 'Dê um nome ao projeto.' : r === 'pasta-inexistente' ? 'Essa pasta não existe.' : 'Não consegui falar com o servidor do Solis.',
      );
    }
    for (const f of pendentes) await enviarArquivoProjeto(r.id, f);
    definirSalvando(false);
    aoSalvar(r, id === null);
  };

  const rotulo = { fontSize: 'var(--cfg-rotulo)' } as const;
  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' } as const;

  // No body, por um portal: dentro da conversa (que tem camada própria), o
  // véu ficava por baixo das barras da navegação por ícones.
  return createPortal(
    <div
      // A fonte e a cor do app: no body, fora da caixa do App, não herda.
      className="fixed inset-0 flex items-center justify-center font-sans text-text-primary"
      style={{ zIndex: 50, background: 'rgb(0 0 0 / 0.45)' }}
      onMouseDown={(e) => e.target === e.currentTarget && !salvando && aoFechar()}
    >
      <div
        role="dialog"
        aria-label={id === null ? 'Novo projeto' : 'Editar o projeto'}
        className="border border-divider bg-canvas flex flex-col overflow-y-auto"
        style={{
          width: 'min(var(--proj-largura), calc(100vw - 32px))',
          maxHeight: 'calc(100vh - 64px)',
          borderRadius: 'var(--cfg-card-raio)',
          padding: 'var(--cfg-card-pad)',
          boxShadow: '0 16px 48px rgb(0 0 0 / 0.35)',
          gap: 'var(--proj-gap)',
        }}
      >
        <div className="flex items-start justify-between" style={{ gap: 16 }}>
          <div>
            <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>
              {id === null ? 'Novo projeto' : 'Projeto'}
            </h2>
            <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
              As conversas do projeto seguem as instruções, têm os arquivos à mão e, com uma pasta, o Claude trabalha nela.
            </p>
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={aoFechar}
            className="text-text-secondary hover:text-text-primary shrink-0 flex items-center justify-center"
            style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', marginTop: -6, marginRight: -8 }}
          >
            <Icone nome="adicionar" tamanho={18} style={{ transform: 'rotate(45deg)' }} />
          </button>
        </div>

        {carregando ? (
          <p className="text-text-secondary" style={dica}>Abrindo…</p>
        ) : (
          <>
            <label className="block">
              <span className="text-text-primary block" style={rotulo}>Nome</span>
              <input
                autoFocus
                value={nome}
                onChange={(e) => definirNome(e.target.value)}
                placeholder="Aulas do Núcleo WIT, Casa, Solis…"
                aria-label="Nome do projeto"
                className={campo}
                style={{ fontSize: 'var(--mem-item-texto)', borderRadius: 'var(--mac-campo-raio)', padding: '8px 10px', marginTop: 8 }}
              />
            </label>

            <label className="block">
              <span className="text-text-primary block" style={rotulo}>Instruções</span>
              <span className="text-text-secondary block" style={dica}>
                Como responder nas conversas deste projeto. Valem pra todos os cérebros.
              </span>
              <textarea
                value={instrucoes}
                onChange={(e) => definirInstrucoes(e.target.value)}
                rows={5}
                placeholder="Ex.: responda como professor de ensino médio, com exemplos do dia a dia."
                aria-label="Instruções do projeto"
                className={`${campo} resize-y`}
                style={{ fontSize: 'var(--mem-item-texto)', lineHeight: 'var(--mem-item-lh)', borderRadius: 'var(--mac-campo-raio)', padding: '8px 10px', marginTop: 8 }}
              />
            </label>

            <label className="block">
              <span className="text-text-primary block" style={rotulo}>Pasta de código (se quiser)</span>
              <span className="text-text-secondary block" style={dica}>
                O Claude trabalha nela e segue o CLAUDE.md dela, como no Claude Code.
              </span>
              <input
                value={pasta}
                onChange={(e) => definirPasta(e.target.value)}
                placeholder="Cole o caminho da pasta"
                aria-label="Pasta de código do projeto"
                className={`${campo} font-mono`}
                style={{ fontSize: 'var(--et-chip-texto)', borderRadius: 'var(--mac-campo-raio)', padding: '8px 10px', marginTop: 8 }}
              />
            </label>

            <div>
              <div className="flex items-center justify-between" style={{ gap: 12 }}>
                <span className="text-text-primary" style={rotulo}>Arquivos</span>
                <button
                  type="button"
                  onClick={() => seletor.current?.click()}
                  className="text-accent hover:underline shrink-0"
                  style={{ fontSize: 'var(--cfg-dica)' }}
                >
                  Adicionar arquivos
                </button>
                <input
                  ref={seletor}
                  type="file"
                  multiple
                  hidden
                  onChange={(e) => {
                    if (e.target.files) void adicionar(e.target.files);
                    e.target.value = '';
                  }}
                />
              </div>
              <span className="text-text-secondary block" style={dica}>
                O que as conversas do projeto têm sempre à mão: o Claude lê; os outros cérebros recebem o texto.
              </span>
              <ul aria-label="Arquivos do projeto" style={{ marginTop: 8 }}>
                {[...arquivos.map((a) => ({ chave: `a${a.id}`, nome: a.nome, tamanho: a.tamanho, a })),
                  ...pendentes.map((f, i) => ({ chave: `p${i}`, nome: f.name, tamanho: f.size, a: null as ArquivoProjeto | null, i }))].map(
                  (x) => (
                    <li
                      key={x.chave}
                      className="flex items-center border-t border-divider first:border-t-0"
                      style={{ gap: 10, padding: '8px 0', fontSize: 'var(--et-chip-texto)' }}
                    >
                      <Icone nome="documento" tamanho={14} className="text-text-secondary shrink-0" />
                      <span className="text-text-primary truncate min-w-0 flex-1" title={x.nome}>{x.nome}</span>
                      <span className="text-text-secondary shrink-0">{tamanho(x.tamanho)}</span>
                      <button
                        type="button"
                        aria-label={`Tirar ${x.nome}`}
                        className="text-text-secondary hover:text-text-primary shrink-0"
                        onClick={async () => {
                          if (x.a && id !== null) {
                            if (await removerArquivoProjeto(id, x.a.id)) definirArquivos((l) => l.filter((y) => y.id !== x.a?.id));
                          } else {
                            definirPendentes((l) => l.filter((_, j) => j !== (x as { i: number }).i));
                          }
                        }}
                      >
                        <Icone nome="adicionar" tamanho={14} style={{ transform: 'rotate(45deg)' }} />
                      </button>
                    </li>
                  ),
                )}
                {!arquivos.length && !pendentes.length && (
                  <li className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)' }}>Nenhum arquivo ainda.</li>
                )}
              </ul>
            </div>

            {erro && <p className="text-[var(--erro)]" style={{ fontSize: 'var(--cfg-dica)' }}>{erro}</p>}

            <div className="flex items-center" style={{ gap: 'var(--mac-botao-gap)' }}>
              {id !== null &&
                (confirmandoApagar ? (
                  <>
                    <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>
                      Apagar o projeto e os arquivos dele? As conversas ficam.
                    </span>
                    <Botao tipo="perigo" onClick={async () => (await apagarProjetoSolis(id)) && aoApagar()}>
                      Apagar
                    </Botao>
                  </>
                ) : (
                  <Botao onClick={() => definirConfirmandoApagar(true)}>Apagar projeto</Botao>
                ))}
              <div className="flex-1" />
              <Botao onClick={aoFechar} disabled={salvando}>Cancelar</Botao>
              <Botao tipo="destaque" onClick={salvar} disabled={salvando || !nome.trim()}>
                {salvando ? 'Salvando…' : id === null ? 'Criar projeto' : 'Salvar'}
              </Botao>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
