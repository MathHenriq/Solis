import { useCallback, useEffect, useRef, useState } from 'react';
import { acaoGit, lerDiffGit, lerGit, type ArquivoGit, type Git } from '../servidor';
import { Botao } from './Controles';
import { Diff } from './EtapasResposta';
import { Icone } from './icons';

/** O git da pasta de projeto, na barra do projeto — o que o Claude Code
 *  Desktop mostra: o ramo e quantos arquivos mudaram; aberto, cada arquivo com
 *  o diff, o commit, o push e o PR. Cada ação é o Matheus clicando (e vai pro
 *  registro de ações, no servidor).
 *
 *  Aprovado pelo Matheus em 13/11/2026 — desenho próprio (12/11/2026), base no Claude Code Desktop: o
 *  botão no texto da barra do projeto; abre pra cima na caixa dos menus do
 *  Conhecimento (--kn-menu-*), na largura --git-largura; o diff é o do cartão
 *  de aprovação (layout.thread.etapas._git no solis-tokens.json). */

const COR: Record<string, string> = {
  M: 'var(--accent)',
  A: 'var(--code-string)',
  '?': 'var(--code-string)',
  D: 'var(--erro)',
  R: 'var(--code-number)',
  U: 'var(--erro)',
};
const NOME: Record<string, string> = {
  M: 'mudou',
  A: 'novo',
  '?': 'novo, fora do git',
  D: 'apagado',
  R: 'renomeado',
  U: 'em conflito',
};

function LinhaArquivo({ conversa, a }: { conversa: number; a: ArquivoGit }) {
  const [diff, definirDiff] = useState<string | null>(null);
  const [aberto, definirAberto] = useState(false);
  return (
    <li>
      <button
        type="button"
        aria-expanded={aberto}
        onClick={async () => {
          const abrir = !aberto;
          definirAberto(abrir);
          if (abrir && diff === null) definirDiff((await lerDiffGit(conversa, a.caminho)) ?? 'Não consegui ler o diff.');
        }}
        className="flex items-center w-full text-left hover:bg-[var(--mem-hover)]"
        style={{ gap: 10, padding: '6px var(--kn-menu-item-px)', borderRadius: 'calc(var(--kn-menu-raio) - var(--kn-menu-pad))' }}
      >
        <span
          className="font-mono shrink-0 text-center"
          title={NOME[a.status] ?? a.status}
          style={{ width: 14, fontSize: 'var(--cod-texto)', color: COR[a.status] ?? 'var(--text-secondary)' }}
        >
          {a.status === '?' ? 'A' : a.status}
        </span>
        <span className="font-mono text-text-primary truncate min-w-0 flex-1" title={a.caminho} style={{ fontSize: 'var(--cod-texto)' }}>
          {a.caminho}
        </span>
        <span className="shrink-0 font-mono" style={{ fontSize: 'var(--et-chip-texto)' }}>
          {a.mais > 0 && <span style={{ color: 'var(--code-string)' }}>+{a.mais}</span>}
          {a.menos > 0 && <span style={{ color: 'var(--erro)', marginLeft: 6 }}>−{a.menos}</span>}
        </span>
        <Icone nome="chevron" tamanho={14} className="text-text-secondary shrink-0" style={{ transform: aberto ? 'rotate(180deg)' : undefined }} />
      </button>
      {aberto && (
        <div style={{ padding: '0 var(--kn-menu-item-px) 8px' }}>
          {diff === null ? (
            <div className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)', marginTop: 6 }}>
              Lendo o diff…
            </div>
          ) : (
            <Diff texto={diff} />
          )}
        </div>
      )}
    </li>
  );
}

