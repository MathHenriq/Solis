import { useEffect, useRef, useState } from 'react';
import { pararFundo, type ComandoFundo } from '../servidor';
import { Botao } from './Controles';
import { SaidaTerminal } from './EtapasResposta';
import { Icone } from './icons';

/** Os comandos que o Claude deixou rodando em segundo plano (um servidor, um
 *  teste longo), à direita da barra do projeto — como o Claude Code mostra
 *  as tarefas em segundo plano. Abre pra cima: cada comando com o fim da
 *  saída e o Parar.
 *
 *  PROVISÓRIO — desenho próprio (12/11/2026), base no Claude Code: o botão no
 *  texto secundário da barra do projeto, com o ponto da etapa atual; a caixa
 *  dos menus do Conhecimento (--kn-menu-*) e a saída no terminal da conversa
 *  (layout.thread.etapas._background no solis-tokens.json). */

const tempo = (s: number) => (s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min` : `${Math.floor(s / 3600)} h`);

export function ComandosFundo({ conversa, comandos }: { conversa: number | null; comandos: ComandoFundo[] }) {
  const [aberto, definirAberto] = useState(false);
  const [parando, definirParando] = useState<Set<string>>(new Set());
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => !caixa.current?.contains(e.target as Node) && definirAberto(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && definirAberto(false);
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc);
    };
  }, [aberto]);
  useEffect(() => {
    if (!comandos.length) definirAberto(false);
  }, [comandos.length]);

  if (conversa === null || !comandos.length) return null;
  const n = comandos.length;

  return (
    <div ref={caixa} className="relative">
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={aberto}
        onClick={() => definirAberto((a) => !a)}
        className="flex items-center text-text-secondary hover:text-text-primary"
        style={{ gap: 8, fontSize: 'var(--et-dobra-texto)', height: 28 }}
      >
        <span className="bg-accent shrink-0" style={{ width: 'var(--et-ponto)', height: 'var(--et-ponto)', borderRadius: 999 }} />
        {n === 1 ? '1 comando em segundo plano' : `${n} comandos em segundo plano`}
        <Icone nome="chevron" tamanho={14} style={{ transform: aberto ? 'rotate(180deg)' : undefined }} />
      </button>
      {aberto && (
        <div
          role="dialog"
          aria-label="Comandos em segundo plano"
          className="absolute right-0 z-10 border border-divider bg-canvas flex flex-col overflow-y-auto"
          style={{
            bottom: 'calc(100% + var(--kn-menu-top))',
            width: 'var(--fundo-largura)',
            maxHeight: '60vh',
            padding: 'var(--kn-menu-pad)',
            gap: 'var(--kn-menu-pad)',
            borderRadius: 'var(--kn-menu-raio)',
            boxShadow: '0 8px 24px rgb(0 0 0 / 0.25)',
          }}
        >
          {comandos.map((c) => (
            <div key={c.id} style={{ padding: '8px var(--kn-menu-item-px)' }}>
              <div className="flex items-start justify-between" style={{ gap: 12 }}>
                <div className="min-w-0">
                  <div className="text-text-primary truncate" title={c.descricao} style={{ fontSize: 'var(--mac-botao-texto)' }}>
                    {c.descricao || 'Comando'}
                  </div>
                  <div className="text-text-secondary truncate" title={c.comando} style={{ fontSize: 'var(--et-chip-texto)' }}>
                    <span className="font-mono">{c.comando}</span> · há {tempo(c.segundos)}
                  </div>
                </div>
                <Botao
                  disabled={parando.has(c.id)}
                  onClick={async () => {
                    definirParando((p) => new Set(p).add(c.id));
                    await pararFundo(conversa, c.id);
                  }}
                >
                  {parando.has(c.id) ? 'Parando…' : 'Parar'}
                </Botao>
              </div>
              <div style={{ marginTop: 8 }}>
                <SaidaTerminal texto={c.saida || '(nada ainda)'} rotulo={`Saída de ${c.descricao || c.comando}`} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
