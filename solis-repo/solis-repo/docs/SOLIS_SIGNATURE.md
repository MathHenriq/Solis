# Solis — Assinatura Visual Oficial

Três elementos aprovados, combinados. Importante entender que são **camadas independentes**, não uma feature só — isso evita que vocês tentem controlar tudo com uma variável só amanhã e travem.

```
Camada 3: Interação    (idle / listening / thinking / responding / executing)
Camada 2: Ciclo do dia (paleta muda com a hora real)
Camada 1: Horizonte    (sempre presente, em toda tela)
```

Cada camada só sabe da que está embaixo dela. A camada de interação não precisa saber que horas são; a camada de ciclo do dia não sabe se o usuário está falando. Isso é o que evita esse sistema virar uma bola de estado só, difícil de debugar.

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
- Se o ciclo do dia (antiga Camada 2, `signature.dayCycle` no `solis-tokens.json`) ainda faz sentido como troca de cor de um vetor, ou se agora precisa de **múltiplas versões da imagem** (uma por fase do dia) — isso muda o custo de manter de "editar um token" para "gerar 5 imagens e trocar entre elas", parecido com o que já vivemos com os estados do símbolo.


## Camada 2 — Ciclo do dia

A cor do horizonte e a posição do sol no arco mudam com a hora real do dispositivo. Não é decoração — é o "nascer do sol" do conceito de marca (seção 2 do DS) sendo levado a sério.

| Fase | Horário | Paleta | Posição do sol no arco |
|---|---|---|---|
| Madrugada | 00h–05h | `night` + `deep`, glow quase nulo | Base do arco (quase invisível) |
| Amanhecer | 05h–08h | `amber` entrando, ainda escuro atrás | Subindo |
| Dia | 08h–17h | `solar` + `light`, brilho máximo | Topo do arco |
| Entardecer | 17h–20h | `amber` dominante, tom mais quente | Descendo |
| Noite | 20h–00h | `muted` + `deep`, glow mínimo | Base do arco |

**Regra de token:** não criar hex novo pra isso. Cada fase é uma composição de opacidade/mistura dos tokens que já existem (`color.night`, `color.deep`, `color.amber`, `color.solar`, `color.light`, `color.muted`). Se alguma fase parecer "sem graça" com os tokens atuais, o problema é ajustar a opacidade, não inventar cor nova — isso já é regra herdada da seção 21 do DS ("nada existe apenas porque pode existir").

**Efeito colateral bom:** a fase "madrugada/noite" naturalmente parece com o estado `idle`/repouso — reforça a metáfora em vez de competir com ela.

## Camada 3 — Glow reativo ao áudio (estado "escutando")

Só ativo durante `listening`. O brilho reage à amplitude real do microfone, não a um timer decorativo.

### Atualização: a arte final é raster, não vetor em camadas

O plano original desta seção presumia um SVG com `horizon`/`sun`/`glow` como elementos separados e animáveis. A marca aprovada (ver `HANDOFF.md` → "Símbolo oficial") é uma imagem PNG achatada, gerada e aprovada visualmente pelo Matheus — não dá mais pra recortar o glow de dentro dela.

**Ajuste de arquitetura:** o glow reativo passa a ser uma camada CSS **independente**, posicionada atrás da imagem (`radial-gradient` com blur, opacity/scale controlados por `--audio-level`). A arte da marca nunca é modificada — só uma camada extra por trás dela pulsa. Implementação de referência em `solis-prototype.html` (classe `.symbol-glow`).

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

Um usuário fala com o Solis às 21h:
- Camada 1: horizonte visível em todas as telas, sempre.
- Camada 2: paleta em modo "noite" (tons `muted`/`deep`, sol baixo no arco).
- Camada 3: enquanto ele fala, o glow do símbolo pulsa com a voz dele, sobre a paleta noturna da camada 2.

Nenhuma camada foi "desligada" pra outra funcionar — elas somam.
