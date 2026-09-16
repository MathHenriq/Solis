import { useState } from 'react';
import { Icone, type NomeIcone } from '../components/icons';

/** Tela de Conversa — estado de abertura.
 *
 *  Medidas de docs/MEDICOES_FASE2.md, normalizadas pra janela de 1440px.
 *  Referências: referencias/telas/tema-dark.png, tema-espacial-vinho.png,
 *  tema-claro-padrao.png (as 3 mostram esta mesma tela).
 *
 *  O microfone está aqui porque a decisão registrada é que ele sumiu das 3
 *  telas por omissão do gerador de imagem, não por decisão de produto: Whisper
 *  e a Camada 3 do SOLIS_SIGNATURE.md dependem dele como porta de entrada.
 *
 *  Enviar texto daqui abre a Thread E manda a mensagem pro modelo local (ver
 *  lib/useConversa). A tela não espera a resposta: quem desenha o estado de
 *  "gerando" é a Thread, com o cursor. */

const ATALHOS: { rotulo: string; icone: NomeIcone }[] = [
  { rotulo: 'Nova tarefa', icone: 'nova-tarefa' },
  { rotulo: 'Buscar algo', icone: 'buscar' },
  { rotulo: 'Resumir', icone: 'resumir' },
  { rotulo: 'Analisar', icone: 'analisar' },
];

/** Microfone e envio. Renderizado duas vezes: uma de verdade à direita do campo
 *  e uma invisível à esquerda, como espelho — ver o comentário no form. */
function Acoes({ interativo = false }: { interativo?: boolean } = {}) {
  return (
    <>
      <button
        type="button"
        className="text-text-secondary p-sm"
        aria-label={interativo ? 'Falar' : undefined}
        aria-hidden={!interativo}
        tabIndex={interativo ? undefined : -1}
      >
        <Icone nome="microfone" tamanho={19} />
      </button>
      <button
        type={interativo ? 'submit' : 'button'}
        className="text-accent p-sm"
        style={{ marginRight: 18 }}
        aria-label={interativo ? 'Enviar' : undefined}
        aria-hidden={!interativo}
        tabIndex={interativo ? undefined : -1}
      >
        <Icone nome="enviar" tamanho={19} />
      </button>
    </>
  );
}

export function Conversa({
  aoAbrirThread,
  aoEnviar,
}: { aoAbrirThread?: () => void; aoEnviar?: (texto: string) => void } = {}) {
  const [texto, definirTexto] = useState('');

  return (
    <main className="tela-conversa relative flex-1 overflow-y-auto" style={{ zIndex: 1 }}>
      {/* 191px da divisória da sidebar. O topo é 298 e não 295 porque a Playfair
          tem métrica diferente da serifada genérica que estava antes: a mesma caixa
          punha a tinta 3px mais alto. Esses 298 são o TETO: numa janela de 930 de
          altura é exatamente o que sai; numa de 693, que é o que um navegador dá,
          298 seriam 43% da altura e jogavam o bloco inteiro pra metade de baixo,
          espremendo o horizonte. Ver layout.escalaVertical. */}
      {/* No modo 'icones' não há sidebar, e a referência mostra a coluna
          centralizada na janela em vez de encostada à esquerda. A troca é só de
          CSS, por atributo na raiz — o componente não precisa saber do modo. */}
      {/* A coluna acompanha a largura do composer. Sem isso os chips e o campo
          ficavam com medidas independentes, e numa janela larga um esticava e o
          outro não — que é o tipo de desalinho que só aparece fora dos 1440px em
          que a referência foi medida. */}
      {/* Nenhuma geometria aqui: largura, âncora, teto e o topo vivem todos no
          CSS (.conversa-coluna em index.css). O topo estava neste style inline, e
          inline vence qualquer seletor — então a regra do modo 'icones', que
          precisa zerar o topo pra centralizar o bloco na faixa, era silenciosamente
          ignorada. */}
      <div className="conversa-coluna">
        <h1 className="font-display text-hero text-text-primary leading-none">Olá, Matheus.</h1>

        {/* subtítulo a 359px do topo */}
        <p className="text-text-secondary" style={{ marginTop: 'var(--conversa-sub)', fontSize: 20 }}>
          Como posso te ajudar hoje?
        </p>

        {/* composer a 422px do topo, 802×79, raio 13 */}
        {/* Mesma superfície dos atalhos logo abaixo. Transparente, sobre a foto do
            horizonte, o contorno fino sozinho não fechava o retângulo e o campo
            flutuava — o mesmo defeito que os chips já tinham tido. O véu é o do
            próprio canvas, então não opaca a foto atrás; e o focus-within troca
            pelo véu forte, que é como o resto do sistema marca "estou aqui". */}
        <form
          className="flex items-center border border-divider rounded-composer
                     bg-[var(--mem-hover)] focus-within:bg-[var(--mem-hover-forte)]"
          style={{ marginTop: 'var(--conversa-campo)', width: '100%', height: 'var(--composer-height)' }}
          onSubmit={(e) => {
            e.preventDefault();
            // Campo vazio continua abrindo a Thread sem mandar nada: é por aí
            // que design/capturar-todas.mjs chega no segundo estado da tela pra
            // conferir contra a referência. Com texto, a mensagem vai pro
            // modelo e a Thread abre já com ela.
            const limpo = texto.trim();
            if (limpo) {
              definirTexto('');
              aoEnviar?.(limpo);
            }
            aoAbrirThread?.();
          }}
        >
          {/* Espelho do bloco de ações, à esquerda do campo.
              No modo 'icones' o texto do campo é centralizado, e centralizado
              DENTRO DA CAIXA DO INPUT — que é 89px mais curta que o form, porque
              o microfone e a seta ocupam a direita. O texto caía 30px à esquerda
              do eixo (−44,5 da meia-caixa, +14,5 do padding), e era isso o torto:
              tudo o mais na tela passava pelo eixo, menos o placeholder.

              O espelho carrega os controles DE VERDADE, invisíveis: assim a
              largura dos dois lados é a mesma por construção e não pode divergir
              se um ícone mudar de tamanho. `visibility: hidden` e não `display:
              none` justamente porque só o primeiro reserva o espaço.
              No modo sidebar o texto é alinhado à esquerda e o espelho some. */}
          <span className="composer-espelho" aria-hidden>
            <Acoes />
          </span>
          <input
            className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
            style={{ fontSize: 16 }}
            placeholder="Fale com o Solis…"
            aria-label="Fale com o Solis"
            value={texto}
            onChange={(e) => definirTexto(e.target.value)}
          />
          <Acoes interativo />
        </form>

        {/* chips 34px abaixo do composer, altura 56, vão de 22 */}
        <div className="flex" style={{ marginTop: 'var(--conversa-chips)', gap: 18 }}>
          {ATALHOS.map((a) => (
            <button
              key={a.rotulo}
              type="button"
              // Superfície própria em vez de fundo transparente: sobre a foto
              // do horizonte o contorno fino sozinho sumia e o texto flutuava.
              // O véu é o do canvas, então não opaca a foto atrás.
              className="flex items-center gap-md border border-divider rounded-md text-text-primary
                         bg-[var(--mem-hover)] hover:bg-[var(--mem-hover-forte)]"
              style={{
                height: 'var(--chip-height)',
                paddingLeft: 18,
                paddingRight: 19,
                fontSize: 'var(--chip-texto)',
              }}
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
