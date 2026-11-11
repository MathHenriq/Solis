import { useEffect, useRef, useState } from 'react';
import { guardarAjustesClaude, lerAjustesClaude, type AjustesClaude } from '../servidor';
import { Icone } from './icons';

/** O modelo do Claude e o quanto ele pensa, no campo de digitar — como o
 *  seletor do Claude Desktop (docs/PARIDADE.md). Vale pra toda resposta do
 *  Claude a partir da próxima; os outros cérebros não mudam.
 *
 *  PROVISÓRIO — desenho próprio (11/11/2026), base no Claude: o nome do modelo
 *  em texto secundário dentro do campo, e o menu abrindo pra cima, na caixa
 *  dos menus do Conhecimento (layout.conhecimento, --kn-menu-*). */

const MODELO: Record<string, string> = { fable: 'Fable', opus: 'Opus', sonnet: 'Sonnet', haiku: 'Haiku' };
const ESFORCO: Record<string, string> = {
  low: 'Pouco',
  medium: 'Médio',
  high: 'Alto',
  xhigh: 'Muito alto',
  max: 'Máximo',
};

function Opcao({ marcada, aoEscolher, children }: { marcada: boolean; aoEscolher: () => void; children: string }) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={marcada}
      onClick={aoEscolher}
      className="flex items-center justify-between w-full text-left text-text-primary hover:bg-[var(--mem-hover)]"
      style={{
        height: 'var(--kn-menu-item-h)',
        padding: '0 var(--kn-menu-item-px)',
        borderRadius: 'calc(var(--kn-menu-raio) - var(--kn-menu-pad))',
        fontSize: 'var(--mac-botao-texto)',
      }}
    >
      {children}
      {marcada && <Icone nome="feito" tamanho="var(--mac-icone)" className="text-accent" />}
    </button>
  );
}

function Titulo({ children }: { children: string }) {
  return (
    <div
      className="text-text-secondary"
      style={{ fontSize: 'var(--et-chip-texto)', padding: '8px var(--kn-menu-item-px) 4px' }}
    >
      {children}
    </div>
  );
}

export function EscolhaClaude() {
  const [ajustes, definirAjustes] = useState<AjustesClaude | null>(null);
  const [aberto, definirAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    lerAjustesClaude().then(definirAjustes);
  }, []);

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

  // Sem servidor, não há o que escolher: o seletor some.
  if (!ajustes) return null;

  const escolher = async (modelo: string | null, esforco: string | null) => {
    const novos = await guardarAjustesClaude(modelo, esforco);
    if (novos) definirAjustes(novos);
  };
  const rotulo =
    (ajustes.modelo ? MODELO[ajustes.modelo] ?? ajustes.modelo : 'Claude') +
    (ajustes.esforco ? ` · ${ESFORCO[ajustes.esforco] ?? ajustes.esforco}` : '');

  return (
    <div ref={caixa} className="relative shrink-0">
      <button
        type="button"
        onClick={() => definirAberto((a) => !a)}
        aria-haspopup="menu"
        aria-expanded={aberto}
        aria-label={`Modelo do Claude: ${rotulo}`}
        title="O modelo do Claude e o quanto ele pensa"
        className="flex items-center text-text-secondary hover:text-text-primary"
        style={{ height: 'var(--mac-alvo)', padding: '0 8px', gap: 4, fontSize: 'var(--mac-botao-texto)', borderRadius: 'var(--mac-botao-raio)' }}
      >
        {rotulo}
        <Icone nome="chevron" tamanho={16} style={{ transform: aberto ? 'rotate(180deg)' : undefined }} />
      </button>
      {aberto && (
        <div
          role="menu"
          aria-label="Modelo do Claude"
          className="absolute right-0 z-10 border border-divider bg-canvas"
          style={{
            bottom: 'calc(100% + var(--kn-menu-top))',
            width: 'var(--kn-menu-l)',
            padding: 'var(--kn-menu-pad)',
            borderRadius: 'var(--kn-menu-raio)',
            boxShadow: '0 8px 24px rgb(0 0 0 / 0.25)',
          }}
        >
          <Titulo>Modelo do Claude</Titulo>
          <Opcao marcada={ajustes.modelo === null} aoEscolher={() => escolher(null, ajustes.esforco)}>
            Padrão da conta
          </Opcao>
          {ajustes.modelos.map((m) => (
            <Opcao key={m} marcada={ajustes.modelo === m} aoEscolher={() => escolher(m, ajustes.esforco)}>
              {MODELO[m] ?? m}
            </Opcao>
          ))}
          <div className="border-t border-divider" style={{ margin: '6px 0' }} />
          <Titulo>Quanto ele pensa</Titulo>
          <Opcao marcada={ajustes.esforco === null} aoEscolher={() => escolher(ajustes.modelo, null)}>
            Padrão
          </Opcao>
          {ajustes.esforcos.map((e) => (
            <Opcao key={e} marcada={ajustes.esforco === e} aoEscolher={() => escolher(ajustes.modelo, e)}>
              {ESFORCO[e] ?? e}
            </Opcao>
          ))}
        </div>
      )}
    </div>
  );
}
