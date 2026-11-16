import { useEffect, useState } from 'react';
import { lerUso, type Uso } from '../servidor';
import { quando } from './CartaoAgendadas';

/** Configurações → Uso: quanto da cota do Claude já foi (a sessão de 5 horas,
 *  a semana) e quando volta — como Configurações → Uso no Claude Desktop
 *  (backend/solis/uso.py, pelo /usage do CLI, que não gasta cota).
 *
 *  Aprovado pelo Matheus em 15/11/2026 nos 3 temas e 2 navs — desenho próprio:
 *  o cartão e as linhas do de Cérebros (layout.configuracoes.cerebros), o "Ver
 *  de novo" dos Conectores e uma barra fina por cota (layout.configuracoes.uso). */

function Barra({ usado }: { usado: number }) {
  const cheia = usado >= 90;
  return (
    <div
      role="progressbar"
      aria-valuenow={usado}
      aria-valuemin={0}
      aria-valuemax={100}
      className="w-full overflow-hidden"
      style={{ height: 'var(--uso-barra-h)', borderRadius: 999, background: 'var(--divider)', marginTop: 'var(--uso-barra-top)' }}
    >
      <div
        style={{
          height: '100%',
          width: `${Math.min(100, Math.max(0, usado))}%`,
          borderRadius: 999,
          background: cheia ? 'var(--erro)' : 'var(--accent)',
        }}
      />
    </div>
  );
}

export function CartaoUso() {
  // undefined = lendo; null = não deu.
  const [uso, definirUso] = useState<Uso | null | undefined>(undefined);
  const ler = (atualizar = false) => {
    definirUso(undefined);
    void lerUso(atualizar).then(definirUso);
  };
  useEffect(() => ler(), []);

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;

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
      <div className="flex items-start justify-between" style={{ gap: 'var(--cer-controles-gap)' }}>
        <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Uso</h2>
        <button
          type="button"
          onClick={() => ler(true)}
          disabled={uso === undefined}
          className="text-text-secondary hover:text-text-primary hover:underline disabled:opacity-50 shrink-0"
          style={{ fontSize: 'var(--cfg-dica)' }}
        >
          Ver de novo
        </button>
      </div>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        Quanto da sua cota do Claude{uso?.plano ? ` (${uso.plano})` : ''} já foi, aqui e no Claude Code, e quando volta. O
        GPT e os outros cérebros têm a cota deles.
      </p>

      {uso === undefined && (
        <p className="text-text-secondary" style={{ ...dica, marginTop: 'var(--cer-linha-pad)' }}>Vendo o uso… leva alguns segundos.</p>
      )}
      {uso === null && (
        <p className="text-text-secondary" style={{ ...dica, marginTop: 'var(--cer-linha-pad)' }}>
          Não consegui ver o uso agora: o servidor do Solis ou o Claude não respondeu.
        </p>
      )}
      {uso?.cotas.map((c) => (
        <div key={c.tipo} className="border-t border-divider" style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' }}>
          <div className="flex items-baseline justify-between" style={{ gap: 'var(--cer-controles-gap)' }}>
            <span className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>{c.rotulo}</span>
            <span className={c.usado >= 90 ? 'text-[var(--erro)]' : 'text-text-secondary'} style={{ fontSize: 'var(--cfg-dica)' }}>
              {c.usado}% usado
            </span>
          </div>
          <Barra usado={c.usado} />
          {c.volta && (
            <div className="text-text-secondary" style={dica}>
              {c.usado >= 100 ? 'Acabou. ' : ''}Volta {quando(c.volta)}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
