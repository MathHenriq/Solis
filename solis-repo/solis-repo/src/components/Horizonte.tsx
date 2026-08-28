/** Camada 1 da assinatura (SOLIS_SIGNATURE.md): o horizonte.
 *
 *  Renderizado UMA VEZ no shell e nunca remontado ao trocar de tela — o
 *  documento exige, e importa mais ainda agora que é uma foto por tema.
 *  Fica atrás do conteúdo e nunca compete com texto.
 *
 *  Movimento: ciclo de 90s, variação mínima, só transform e opacity
 *  (PERFORMANCE.md). A regra prática do documento é que se alguém consegue
 *  apontar quando o ciclo "bate", está rápido demais.
 *
 *  Cada tema tem a SUA foto — não há mais cena compartilhada, e o dark não é
 *  mais um arco sintético em CSS. Qual foto vem do tema, por custom property;
 *  este componente não sabe nada sobre temas.
 *
 *  A cena é uma BANDA ancorada na base da área de conteúdo, não um fundo de
 *  tela cheia: "ocupando a parte inferior de toda tela", no texto da Camada 1,
 *  e é o que as 3 referências mostram. Esticá-la atrás da tela inteira punha
 *  texto em cima de foto e derrubava o contraste. Toda a geometria (altura,
 *  ancoragem vertical, máscara do topo) vem de tokens gerados do JSON — ver
 *  .cena-camada em src/styles/index.css.
 *
 *  São dois elementos porque a máscara e o recorte moram no de fora, que é
 *  estático: o de dentro é o que anima, e uma máscara no elemento animado
 *  passearia junto com o scale.
 *
 *  Se o arquivo da cena não existir, a camada simplesmente não pinta e sobra o
 *  canvas sólido do tema — o mesmo caminho de "Exibir imagem de fundo"
 *  desligado. É um estado que o produto já tem, não uma falha. */
export function Horizonte() {
  return (
    <div aria-hidden className="cena-camada pointer-events-none fixed overflow-hidden" style={{ zIndex: 0 }}>
      <div
        className="cena absolute inset-0 animate-solis-horizon"
        style={{ willChange: 'transform, opacity' }}
      />
    </div>
  );
}
