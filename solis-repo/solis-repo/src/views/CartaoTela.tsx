import { useEffect, useState } from 'react';
import { Interruptor } from '../components/Controles';
import { lerTela, ligarTela, type Tela } from '../servidor';

/** Configurações → Controle da tela: deixar o Solis ver a tela e clicar,
 *  digitar e apertar teclas em qualquer programa, como o computer use do
 *  Claude Desktop (backend/solis/tela.py), com qualquer cérebro (o Claude pelo
 *  print, os de API pelo texto da tela: corpo.py). Desligado até o Matheus ligar.
 *  O texto dizia "o Claude"; trocado pra "o Solis" a pedido dele (19/11/2026).
 *
 *  Aprovado pelo Matheus em 16/11/2026 nos 3 temas e 2 navs — desenho próprio:
 *  o cartão e uma linha do de Cérebros (layout.configuracoes.cerebros) com o
 *  interruptor da Aparência. Ver layout.configuracoes.tela. */

export function CartaoTela() {
  const [tela, definirTela] = useState<Tela | null | undefined>(undefined);
  const [erro, definirErro] = useState('');
  useEffect(() => {
    void lerTela().then(definirTela);
  }, []);

  const trocar = async (ligada: boolean) => {
    definirErro('');
    const r = await ligarTela(ligada);
    if (r) definirTela(r);
    else definirErro('Não consegui trocar agora: o servidor do Solis não respondeu.');
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;

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
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Controle da tela</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        O Solis vê a tela e clica, digita e aperta teclas em qualquer programa, pra o que não tem outro jeito. Cada
        ação pede você antes, com o print marcado onde ele vai clicar. Na janela do Solis ele não mexe.
      </p>

      {tela === undefined && <p className="text-text-secondary" style={{ ...dica, ...linha }}>Vendo…</p>}
      {tela === null && (
        <p className="text-text-secondary" style={{ ...dica, ...linha }}>
          Servidor do Solis desligado. Iniciar com npm run backend.
        </p>
      )}
      {tela && (
        <div className="flex items-center justify-between border-t border-divider" style={{ ...linha, gap: 'var(--cer-controles-gap)' }}>
          <div className="min-w-0">
            <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Deixar o Solis controlar a tela</div>
            <div className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
              {!tela.disponivel
                ? 'Só funciona no Windows.'
                : 'Ligado, o que estiver na tela vai pro cérebro que responder (Claude, Groq, Gemini, na nuvem) quando ele olhar: feche o que for privado antes. Só a tela principal.'}
            </div>
          </div>
          <Interruptor
            ligado={tela.ligada}
            rotulo="Deixar o Solis controlar a tela"
            aoTrocar={tela.disponivel ? (v) => void trocar(v) : undefined}
          />
        </div>
      )}
      {erro && (
        <div className="text-[var(--erro)]" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
          {erro}
        </div>
      )}
    </section>
  );
}
