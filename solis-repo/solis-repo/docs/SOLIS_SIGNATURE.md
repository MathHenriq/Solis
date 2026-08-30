# Solis — Assinatura Visual Oficial

Três elementos aprovados, combinados. Importante entender que são **camadas independentes**, não uma feature só — isso evita que vocês tentem controlar tudo com uma variável só amanhã e travem.

```
Camada 3: Interação    (idle / listening / thinking / responding / executing)
Camada 1: Horizonte    (foto por tema, sempre presente, em toda tela)
```

> **Atualização:** a Camada 2 (ciclo do dia) foi removida — ver a seção dela abaixo. A
> numeração das outras duas fica como está, de propósito: renumerar quebraria toda
> referência cruzada já escrita nos outros documentos.

Cada camada só sabe da que está embaixo dela. A camada de interação não precisa saber que horas são. Isso é o que evita esse sistema virar uma bola de estado só, difícil de debugar.

---

## Camada 1 — Horizonte persistente (revisado)

**Mudança de escopo confirmada:** deixou de ser uma faixa fina de 2-4px (especificação original) e virou a cena de nascer do sol em tamanho grande, ocupando a parte inferior de toda tela — validado visualmente nas telas geradas e aprovado como direção definitiva. Documentando a versão atual, não a antiga.

- Continua **renderizado uma vez no shell do app**, nunca remontado ao trocar de tela — isso não mudou, e importa ainda mais agora porque é um asset de imagem grande, não uma linha de CSS. Recarregar isso a cada navegação seria um problema de performance real.
- Fica atrás do conteúdo de cada tela (z-index abaixo), nunca compete com texto ou interação.

### Movimento obrigatório, mas quase imperceptível

Regra explícita do Matheus: "precisa ter movimento extremamente leve, mas precisa, pra não virar background estático cansativo." Isso é diferente da respiração do símbolo (Camada 2/3, ciclo de ~4,5s) — aqui o ciclo tem que ser muito mais lento, quase subliminar.

```css
/* Ciclo de 90s, variação mínima — a pessoa não deve "perceber" a animação
   conscientemente, só sentir que a tela não está morta. Só transform/opacity
   (PERFORMANCE.md): nunca filter, nunca em cima de um asset desse tamanho. */
.horizon-hero{
  animation: horizon-drift 90s ease-in-out infinite;
  will-change: transform, opacity;
}
@keyframes horizon-drift{
  0%, 100% { transform: scale(1.0); opacity: 0.94; }
  50%      { transform: scale(1.015); opacity: 1; }
}
```

**Por que 90s e não os 4,5s do símbolo:** o símbolo é um elemento pequeno que o usuário olha ativamente durante uma interação — pode respirar num ritmo perceptível sem cansar. O horizonte fica visível o tempo inteiro, em toda tela, inclusive quando a pessoa está lendo ou digitando — qualquer ciclo perceptível vira irritante rápido. A regra prática: se alguém consegue apontar exatamente quando o ciclo "bate", está rápido demais.

### Pendência técnica desta mudança

A imagem de nascer do sol é um asset pesado (raster grande, com bloom/glow de imagem gerada). Duas coisas que ainda faltam decidir com o Claude Code amanhã, não hoje:
- Formato de entrega (WebP comprimido é quase certo, pra não pesar no bundle do Tauri).
- ~~Se o ciclo do dia ainda faz sentido~~ — **resolvido**: o ciclo do dia foi removido, e a resposta acabou sendo a segunda hipótese levantada aqui (uma imagem por variação), só que a variação virou o TEMA e não a hora do dia.


## Camada 2 — Ciclo do dia — **REMOVIDA**

Esta camada não existe mais. Cada tema passou a ter uma **foto fixa própria**, e cada foto
já retrata um momento do dia (espacial = amanhecer dourado, claro = manhã pálida, dark =
noite com fresta de luz). Recalcular cor ambiente pela hora do relógio brigaria com essa
narrativa: a interface diria "é dia" com o fundo mostrando noite.

A pilha passa a ser duas camadas, não três:

```
Camada 3: Interação    (idle / listening / thinking / responding / executing)
Camada 1: Horizonte    (foto por tema, sempre presente, em toda tela)
```

Se dinamismo por hora real voltar, nasce como decisão nova, com assets que suportem a
variação — não como retrofit desta camada. O bloco `signature.dayCycle` saiu do
`solis-tokens.json` junto.

## Camada 3 — Glow reativo ao áudio (estado "escutando")

Só ativo durante `listening`. O brilho reage à amplitude real do microfone, não a um timer decorativo.

