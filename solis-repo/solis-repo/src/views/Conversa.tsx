import { Icone, type NomeIcone } from '../components/icons';

/** Tela de Conversa — estado de abertura.
 *
 *  Medidas de docs/MEDICOES_FASE2.md, normalizadas pra janela de 1440px.
 *  Referências: referencias/telas/tema-dark.png, tema-espacial-vinho.png,
 *  tema-claro-padrao.png (as 3 mostram esta mesma tela).
 *
 *  O microfone está aqui porque a decisão registrada é que ele sumiu das 3
 *  telas por omissão do gerador de imagem, não por decisão de produto: Whisper
 *  e a Camada 3 do SOLIS_SIGNATURE.md dependem dele como porta de entrada. */

const ATALHOS: { rotulo: string; icone: NomeIcone }[] = [
  { rotulo: 'Nova tarefa', icone: 'nova-tarefa' },
  { rotulo: 'Buscar algo', icone: 'buscar' },
  { rotulo: 'Resumir', icone: 'resumir' },
  { rotulo: 'Analisar', icone: 'analisar' },
];

export function Conversa({ aoAbrirThread }: { aoAbrirThread?: () => void } = {}) {
  return (
    <main className="relative flex-1 overflow-y-auto" style={{ zIndex: 1 }}>
      {/* 191px da divisória da sidebar. O topo é 298 e não 295 porque a Playfair
          tem métrica diferente da serifada genérica que estava antes: a mesma caixa
          punha a tinta 3px mais alto. */}
      {/* No modo 'icones' não há sidebar, e a referência mostra a coluna
          centralizada na janela em vez de encostada à esquerda. A troca é só de
          CSS, por atributo na raiz — o componente não precisa saber do modo. */}
      <div className="conversa-coluna" style={{ paddingLeft: 191, paddingTop: 298 }}>
        <h1 className="font-display text-hero text-text-primary leading-none">Olá, Matheus.</h1>

        {/* subtítulo a 359px do topo */}
        <p className="text-text-secondary" style={{ marginTop: 21, fontSize: 20 }}>
          Como posso te ajudar hoje?
        </p>

        {/* composer a 422px do topo, 802×79, raio 13 */}
        <form
          className="flex items-center border border-divider rounded-composer"
          style={{ marginTop: 44, width: 'var(--composer-width)', height: 'var(--composer-height)' }}
          onSubmit={(e) => {
            e.preventDefault();
            aoAbrirThread?.();
          }}
        >
          <input
            className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
            style={{ paddingLeft: 29, fontSize: 16 }}
            placeholder="Fale com o Solis…"
            aria-label="Fale com o Solis"
          />
          <button type="button" className="text-text-secondary p-sm" aria-label="Falar">
            <Icone nome="microfone" tamanho={19} />
          </button>
          <button type="submit" className="text-accent p-sm" style={{ marginRight: 18 }} aria-label="Enviar">
            <Icone nome="enviar" tamanho={19} />
          </button>
        </form>

        {/* chips 34px abaixo do composer, altura 56, vão de 22 */}
        <div className="flex" style={{ marginTop: 32, gap: 22 }}>
          {ATALHOS.map((a) => (
            <button
              key={a.rotulo}
              type="button"
              className="flex items-center gap-md border border-divider rounded-md text-text-primary"
              style={{ height: 'var(--chip-height)', paddingLeft: 21, paddingRight: 22, fontSize: 15 }}
            >
              <span className="text-accent"><Icone nome={a.icone} tamanho={17} /></span>
              {a.rotulo}
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
