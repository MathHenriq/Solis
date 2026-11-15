import { useEffect, useRef, useState, type ReactNode } from 'react';
import { guardarProjeto, lerProjeto, listarProjetos, type Projeto, type ProjetoSolis } from '../servidor';
import { Botao } from './Controles';
import { EditorProjeto } from './EditorProjeto';
import { Icone } from './icons';
import { PainelGit } from './PainelGit';

/** A pasta de projeto e o modo da conversa, acima do campo de digitar — como o
 *  Claude Code mostra a pasta e o modo (docs/PARIDADE.md → Trabalhar num
 *  projeto). Com projeto, o Claude trabalha nele, lê o CLAUDE.md dele e lê
 *  ali dentro sem pedir.
 *
 *  PROVISÓRIO — desenho próprio (12/11/2026), base no Claude Code: texto
 *  secundário pequeno, sem caixa, e os menus abrindo pra cima na caixa dos
 *  menus do Conhecimento (--kn-menu-*), como o seletor do modelo. */

const MODOS: { id: Projeto['modo']; nome: string; dica: string }[] = [
  { id: 'pedir', nome: 'Pede aprovação', dica: 'Escrever, editar e rodar comando pedem você.' },
  { id: 'aceitar', nome: 'Aceita edições', dica: 'Edita arquivos do projeto sem pedir; comandos ainda pedem.' },
  { id: 'planejar', nome: 'Planeja antes', dica: 'Mostra o plano e só faz depois que você aprovar.' },
];

const nomeDaPasta = (p: string) => p.split(/[\\/]/).filter(Boolean).pop() ?? p;

function Menu({ aoFechar, children, largura }: { aoFechar: () => void; children: ReactNode; largura: number }) {
  const caixa = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const fora = (e: MouseEvent) => !caixa.current?.parentElement?.contains(e.target as Node) && aoFechar();
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc);
    };
  }, [aoFechar]);
  return (
    <div
      ref={caixa}
      role="menu"
      className="absolute left-0 z-10 border border-divider bg-canvas"
      style={{
        bottom: 'calc(100% + var(--kn-menu-top))',
        width: largura,
        maxHeight: '70vh',
        overflowY: 'auto',
        padding: 'var(--kn-menu-pad)',
        borderRadius: 'var(--kn-menu-raio)',
        boxShadow: '0 8px 24px rgb(0 0 0 / 0.25)',
      }}
    >
      {children}
    </div>
  );
}

function Item({ marcado, aoEscolher, titulo, dica, desligado }: {
  marcado?: boolean;
  aoEscolher: () => void;
  titulo: string;
  dica?: string;
  desligado?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={!!marcado}
      disabled={desligado}
      onClick={aoEscolher}
      className="flex items-start justify-between w-full text-left hover:bg-[var(--mem-hover)] disabled:opacity-50"
      style={{ padding: '8px var(--kn-menu-item-px)', borderRadius: 'calc(var(--kn-menu-raio) - var(--kn-menu-pad))', gap: 8 }}
    >
      <span className="min-w-0">
        <span className="block text-text-primary truncate" style={{ fontSize: 'var(--mac-botao-texto)' }}>
          {titulo}
        </span>
        {dica && (
          <span className="block text-text-secondary truncate" title={dica} style={{ fontSize: 'var(--et-chip-texto)' }}>
            {dica}
          </span>
        )}
      </span>
      {marcado && <Icone nome="feito" tamanho="var(--mac-icone)" className="text-accent shrink-0" />}
    </button>
  );
}

