import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Interruptor } from '../components/Controles';
import { Icone } from '../components/icons';
import { definirFalaAutomatica, falaAutomatica } from '../fala';
import { ajustarFala, amostraDeVoz, lerAjustesFala, listarCerebros, type AjustesFala } from '../servidor';

/** Configurações → Voz: como o Solis fala as respostas.
 *
 *  Desenho próprio, aprovado pelo Matheus em 09/11/2026
 *  (design/voz-configuracoes-validacao.png) — com as peças já aprovadas da tela:
 *  a moldura e as linhas do cartão Aparência (layout.configuracoes), o
 *  segmentado da Navegação e o interruptor da imagem de fundo. Nenhuma medida
 *  nova. O seletor de voz é o select do sistema, na largura e altura do
 *  segmentado, e o "Ouvir" ao lado toca uma amostra da voz (gasta um pedido da
 *  cota do Gemini — dito na dica, pra não ser surpresa). */

const NOME_MODELO: Record<string, string> = {
  'gemini-3.8-flash-lite-tts': 'Flash-Lite',
  'gemini-3.8-flash-tts': 'Flash',
};

function Linha({ rotulo, dica, children }: { rotulo: string; dica?: ReactNode; children?: ReactNode }) {
  return (
    <div
      className="flex items-center justify-between border-t border-divider first:border-t-0"
      style={{ paddingTop: 'var(--cfg-linha-pad)', paddingBottom: 'var(--cfg-linha-pad)', gap: 'var(--cer-controles-gap)' }}
    >
      <div className="min-w-0">
        <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>{rotulo}</div>
        {dica && (
          <div
            className="text-text-secondary"
            style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)', textWrap: 'pretty' }}
          >
            {dica}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}

export function CartaoVoz() {
  // undefined = perguntando; null = servidor desligado.
  const [ajustes, definirAjustes] = useState<AjustesFala | null | undefined>(undefined);
  const [temChave, definirTemChave] = useState<boolean | null>(null);
  const [auto, definirAuto] = useState(falaAutomatica);
  const [ouvindo, definirOuvindo] = useState(false);
  const [aviso, definirAviso] = useState<string | null>(null);
  const tocando = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let vivo = true;
    lerAjustesFala().then((a) => vivo && definirAjustes(a));
    listarCerebros().then((l) => vivo && definirTemChave(!!l?.find((c) => c.nome === 'gemini')?.instalado));
    return () => {
      vivo = false;
      tocando.current?.pause();
    };
  }, []);

  async function trocar(campos: { voz?: string; modelo?: string }) {
    const antes = ajustes;
    if (ajustes) definirAjustes({ ...ajustes, ...campos });
    definirAjustes((await ajustarFala(campos)) ?? antes);
  }

  async function ouvir() {
    if (!ajustes || ouvindo) return;
    tocando.current?.pause();
    definirOuvindo(true);
    definirAviso(null);
    const r = await amostraDeVoz(ajustes.voz);
    if (!r || r === 'sem-voz') {
      definirOuvindo(false);
      definirAviso(
        r === 'sem-voz'
          ? 'Nenhuma voz respondeu agora (Gemini, Ava e a local). Tente de novo em instantes.'
          : 'Não consegui tocar a amostra. O servidor do Solis está ligado?',
      );
      return;
    }
    // Se não foi o Gemini que falou (sem chave, ou cota do dia acabou), quem
    // ouviu precisa saber que aquela não é a voz escolhida.
    if (r.voz !== 'gemini') definirAviso('O Gemini não respondeu agora (cota do dia ou sem chave): essa foi a voz de reserva.');
    const url = URL.createObjectURL(r.audio);
    const el = new Audio(url);
    tocando.current = el;
    el.onended = el.onerror = () => {
      URL.revokeObjectURL(url);
      definirOuvindo(false);
    };
    el.play().catch(() => definirOuvindo(false));
  }

  return (
    <section
      className="border border-divider"
      style={{ marginBottom: 'var(--cer-cartao-gap)', borderRadius: 'var(--cfg-card-raio)', padding: 'var(--cfg-card-pad)' }}
    >
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Voz</h2>
      <p
        className="text-text-secondary"
        style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)', textWrap: 'pretty' }}
      >
        Como o Solis fala as respostas. Primeiro a voz do Gemini; se ele chegar ao limite do dia ou cair, a Ava; sem
        internet, e sempre que a conversa tiver algo privado, a voz local.
      </p>

      {ajustes === null && (
        <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cer-linha-pad)' }}>
          Servidor do Solis desligado: a voz fica guardada nele. Iniciar com npm run backend.
        </p>
      )}

      {ajustes && (
        <div style={{ marginTop: 'var(--cfg-linha-pad)' }}>
          <Linha
            rotulo="Voz do Gemini"
            dica={
              temChave === false
                ? 'Sem a chave do Gemini, quem fala é a Ava. Cole a chave em Cérebros, logo acima.'
                : aviso ?? 'Ouvir uma voz gasta um pedido da cota do Gemini.'
            }
          >
            <div className="flex items-center shrink-0" style={{ gap: 'var(--mac-botao-gap)' }}>
              <button
                type="button"
                onClick={ouvir}
                disabled={ouvindo}
                title="Ouvir esta voz"
                aria-label={`Ouvir a voz ${ajustes.voz}`}
                className={`flex items-center justify-center ${ouvindo ? 'text-accent solis-ouvindo' : 'text-text-secondary hover:text-text-primary'}`}
                style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', borderRadius: 'var(--mac-botao-raio)' }}
              >
                <Icone nome="fala" tamanho="var(--mac-icone)" />
              </button>
              <select
                value={ajustes.voz}
                onChange={(e) => trocar({ voz: e.target.value })}
                aria-label="Voz do Gemini"
                className="solis-data bg-canvas text-text-primary border border-divider outline-none focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
                style={{
                  width: 'var(--cfg-seg-l)',
                  height: 'var(--cfg-seg-h)',
                  borderRadius: 'var(--cfg-seg-raio)',
                  padding: '0 var(--mac-campo-px)',
                  fontSize: 'var(--cfg-rotulo)',
                }}
              >
                {ajustes.vozes.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </div>
          </Linha>

          <Linha
            rotulo="Modelo"
            dica="Flash-Lite: cota grátis maior. Flash: um pouco mais natural, mas 10 pedidos por dia no plano grátis."
          >
            <div
              className="flex overflow-hidden border border-divider shrink-0"
              style={{ width: 'var(--cfg-seg-l)', height: 'var(--cfg-seg-h)', borderRadius: 'var(--cfg-seg-raio)' }}
              role="group"
              aria-label="Modelo de voz do Gemini"
            >
              {ajustes.modelos.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => trocar({ modelo: m })}
                  aria-pressed={ajustes.modelo === m}
                  className={`flex-1 ${ajustes.modelo === m ? 'bg-accent text-canvas' : 'text-text-secondary'}`}
                  style={{ fontSize: 'var(--cfg-rotulo)' }}
                >
                  {NOME_MODELO[m] ?? m}
                </button>
              ))}
            </div>
          </Linha>

          <Linha rotulo="Responder falando" dica="Quando você fala com o microfone, a resposta é lida em voz alta">
            <Interruptor
              ligado={auto}
              rotulo="Responder falando"
              aoTrocar={(v) => {
                definirAuto(v);
                definirFalaAutomatica(v);
              }}
            />
          </Linha>
        </div>
      )}
    </section>
  );
}
