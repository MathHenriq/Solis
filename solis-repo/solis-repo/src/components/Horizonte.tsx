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
            {/* A luz não é uniforme ao longo do arco. Medindo a faixa acima de 50% de
                brilho na referência, coluna a coluna, ela vai de 44px no vértice a 25px
                150px dali, 16px a 200, 7px a 300 e some antes das bordas. Isso é um bloom
                de sol centrado no vértice, não uma faixa de espessura constante.

                Reproduzir isso com um traço só é impossível: opacidade é degrau, então
                um traço largo ou está inteiro acima de 50% ou some. Daí as camadas
                empilhadas — cada uma mais estreita e apagando mais longe, de modo que o
                que sobra acima do limiar vai afinando com a distância. As janelas de cada
                gradiente foram calculadas a partir das larguras medidas. */}
            <defs>
              {[
                { id: 'a1', larg: 44, meia: 110, cor: '#FFD489', pico: 0.5 },
                { id: 'a2', larg: 26, meia: 175, cor: '#FFCB72', pico: 0.5 },
                { id: 'a3', larg: 16, meia: 230, cor: '#FFC260', pico: 0.5 },
                { id: 'a4', larg: 7, meia: 320, cor: '#FFBB52', pico: 0.5 },
              ].map((c) => (
                <linearGradient key={c.id} id={`solis-${c.id}`} gradientUnits="userSpaceOnUse" x1="0" x2="1440">
                  <stop offset={(750 - c.meia - 120) / 1440} stopColor={c.cor} stopOpacity="0" />
                  <stop offset={(750 - c.meia) / 1440} stopColor={c.cor} stopOpacity={c.pico * 0.62} />
                  <stop offset="0.521" stopColor={c.cor} stopOpacity={c.pico} />
                  <stop offset={(750 + c.meia) / 1440} stopColor={c.cor} stopOpacity={c.pico * 0.62} />
                  <stop offset={(750 + c.meia + 120) / 1440} stopColor={c.cor} stopOpacity="0" />
                </linearGradient>
              ))}
              <linearGradient id="solis-halo" gradientUnits="userSpaceOnUse" x1="0" x2="1440">
                <stop offset="0.05" stopColor="#F08A24" stopOpacity="0" />
                <stop offset="0.521" stopColor="#F08A24" stopOpacity="0.20" />
                <stop offset="0.95" stopColor="#F08A24" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="solis-nucleo" gradientUnits="userSpaceOnUse" x1="0" x2="1440">
                <stop offset="0.174" stopColor="#FEE7AC" stopOpacity="0" />
                <stop offset="0.257" stopColor="#FEE7AC" stopOpacity="0.6" />
                <stop offset="0.521" stopColor="#FFF6DC" stopOpacity="1" />
                <stop offset="0.785" stopColor="#FEE7AC" stopOpacity="0.6" />
                <stop offset="0.868" stopColor="#FEE7AC" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={ARCO} stroke="url(#solis-halo)" strokeWidth={78} strokeLinecap="round" />
            <path d={ARCO} stroke="url(#solis-a1)" strokeWidth={44} strokeLinecap="round" />
            <path d={ARCO} stroke="url(#solis-a2)" strokeWidth={26} strokeLinecap="round" />
            <path d={ARCO} stroke="url(#solis-a3)" strokeWidth={16} strokeLinecap="round" />
            <path d={ARCO} stroke="url(#solis-a4)" strokeWidth={7} strokeLinecap="round" />
            <path d={ARCO} stroke="url(#solis-nucleo)" strokeWidth={2.6} strokeLinecap="round" />
          </svg>
        </div>
      </div>
    </div>
  );
}
