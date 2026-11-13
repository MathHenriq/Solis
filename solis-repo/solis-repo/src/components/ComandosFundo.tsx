import { useEffect, useRef, useState } from 'react';
import { textoAgora, textoFerramenta } from '../etapas';
import { pararFundo, type ComandoFundo } from '../servidor';
import { Botao } from './Controles';
import { SaidaTerminal } from './EtapasResposta';
import { Icone } from './icons';

/** Os comandos que o Claude deixou rodando em segundo plano (um servidor, um
 *  teste longo) e os ajudantes (subagentes) trabalhando, à direita da barra do projeto — como o Claude Code mostra
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
  const ajudantes = comandos.filter((c) => c.tipo === 'ajudante').length;
  const nComandos = comandos.length - ajudantes;
  const partes = [];
  if (nComandos) partes.push(nComandos === 1 ? '1 comando' : `${nComandos} comandos`);
  if (ajudantes) partes.push(ajudantes === 1 ? '1 ajudante' : `${ajudantes} ajudantes`);
  // "1 comando em segundo plano", "1 ajudante trabalhando", "1 comando e 1 ajudante em segundo plano".
  const rotulo = !nComandos ? `${partes[0]} trabalhando` : `${partes.join(' e ')} em segundo plano`;

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
        {rotulo}
        <Icone nome="chevron" tamanho={14} style={{ transform: aberto ? 'rotate(180deg)' : undefined }} />
      </button>
      {aberto && (
        <div
          role="dialog"
          aria-label="Em segundo plano"
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
                  <div
                    className="text-text-secondary truncate"
                    title={c.comando || (c.agora ? textoAgora(c.agora) : undefined)}
                    style={{ fontSize: 'var(--et-chip-texto)' }}
                  >
                    {c.tipo === 'ajudante' ? (
                      <>
                        {c.agora ? textoAgora(c.agora) : 'Pensando'} · há {tempo(c.segundos)}
                      </>
                    ) : (
                      <>
                        <span className="font-mono">{c.comando}</span> · há {tempo(c.segundos)}
                      </>
                    )}
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
              {c.tipo === 'ajudante' ? (
                // As últimas ações dele, nas frases das etapas da resposta.
                <ol aria-label={`O que ${c.descricao || 'o ajudante'} fez`} style={{ marginTop: 8 }}>
                  {(c.passos ?? []).length === 0 && (
                    <li className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)' }}>
                      Começando…
                    </li>
                  )}
                  {(c.passos ?? []).map((p, i) => (
                    <li
                      key={i}
                      className="flex items-center text-text-secondary"
                      style={{ gap: 8, fontSize: 'var(--et-chip-texto)', height: 24 }}
                    >
                      <Icone nome="feito" tamanho={14} className={p.ok ? 'text-accent shrink-0' : 'text-text-secondary shrink-0'} />
                      <span className="truncate" title={p.alvo}>
                        {textoFerramenta(p)}
                        {p.ok ? '' : ': não deu'}
                      </span>
                    </li>
                  ))}
                </ol>
              ) : (
                <div style={{ marginTop: 8 }}>
                  <SaidaTerminal texto={c.saida || '(nada ainda)'} rotulo={`Saída de ${c.descricao || c.comando}`} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