export function PainelGit({ conversa, respondendo }: { conversa: number | null; respondendo: boolean }) {
  const [git, definirGit] = useState<Git | null>(null);
  const [aberto, definirAberto] = useState(false);
  const [mensagem, definirMensagem] = useState('');
  const [fazendo, definirFazendo] = useState<'commit' | 'push' | 'pr' | null>(null);
  const [aviso, definirAviso] = useState<{ erro: boolean; texto: string } | null>(null);
  const caixa = useRef<HTMLDivElement>(null);

  const ler = useCallback(() => {
    if (conversa !== null) void lerGit(conversa).then((g) => g && definirGit(g));
  }, [conversa]);
  // No fim de cada resposta: o Claude pode ter mudado arquivo ou feito commit.
  useEffect(() => {
    if (!respondendo) ler();
  }, [respondendo, ler]);
  useEffect(() => {
    if (!aberto) return;
    ler();
    const fora = (e: MouseEvent) => !caixa.current?.contains(e.target as Node) && definirAberto(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && definirAberto(false);
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc);
    };
  }, [aberto, ler]);

  if (conversa === null || !git || !git.repo) return null;
  const n = git.arquivos.length;

  const fazer = async (acao: 'commit' | 'push' | 'pr') => {
    definirFazendo(acao);
    definirAviso(null);
    const r = await acaoGit(conversa, acao, acao === 'commit' ? mensagem : undefined);
    definirFazendo(null);
    if (!r.ok) return definirAviso({ erro: true, texto: r.erro });
    if (acao === 'commit') {
      definirMensagem('');
      definirAviso({ erro: false, texto: `Commit ${r.dados.hash}: ${r.dados.mensagem}` });
    } else if (acao === 'push') definirAviso({ erro: false, texto: `Push feito em ${git.ramo}.` });
    else definirAviso({ erro: false, texto: `PR aberto: ${r.dados.url}` });
    ler();
  };

  const remoto = git.upstream
    ? `${git.upstream}${git.frente ? ` · ${git.frente} à frente` : ''}${git.atras ? ` · ${git.atras} atrás` : ''}`
    : 'sem remoto ainda';
  const podePush = !!git.frente || !git.upstream;

  return (
    <div ref={caixa}>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={aberto}
        title={`${git.raiz} · ${remoto}`}
        onClick={() => definirAberto((a) => !a)}
        className="flex items-center text-text-secondary hover:text-text-primary"
        style={{ gap: 6, fontSize: 'var(--et-dobra-texto)', height: 28 }}
      >
        <Icone nome="ramo" tamanho={16} />
        {git.ramo}
        {n > 0 && <span>· {n === 1 ? '1 mudança' : `${n} mudanças`}</span>}
        <Icone nome="chevron" tamanho={14} style={{ transform: aberto ? 'rotate(180deg)' : undefined }} />
      </button>
      {aberto && (
        <div
          role="dialog"
          aria-label="Git do projeto"
          className="absolute left-0 z-10 border border-divider bg-canvas flex flex-col"
          style={{
            bottom: 'calc(100% + var(--kn-menu-top))',
            width: 'var(--git-largura)',
            maxWidth: 'calc(100vw - 32px)',
            maxHeight: '70vh',
            padding: 'var(--kn-menu-pad)',
            borderRadius: 'var(--kn-menu-raio)',
            boxShadow: '0 8px 24px rgb(0 0 0 / 0.25)',
          }}
        >
          <div className="flex items-center justify-between" style={{ gap: 12, padding: '6px var(--kn-menu-item-px) 8px' }}>
            <div className="min-w-0">
              <div className="flex items-center text-text-primary" style={{ gap: 6, fontSize: 'var(--mac-botao-texto)' }}>
                <Icone nome="ramo" tamanho={16} className="text-text-secondary shrink-0" />
                <span className="truncate">{git.ramo}</span>
              </div>
              <div className="text-text-secondary truncate" style={{ fontSize: 'var(--et-chip-texto)' }}>
                {remoto}
              </div>
            </div>
            <div className="flex shrink-0" style={{ gap: 'var(--mac-botao-gap)' }}>
              {git.gh && (
                <Botao onClick={() => fazer('pr')} disabled={fazendo !== null}>
                  {fazendo === 'pr' ? 'Abrindo…' : 'Abrir PR'}
                </Botao>
              )}
              <Botao onClick={() => fazer('push')} disabled={fazendo !== null || !podePush}>
                {fazendo === 'push' ? 'Enviando…' : 'Push'}
              </Botao>
            </div>
          </div>

          <div className="border-t border-divider" />
          {n === 0 ? (
            <div className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)', padding: '12px var(--kn-menu-item-px)' }}>
              Nada mudou desde o último commit.
            </div>
          ) : (
            <ul aria-label="Arquivos mudados" className="overflow-y-auto" style={{ padding: '4px 0', minHeight: 0 }}>
              {git.arquivos.map((a) => (
                <LinhaArquivo key={a.caminho} conversa={conversa} a={a} />
              ))}
            </ul>
          )}
          <div className="border-t border-divider" />

          <form
            className="flex items-center"
            style={{ gap: 6, padding: '10px var(--kn-menu-item-px) 4px' }}
            onSubmit={(e) => {
              e.preventDefault();
              if (mensagem.trim() && n && !fazendo) void fazer('commit');
            }}
          >
            <input
              value={mensagem}
              onChange={(e) => definirMensagem(e.target.value)}
              placeholder={n ? 'Mensagem do commit' : 'Nada pra commitar'}
              disabled={!n}
              aria-label="Mensagem do commit"
              className="flex-1 min-w-0 bg-transparent outline-none text-text-primary placeholder:text-text-secondary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
              style={{ fontSize: 'var(--et-chip-texto)', borderRadius: 'var(--mac-campo-raio)', padding: '6px 8px' }}
            />
            <Botao tipo="destaque" type="submit" disabled={!n || !mensagem.trim() || fazendo !== null}>
              {fazendo === 'commit' ? 'Fazendo…' : n === 0 ? 'Commit' : n === 1 ? 'Commit de 1 arquivo' : `Commit de ${n} arquivos`}
            </Botao>
          </form>
          {aviso && (
            <div
              className={aviso.erro ? 'text-[var(--erro)]' : 'text-text-secondary'}
              style={{ fontSize: 'var(--et-chip-texto)', padding: '4px var(--kn-menu-item-px) 6px', overflowWrap: 'anywhere' }}
            >
              {aviso.texto}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