### Atualização (Fase 2): a marca voltou a ser vetor, e o glow acompanha o desenho

A nota anterior dizia que a arte era um PNG achatado e que, por isso, o glow teria de ser um `radial-gradient` atrás da imagem. **Essa premissa caiu:** a marca é vetor desde a Fase 2 (`design/solis-symbol.svg`, IoU 98,98% contra o raster aprovado).

Um `radial-gradient` só sabe iluminar um ponto, e o símbolo é um arco curvo e assimétrico — o halo saía como uma bolha atrás da arte, não como luz saindo dela. Com o vetor de volta, o glow é um **filtro SVG sobre o próprio caminho**, e o halo acompanha o traço.

**Arquitetura (`src/components/SolisEstado.tsx`):** duas camadas empilhadas.

1. `.solis-brilho` — o mesmo caminho, só desfocado. É a camada que respira.
2. `.solis-arte` — a arte nítida, estática, por cima.

O filtro é **estático**: mora no `<defs>` e nunca entra num keyframe. O que anima é `opacity` e `transform` da camada de brilho. Isso é a regra 1 do `PERFORMANCE.md`, e agora tem número: medido com os 5 estados animando ao mesmo tempo por 6s (`design/medir-custo-animacao.mjs`), a camada certa custa **4ms** de main thread com **zero** recálculos de estilo, e a versão com `filter` dentro do keyframe custa **133ms** com **360** recálculos — um por frame. 33× mais trabalho pelo mesmo efeito.

**Dois desfoques, não um.** Medido na referência `brand/states/solis-state-listening.png`, num corte perpendicular ao traço: o halo cai a 9% do pico em 6px e ainda tem 1,8% em 27px. Uma gaussiana só que fecha em 6px morre antes dos 27; a que chega aos 27 borra o traço. São duas somadas — um núcleo apertado e um rabo largo e fraco.

**O `scale` é mínimo de propósito.** Escalar a camada de brilho em 6% desloca o halo em ~11px nas pontas de um símbolo de 190px, e ele descola da arte — vira um fantasma laranja ao lado do traço. Na referência o brilho pulsa em **intensidade**, não em tamanho: quem carrega a respiração é o `opacity`.

Parâmetros e durações em `solis-tokens.json` → `states.glow` e `states.motion`. Folha de validação: `design/estados-glow.png`.

### Como pegar o áudio sem travar nada

**Importante:** não rotear isso pelo pipeline do Whisper. Whisper transcreve em batch/streaming mas tem latência própria — usar ele como fonte do glow deixaria a animação atrasada e vai contra o objetivo de fluidez.

Em vez disso, o **frontend captura o áudio duas vezes em paralelo**:
1. Uma cópia vai pro backend Python/Whisper pra transcrição (fluxo já existente).
2. Outra cópia fica só no frontend, via Web Audio API (`AnalyserNode`), calculando amplitude em tempo real — isso é local, sem round-trip de rede/processo, então não tem o delay do Whisper.

```ts
const analyser = audioContext.createAnalyser();
analyser.fftSize = 256;
const data = new Uint8Array(analyser.frequencyBinCount);

function tick() {
  analyser.getByteTimeDomainData(data);
  const rms = computeRMS(data); // 0 a 1
  const smoothed = smoothed * 0.7 + rms * 0.3; // média móvel — evita tremedeira
  updateGlow(smoothed);
  requestAnimationFrame(tick);
}
```

### Regras pra não ficar nervoso ou artificial

- **Suavizar sempre** (média móvel, ~30% peso pro valor novo). Áudio cru é ruidoso — sem suavização o glow "tremula" em vez de "respirar".
- **Piso de ruído:** amplitude abaixo de ~0,05 é tratada como silêncio (ignorar ruído ambiente de fundo).
- **Faixa de saída limitada:** mapear amplitude pra `opacity: 0.4–0.9` e `scale: 0.95–1.15`. Nunca deixar ir a 0 ou a um extremo — o Solis continua "calmo" (princípio da seção 20) mesmo reagindo.
- **Movimento reduzido:** se o usuário tiver essa opção ativada (já implementada no protótipo), o glow reativo vira um indicador estático de nível (ex: preenchimento de opacidade sem escala/animação), nunca desliga a informação, só a movimentação.

---

## Composição das camadas — exemplo

Um usuário fala com o Solis:
- Camada 1: horizonte visível em todas as telas, sempre.
- Camada 3: enquanto ele fala, o glow do símbolo pulsa com a voz dele, sobre a paleta noturna da camada 2.

Nenhuma camada foi "desligada" pra outra funcionar — elas somam.
