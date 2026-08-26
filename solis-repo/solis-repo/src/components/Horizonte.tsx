/** Camada 1 da assinatura (SOLIS_SIGNATURE.md): o horizonte.
 *
 *  Renderizado UMA VEZ no shell e nunca remontado ao trocar de tela — é o que
 *  o documento exige, e importa mais ainda nos temas fotográficos, onde é um
 *  asset pesado. Fica atrás do conteúdo e nunca compete com texto.
 *
 *  Movimento: ciclo de 90s, variação mínima, só transform e opacity
 *  (PERFORMANCE.md). A regra prática do documento é que se alguém consegue
 *  apontar quando o ciclo "bate", está rápido demais.
 *
 *  PENDENTE 0a — `espacial` e `claro` usam uma cena fotográfica que ainda não
 *  está no repositório. Enquanto ela não chega, os dois caem no canvas sólido,
 *  que é o mesmo caminho de "Exibir imagem de fundo" desligado: um estado que
 *  o produto já tem, não um placeholder inventado. */

/* Geometria medida em referencias/telas/tema-dark.png, normalizada pra janela
   de 1440×930: a linha do horizonte é uma parábola de vértice (750, 856) que
   sai pelo rodapé em x≈129 e x≈1371. Como quadrática de Bézier com as pontas
   no rodapé, o ponto de controle cai em (750, 782). Núcleo #FEE7AC. */
const ARCO = 'M129 930 Q750 782 1371 930';

export function Horizonte() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 overflow-hidden" style={{ zIndex: 0 }}>
      <div
        className="absolute inset-0 animate-solis-horizon"
        style={{ willChange: 'transform, opacity' }}
      >
        <div className="cena-dark absolute inset-0">
          {/* preserveAspectRatio="none" ancora o arco no rodapé em qualquer
              tamanho de janela. Deforma a curva se a proporção mudar muito,
              mas manter a linha colada no horizonte importa mais do que
              preservar a curvatura exata — é o que a referência mostra. */}
          <svg
            className="absolute inset-0 h-full w-full"
            viewBox="0 0 1440 930"
            preserveAspectRatio="none"
            fill="none"
          >
            <path d={ARCO} stroke="rgba(240,138,36,0.20)" strokeWidth={26} strokeLinecap="round" />
            <path d={ARCO} stroke="rgba(255,183,77,0.42)" strokeWidth={10} strokeLinecap="round" />
            <path d={ARCO} stroke="#FEE7AC" strokeWidth={2.4} strokeLinecap="round" />
          </svg>
        </div>
      </div>
    </div>
  );
}
