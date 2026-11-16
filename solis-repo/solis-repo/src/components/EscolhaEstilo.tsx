import { useEffect, useRef, useState } from 'react';
import { escolherEstilo, listarEstilos, type Estilos } from '../servidor';
import { Icone } from './icons';

/** O estilo de resposta, no campo de digitar — como os estilos do claude.ai
 *  (backend/solis/estilos.py). Vale pra toda resposta, de qualquer cérebro,
 *  até trocar.
 *
 *  PROVISÓRIO — desenho próprio (15/11/2026), precisa da aprovação do Matheus:
 *  o botão da Pesquisa (no Normal, só o ícone; num estilo, a pílula em accent
 *  com o nome) e o menu do seletor de modelo (--kn-menu-*), abrindo pra cima.
 *  Ver layout.thread.estilo no solis-tokens.json. */

function Opcao({ marcada, aoEscolher, nome, dica }: { marcada: boolean; aoEscolher: () => void; nome: string; dica?: string }) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={marcada}
      onClick={aoEscolher}
      title={dica}
      className="flex items-center justify-between w-full text-left text-text-primary hover:bg-[var(--mem-hover)]"
      style={{
        height: 'var(--kn-menu-item-h)',
        padding: '0 var(--kn-menu-item-px)',
        borderRadius: 'calc(var(--kn-menu-raio) - var(--kn-menu-pad))',
        fontSize: 'var(--mac-botao-texto)',
        gap: 8,
      }}
    >
      <span className="truncate">{nome}</span>
      {marcada && <Icone nome="feito" tamanho="var(--mac-icone)" className="text-accent shrink-0" />}
    </button>
  );
}

function Titulo({ children }: { children: string }) {
  return (
    <div className="text-text-secondary" style={{ fontSize: 'var(--et-chip-texto)', padding: '8px var(--kn-menu-item-px) 4px' }}>
      {children}
    </div>
  );
}

export function EscolhaEstilo({ aoCriar }: { aoCriar?: () => void }) {
  const [estilos, definirEstilos] = useState<Estilos | null>(null);
  const [aberto, definirAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void listarEstilos().then(definirEstilos);
  }, []);
  // Aberto o menu, lê de novo: um estilo pode ter sido criado em Configurações.
  useEffect(() => {
    if (aberto) void listarEstilos().then((e) => e && definirEstilos(e));
  }, [aberto]);

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

  if (!estilos) return null;
  const atual = estilos.estilos.find((e) => e.id === estilos.atual) ?? estilos.estilos[0];
  const ligado = atual.id !== 'normal';
  const escolher = async (id: string) => {
    definirAberto(false);
    const r = await escolherEstilo(id);
    if (r) definirEstilos(r);
  };
  const seus = estilos.estilos.filter((e) => e.seu);

  return (
    <div ref={caixa} className="relative shrink-0">
      <button
        type="button"
        onClick={() => definirAberto((a) => !a)}
        aria-haspopup="menu"
        aria-expanded={aberto}
        aria-label={`Estilo da resposta: ${atual.nome}`}
        title="O estilo da resposta: como o Solis escreve"
        className={`flex items-center justify-center ${ligado ? 'text-accent' : 'text-text-secondary hover:text-text-primary'}`}
        style={{
          height: 'var(--mac-alvo)',
          minWidth: 'var(--mac-alvo)',
          padding: ligado ? '0 12px 0 10px' : 0,
          gap: 6,
          borderRadius: 999,
          fontSize: 'var(--et-dobra-texto)',
          background: ligado ? 'color-mix(in srgb, var(--accent) var(--et-chip-fundo), transparent)' : undefined,
          border: ligado ? '1px solid color-mix(in srgb, var(--accent) var(--et-chip-borda), transparent)' : '1px solid transparent',
        }}
      >
        <Icone nome="estilo" tamanho={20} />
        {ligado && <span className="truncate" style={{ maxWidth: 'var(--est-pilula-max)' }}>{atual.nome}</span>}
      </button>
      {aberto && (
        <div
          role="menu"
          aria-label="Estilo da resposta"
          className="absolute left-0 z-10 border border-divider bg-canvas"
          style={{
            bottom: 'calc(100% + var(--kn-menu-top))',
            width: 'var(--kn-menu-l)',
            padding: 'var(--kn-menu-pad)',
            borderRadius: 'var(--kn-menu-raio)',
            boxShadow: '0 8px 24px rgb(0 0 0 / 0.25)',
          }}
        >
          <Titulo>Estilo da resposta</Titulo>
          {estilos.estilos
            .filter((e) => !e.seu)
            .map((e) => (
              <Opcao key={e.id} marcada={e.id === atual.id} aoEscolher={() => void escolher(e.id)} nome={e.nome} dica={e.instrucoes} />
            ))}
          {seus.length > 0 && (
            <>
              <div className="border-t border-divider" style={{ margin: '6px 0' }} />
              <Titulo>Seus</Titulo>
              {seus.map((e) => (
                <Opcao key={e.id} marcada={e.id === atual.id} aoEscolher={() => void escolher(e.id)} nome={e.nome} dica={e.instrucoes} />
              ))}
            </>
          )}
          {aoCriar && (
            <>
              <div className="border-t border-divider" style={{ margin: '6px 0' }} />
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  definirAberto(false);
                  aoCriar();
                }}
                className="flex items-center w-full text-left text-text-secondary hover:text-text-primary hover:bg-[var(--mem-hover)]"
                style={{
                  height: 'var(--kn-menu-item-h)',
                  padding: '0 var(--kn-menu-item-px)',
                  borderRadius: 'calc(var(--kn-menu-raio) - var(--kn-menu-pad))',
                  fontSize: 'var(--mac-botao-texto)',
                }}
              >
                Criar ou editar estilos
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