export function BarraProjeto({ conversa, respondendo = false }: { conversa: number | null; respondendo?: boolean }) {
  const [projeto, definirProjeto] = useState<Projeto | null>(null);
  const [aberto, definirAberto] = useState<'pasta' | 'modo' | null>(null);
  const [colado, definirColado] = useState('');
  const [erro, definirErro] = useState<string | null>(null);
  // Os projetos (lidos ao abrir o menu) e o editor aberto: um id, 'novo' ou null.
  const [projetos, definirProjetos] = useState<ProjetoSolis[]>([]);
  const [editando, definirEditando] = useState<number | 'novo' | null>(null);
  useEffect(() => {
    if (aberto === 'pasta') void listarProjetos().then((l) => l && definirProjetos(l));
  }, [aberto]);

  useEffect(() => {
    definirProjeto(null);
    if (conversa !== null) lerProjeto(conversa).then(definirProjeto);
  }, [conversa]);
  // No fim de cada resposta: o modo pode ter mudado no meio (o plano aprovado
  // volta a conversa pra "pede aprovação").
  useEffect(() => {
    if (!respondendo && conversa !== null) lerProjeto(conversa).then((p) => p && definirProjeto(p));
  }, [respondendo, conversa]);

  if (conversa === null || !projeto) return null;

  /** `projeto`: o id (entra no projeto), null (sai dele) ou nada (fica). */
  async function trocar(pasta: string | null, modo: Projeto['modo'], projetoId?: number | null) {
    if (conversa === null) return;
    const r = await guardarProjeto(conversa, pasta, modo, projetoId);
    if (r === 'pasta-inexistente') return definirErro('Essa pasta não existe.');
    if (!r) return definirErro('Não consegui falar com o servidor do Solis.');
    definirErro(null);
    definirProjeto(r);
    definirAberto(null);
    definirColado('');
  }

  const modo = MODOS.find((m) => m.id === projeto.modo) ?? MODOS[0];
  const botao = 'flex items-center text-text-secondary hover:text-text-primary';
  const estilo = { gap: 6, fontSize: 'var(--et-dobra-texto)', height: 28 } as const;

  return (
    // relative: o painel do git abre pra cima a partir do começo da barra.
    <div className="relative flex items-center" style={{ gap: 16, marginBottom: 6, paddingLeft: 12 }}>
      <div className="relative">
        <button
          type="button"
          className={botao}
          style={estilo}
          aria-haspopup="menu"
          aria-expanded={aberto === 'pasta'}
          title={
            projeto.projeto
              ? `Projeto ${projeto.projeto.nome}${projeto.pasta ? ` · ${projeto.pasta}` : ''}`
              : (projeto.pasta ?? 'O Claude trabalha na pasta de trabalho do Solis')
          }
          onClick={() => definirAberto((a) => (a === 'pasta' ? null : 'pasta'))}
        >
          <Icone nome={projeto.projeto ? 'conhecimento' : 'arquivos'} tamanho={16} />
          {projeto.projeto ? projeto.projeto.nome : projeto.pasta ? nomeDaPasta(projeto.pasta) : 'Sem projeto'}
          <Icone nome="chevron" tamanho={14} style={{ transform: aberto === 'pasta' ? 'rotate(180deg)' : undefined }} />
        </button>
        {aberto === 'pasta' && (
          <Menu aoFechar={() => definirAberto(null)} largura={380}>
            <div className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)', padding: '6px var(--kn-menu-item-px) 4px' }}>
              Projeto: instruções, arquivos e a pasta de código que a conversa usa
            </div>
            {projetos.map((p) => (
              <Item
                key={p.id}
                marcado={p.id === projeto.projeto?.id}
                titulo={p.nome}
                dica={
                  [
                    typeof p.arquivos === 'number' && p.arquivos ? `${p.arquivos} ${p.arquivos === 1 ? 'arquivo' : 'arquivos'}` : '',
                    p.pasta ? nomeDaPasta(p.pasta) : '',
                    p.instrucoes.trim() ? 'com instruções' : '',
                  ].filter(Boolean).join(' · ') || 'Sem instruções nem arquivos ainda'
                }
                aoEscolher={() => trocar(null, projeto.modo === 'aceitar' && !p.pasta ? 'pedir' : projeto.modo, p.id)}
              />
            ))}
            <Item titulo="Novo projeto…" dica="Instruções, arquivos fixos e, se quiser, uma pasta de código" aoEscolher={() => {
              definirAberto(null);
              definirEditando('novo');
            }} />
            {projeto.projeto && (
              <Item titulo="Editar este projeto…" aoEscolher={() => {
                definirAberto(null);
                definirEditando(projeto.projeto?.id ?? null);
              }} />
            )}
            <div className="border-t border-divider" style={{ margin: '4px 0' }} />
            <div className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)', padding: '6px var(--kn-menu-item-px) 4px' }}>
              Só uma pasta: o Claude trabalha nela e segue o CLAUDE.md dela
            </div>
            <div className="flex items-center" style={{ gap: 6, padding: '4px var(--kn-menu-item-px) 8px' }}>
              <input
                value={colado}
                onChange={(e) => definirColado(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && colado.trim() && trocar(colado, projeto.modo, null)}
                placeholder="Cole o caminho da pasta"
                aria-label="Caminho da pasta do projeto"
                className="flex-1 min-w-0 bg-transparent outline-none text-text-primary placeholder:text-text-secondary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
                style={{ fontSize: 'var(--et-chip-texto)', borderRadius: 'var(--mac-campo-raio)', padding: '6px 8px' }}
              />
              <Botao tipo="destaque" onClick={() => trocar(colado, projeto.modo, null)} disabled={!colado.trim()}>
                Abrir
              </Botao>
            </div>
            {erro && (
              <div className="text-[var(--erro)]" style={{ fontSize: 'var(--et-chip-texto)', padding: '0 var(--kn-menu-item-px) 6px' }}>
                {erro}
              </div>
            )}
            {projeto.recentes.map((p) => (
              <Item
                key={p}
                marcado={!projeto.projeto && p === projeto.pasta}
                titulo={nomeDaPasta(p)}
                dica={p}
                aoEscolher={() => trocar(p, projeto.modo, null)}
              />
            ))}
            <div className="border-t border-divider" style={{ margin: '4px 0' }} />
            <Item
              marcado={!projeto.projeto && !projeto.pasta}
              titulo="Sem projeto"
              dica="Na pasta de trabalho do Solis"
              aoEscolher={() => trocar(null, projeto.modo === 'aceitar' ? 'pedir' : projeto.modo, null)}
            />
          </Menu>
        )}
      </div>

      <div className="relative">
        <button
          type="button"
          className={botao}
          style={estilo}
          aria-haspopup="menu"
          aria-expanded={aberto === 'modo'}
          title={modo.dica}
          onClick={() => definirAberto((a) => (a === 'modo' ? null : 'modo'))}
        >
          {modo.nome}
          <Icone nome="chevron" tamanho={14} style={{ transform: aberto === 'modo' ? 'rotate(180deg)' : undefined }} />
        </button>
        {aberto === 'modo' && (
          <Menu aoFechar={() => definirAberto(null)} largura={360}>
            {MODOS.map((m) => (
              <Item
                key={m.id}
                marcado={m.id === projeto.modo}
                titulo={m.nome}
                dica={m.id === 'aceitar' && !projeto.pasta ? 'Só com uma pasta de projeto aberta.' : m.dica}
                desligado={m.id === 'aceitar' && !projeto.pasta}
                aoEscolher={() => trocar(projeto.pasta, m.id)}
              />
            ))}
          </Menu>
        )}
      </div>

      {projeto.pasta && <PainelGit conversa={conversa} respondendo={respondendo} />}

      {editando !== null && (
        <EditorProjeto
          id={editando === 'novo' ? null : editando}
          aoFechar={() => definirEditando(null)}
          aoSalvar={(p, novo) => {
            definirEditando(null);
            // Novo: a conversa entra nele. Editado: relê (o nome ou a pasta mudaram).
            if (novo) void trocar(null, projeto.modo === 'aceitar' && !p.pasta ? 'pedir' : projeto.modo, p.id);
            else if (conversa !== null) void lerProjeto(conversa).then((r) => r && definirProjeto(r));
          }}
          aoApagar={() => {
            definirEditando(null);
            if (conversa !== null) void lerProjeto(conversa).then((r) => r && definirProjeto(r));
          }}
        />
      )}
    </div>
  );
}
