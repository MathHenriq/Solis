import { useEffect, useRef, useState, type ReactNode } from 'react';
import { guardarProjeto, lerProjeto, type Projeto } from '../servidor';
import { Botao } from './Controles';
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

  async function trocar(pasta: string | null, modo: Projeto['modo']) {
    if (conversa === null) return;
    const r = await guardarProjeto(conversa, pasta, modo);
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
          title={projeto.pasta ?? 'O Claude trabalha na pasta de trabalho do Solis'}
          onClick={() => definirAberto((a) => (a === 'pasta' ? null : 'pasta'))}
        >
          <Icone nome="arquivos" tamanho={16} />
          {projeto.pasta ? nomeDaPasta(projeto.pasta) : 'Sem projeto'}
          <Icone nome="chevron" tamanho={14} style={{ transform: aberto === 'pasta' ? 'rotate(180deg)' : undefined }} />
        </button>
        {aberto === 'pasta' && (
          <Menu aoFechar={() => definirAberto(null)} largura={380}>
            <div className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)', padding: '6px var(--kn-menu-item-px) 4px' }}>
              Pasta do projeto: o Claude trabalha nela e segue o CLAUDE.md dela
            </div>
            <div className="flex items-center" style={{ gap: 6, padding: '4px var(--kn-menu-item-px) 8px' }}>
              <input
                autoFocus
                value={colado}
                onChange={(e) => definirColado(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && colado.trim() && trocar(colado, projeto.modo)}
                placeholder="Cole o caminho da pasta"
                aria-label="Caminho da pasta do projeto"
                className="flex-1 min-w-0 bg-transparent outline-none text-text-primary placeholder:text-text-secondary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
                style={{ fontSize: 'var(--et-chip-texto)', borderRadius: 'var(--mac-campo-raio)', padding: '6px 8px' }}
              />
              <Botao tipo="destaque" onClick={() => trocar(colado, projeto.modo)} disabled={!colado.trim()}>
                Abrir
              </Botao>
            </div>
            {erro && (
              <div className="text-[var(--erro)]" style={{ fontSize: 'var(--et-chip-texto)', padding: '0 var(--kn-menu-item-px) 6px' }}>
                {erro}
              </div>
            )}
            {projeto.recentes.map((p) => (
              <Item key={p} marcado={p === projeto.pasta} titulo={nomeDaPasta(p)} dica={p} aoEscolher={() => trocar(p, projeto.modo)} />
            ))}
            <div className="border-t border-divider" style={{ margin: '4px 0' }} />
            <Item
              marcado={!projeto.pasta}
              titulo="Sem projeto"
              dica="Na pasta de trabalho do Solis"
              aoEscolher={() => trocar(null, projeto.modo === 'aceitar' ? 'pedir' : projeto.modo)}
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
    </div>
  );
}
