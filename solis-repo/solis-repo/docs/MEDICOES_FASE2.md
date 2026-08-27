# Medições da Fase 2 — 4 temas, sidebar compacta, símbolo refinado

Registro das medições feitas nas referências da Fase 2. Existe porque a Regra 2 do
`CLAUDE.md` exige cor por amostra de pixel e espaçamento medido em px — este arquivo é
onde esses números ficam, pra não serem re-estimados no olho a cada tela.

**Referências medidas** (em `referencias/`):
`telas/tema-espacial-vinho.png`, `telas/tema-claro-padrao.png`, `telas/tema-dark.png`,
`brand/symbol-refinado/*`.

## Método

- Cor: erosão 5×5 sobre a máscara de tinta e média do **interior do traço** — não é média
  do bounding box, que puxaria a cor pro antialiasing e clarearia o resultado. Para texto
  pequeno (onde não sobra interior), média dos 6% de pixels mais escuros/claros.
- Geometria: detecção de borda por gradiente de linha/coluna, não leitura visual.
- **Normalização:** as 3 imagens têm 1536×1024, mas a janela do app dentro delas não é
  igual (espacial/claro ocupam a imagem inteira; dark tem a janela em 1524px). Todos os
  valores "@1440" abaixo já estão normalizados pra uma janela de 1440px de largura, que é
  a unidade em que o CSS vai ser escrito. Sem isso os três temas dariam números diferentes
  pra mesma coisa.

## Cores por tema

| Papel | espacial | claro | dark |
|---|---|---|---|
| Canvas | `#FAE7D0` | `#FCF7F2` | `#07080D` |
| Divisória | `#DAC1A8` | `#E5DDD5` | `#181A1C` |
| Texto primário | `#4A0A09` | `#27231C` | `#F1E4D4` |
| Texto secundário | `#894D43` | `#888480` | `#746A5F` |
| Placeholder | `#90554B` | `#64615E` | `#8F8172` |
| Acento (item ativo) | `#DA7B22` | `#E18A21` | `#F0BA46` |

Três coisas que caem daqui:

1. **O acento varia por tema.** Não existe um `solar` único servindo os três. Isso
   colide com o controle "Cor de destaque" que aparece em `telas/06-configuracoes.png`
   como se fosse independente do tema — pendência de produto, não de código.
2. **A sidebar não é uma superfície separada.** O fundo dela é o mesmo do canvas nos três
   temas (diferença de 1–3 pontos em cada canal, dentro do ruído do render). O que a
   separa é só a divisória de 1px. Não criar `bg.surface` pra ela.
3. **O vinho medido é `#4A0A09`**, não o `#6B1420` que estava no pedido — este último
   corresponde à borda antialiasada do glifo, não ao traço. Decisão do Matheus: vale o
   medido.

### Contraste — PROVISÓRIO

> **Medido no screenshot de 1536×1024, não na imagem-fonte.** A foto em resolução real
> (pendência 0a) pode ter faixa dinâmica maior nas altas luzes, o que só pioraria os
> números do fundo claro. **Reconferir quando a imagem chegar.**

Método: WCAG 2.x, amostrando só a margem direita de cada tela (220 mil px de fundo puro,
sem UI por cima), com a razão calculada pixel a pixel contra a cor do token.

| | primário | secundário | secundário: % do fundo abaixo de 4,5:1 |
|---|---|---|---|
| espacial | 12,78:1 | **5,34:1** (mediana) | 27,6% |
| claro | 14,56:1 | **3,46:1** | 100% |
| dark | 15,93:1 | **3,77:1** | 100% |

O resultado inverteu a expectativa. A foto **não** é o problema principal:

1. **`espacial` passa** onde o texto realmente cai. O secundário sustenta 5,4:1 até ~72%
   da altura da janela e só então despenca (4,25:1 em 74%, 3,07:1 em 86%, 1,30:1 no
   rodapé, onde o clarão do sol cruza a luminância do texto). Regra prática que sai daí:
   **texto secundário não pode ir abaixo de ~70% da altura nos temas com foto** — o que a
   referência já respeita, porque ali embaixo só existem o composer e os chips.
2. **`claro` e `dark` reprovam em AA para texto normal (4,5:1) no canvas chapado**, antes
   de qualquer foto: 3,46:1 e 3,77:1 em toda a área. Os 3:1 que eles superam são o limiar
   de **texto grande** (≥24px normal ou ≥18,66px negrito), e o subtítulo medido tem ~20px
   normal — não se qualifica.

### Derivação das cores secundárias

Decisão do Matheus: **não aceitar "AA só para texto grande"** — isso baixaria um padrão
que todos os outros tokens de texto do sistema já cumprem. As duas cores que reprovavam
foram ajustadas até 4,5:1.

**Método — derivar do medido, não substituir.** Cada cor é convertida para OKLCh e só o
**L** (claridade perceptual) se move; croma e matiz ficam travados. É isso que separa
"derivar" de "trocar por outra cor": o tom e a saturação perceptual continuam sendo os
amostrados na referência. Implementado em `design/derivar-cor.py`.

O alvo não é o canvas chapado, é o **pior pixel de fundo dos 70% superiores da janela** —
a faixa onde texto secundário efetivamente cai. Mirar só no canvas deixaria margem zero
sobre a foto e a cor oscilaria em torno de 4,5 conforme o gradiente.

| tema | medido | final | contraste antes | contraste depois | ΔEOK | matiz |
|---|---|---|---|---|---|---|
| espacial | `#894D43` | *(mantido)* | 4,59:1 | 4,59:1 | — | — |
| claro | `#888480` | **`#726E6A`** | 3,32:1 | **4,52:1** | 0,0750 | 67,7° → 67,7° |
| dark | `#746A5F` | **`#82786D`** | 3,72:1 | **4,55:1** | 0,0482 | 70,0° → 70,1° |

Contraste é o do **pior pixel de fundo**, não a mediana — as medianas ficam em 5,38:1,
4,72:1 e 4,63:1. O matiz sobrevive intacto nos dois casos; o croma varia na terceira casa,
que é só o arredondamento para hex de 8 bits.

ΔEOK é a distância perceptual em OKLab. O limiar em que a maioria das pessoas percebe
diferença lado a lado fica em torno de 0,02, então **os dois ajustes são perceptíveis** se
você comparar as duas versões coladas uma na outra — não dava para chegar a 4,5:1 com um
passo imperceptível partindo de 3,3:1. Isoladamente, cada cor lê como o mesmo tom.

Duas notas de método:

- A amostragem exclui os 80px do topo. A faixa que eu usava pegava os botões de janela no
  canto superior direito, e aqueles pixels claros apareciam como "pior fundo" — davam
  1,00:1 falso em todos os três temas.
- `espacial` não mudou: os 5,34:1 de mediana que ele já tinha se sustentam em 4,59:1 mesmo
  no pior pixel dos 70% superiores.

## Sidebar

| | @1536 | **@1440** | pedido |
|---|---|---|---|
| Largura | 214px (13,93%) | **200px** | ~200px / 14% ✅ |
| Ícone | 18–19px | **18px** | 16–18px ✅ |
| Passo entre itens | 59px | **55px** | "generoso" ✅ |
| Rótulo (cap-height 11px) | ~15px | **~14px** | 13px — 1px acima |
| Barra do item ativo | 3px, a 13px da borda | **3px, a 12px** | — |
| Recuo esquerdo do ícone | 31px | **29px** | — |
| Recuo esquerdo do rótulo | 73px | **69px** | — |
| Símbolo + wordmark (topo) | 75px de largura | **70px** | — |

Referência anterior (`telas/06-configuracoes.png`), pra dimensionar a mudança: sidebar de
250px @1440, ícones de 21px, passo de 62px, rótulo de ~16px. A nova é 20% mais estreita
com ícone e texto menores, mas o passo caiu só 11% — é isso que faz o conjunto ficar
enxuto sem ficar apertado.

## Composer ("Fale com o Solis…")

| | @1536 | **@1440** |
|---|---|---|
| Altura (espacial/claro) | 84px | **79px** |
| Altura (dark) | 77px | 73px |
| Largura | 849–867px | **~805px** |
| Raio do canto | ~14px | **~13px** (≈ `radius.md`) |
| Chips de ação (altura) | 59px | **58px** |

**Nota importante:** a referência anterior tinha 81px @1440. O campo novo **não ficou
mais baixo** — ficou 2px menor no mesmo enquadramento. O que mudou foi o peso: borda
âmbar → borda neutra sutil, botão circular âmbar de 48px → seta fina, e a largura cresceu
de 773 para ~805px. Decisão do Matheus: implementa os 79px da referência, a descrição
verbal de "mais fino" se referia ao peso visual.

### Horizonte do tema dark

A linha de luz não é um borrão radial — é uma **curva nítida** com halo em volta.
Amostrando o pico de brilho por coluna, ela é uma parábola de vértice **(750, 856)** que
sai pelo rodapé em x≈129 e x≈1371, com núcleo `#FEE7AC`. Como quadrática de Bézier com as
pontas no rodapé, o ponto de controle cai em (750, 782) — que é exatamente o path usado em
`src/components/Horizonte.tsx`. Implementado assim, o arco bate com a referência dentro de
1px em todas as colunas amostradas.

A primeira tentativa foi uma elipse em CSS (`border-radius: 50%` + `border-top`), e ela
saiu 230px alta demais: acertar apex e curvatura de uma elipse por porcentagem de caixa é
chute. Medir a curva e escrever o path resolve de primeira.

**A luz não é uniforme ao longo do arco.** Medindo a faixa acima de 50% de brilho coluna a
coluna, a referência vai de 44px no vértice a 25px 150px dali, 16px a 200, 7px a 300, e
some antes das bordas. É um bloom de sol centrado no vértice, não uma faixa de espessura
constante — e um traço único não reproduz isso, porque opacidade é degrau: ou a faixa
inteira passa de 50% ou some. A solução são camadas empilhadas de larguras decrescentes
(44/26/16/7px), cada uma com um gradiente longitudinal que apaga a uma distância própria,
de modo que o que sobra acima do limiar afina com a distância. Erro absoluto somado nas 11
colunas amostradas: **51px → 18px**, com casamento exato em x = 400, 550, 600, 750, 900 e
1200.

## Tipografia

| | @1536 | **@1440** | família |
|---|---|---|---|
| Saudação "Olá, Matheus." | bbox 54–56px | **~52px** | **serifada** |
| Subtítulo | bbox 21–23px | **~20px** | sans |
| Rótulo da nav | cap 11px | **~14px** | sans |

O contraste serifada/sans está confirmado como intencional e **restrito à saudação**:
subtítulo, rótulos da nav, placeholder, chips de ação e o wordmark SOLIS são todos sans
nas três telas. A serifada entra como um token só (`fontFamilyDisplay`) usado num lugar
só. Qual serifada ainda não foi escolhida — e vai exigir self-host no bundle do Tauri,
porque o `HANDOFF.md` trava "sem dependência de rede".

## Fundos

Correlação da faixa do horizonte entre as três telas (luminância normalizada):

| par | correlação | leitura |
|---|---|---|
| espacial × claro | **0,98** | mesma foto, só re-gradeada |
| espacial × dark | 0,55 | cenas diferentes |
| claro × dark | 0,47 | cenas diferentes |
| espacial × `telas/07 - Background.png` | 0,49 | **não é este arquivo** |
| espacial × `telas/08-Background Novo.png` | 0,32 | **não é este arquivo** |

Ou seja: a convergência espacial/claro se confirma numericamente — **um asset, duas
tintas**. E a foto usada nas telas da Fase 2 **não está no repositório** como arquivo
próprio; os dois backgrounds que existem são outra imagem. Pendência 0a: subir a cena
em resolução real (≥2560px de largura), preferencialmente já em WebP.

O tema `dark` não usa foto — o horizonte dele é um arco de glow sintético, o que é bom
pro bundle e coerente com a Camada 1 do `SOLIS_SIGNATURE.md`.

## Símbolo refinado

Os 6 arquivos entregues são **RGB sem canal alpha**, todos sobre branco `#FEFEFE`. A
maior renderização da marca sozinha tem **387×221px de tinta** (em `mono-wordmark.png`).
Isso não sustenta um ícone de app de 1024×1024 sem ampliar 2,6× um desenho de traço fino
— por isso a vetorização (pendência 0b), e não um recorte com alpha.

**Vetor gerado:** `design/solis-symbol.svg` — 48 segmentos, 2,1 KB, viewBox
384.91 × 220.83. Traço direto do raster, **sem ajuste manual em nenhum ponto de
controle**, reproduzível por `design/vetorizar-simbolo.py`.

| métrica | valor |
|---|---|
| IoU contra o original | **98,98%** |
| Pixels que o vetor perdeu | 45 de 15.152 (0,30%) |
| Pixels que o vetor engordou | 111 de 15.152 (0,73%) |

Validação visual em `design/solis-symbol-validacao.png` (sobreposição + zoom nas duas
pontas finas do arco e no ponto onde o sol emerge da base + renderização em 16/18/24/32/
48/64px). **Status: aguardando aprovação visual do Matheus** — a condição dele foi não
considerar pronto sem a comparação lado a lado.

Hexes declarados na folha do símbolo, conferidos contra os tokens:

| folha | token existente | bate? |
|---|---|---|
| `#FFB74D` âmbar | `color.solar` | ✅ |
| `#F5F0E7` creme | `color.warmWhite` | ✅ |
| `#FFFFFF` claro | `colorLight.paper` | ✅ |
| `#0A0F14` escuro | `color.night` = `#071019` | ❌ e o canvas medido na tela dark é `#07080D` — três valores pra mesma coisa |

## Divergências resolvidas com o Matheus

| # | Divergência | Decisão |
|---|---|---|
| 1 | Composer não ficou mais baixo que a referência antiga | Implementa os 79px medidos |
| 2 | Microfone sumiu do composer nas 3 telas | Omissão do gerador — **reintroduzir** (Whisper e a Camada 3 do SIGNATURE dependem dele) |
| 3 | Nav com 7 itens, sem "Modelos locais" | Omissão do gerador — **mantém os 8 itens**. As telas da Fase 2 valem pro estilo da nav, não pra lista |
| 4 | Vinho `#6B1420` (pedido) vs `#4A0A09` (medido) | Vale o medido |
| 5 | Assets do símbolo sem alpha e em baixa resolução | Vetorizar, com validação visual obrigatória |
| 6 | Hexes novos conflitando com `solis-tokens.json` | Reescrever os tokens pelos valores medidos |
| — | Controles de janela macOS → Windows | Plataforma alvo é **Windows** |

## Decisões de produto (fechadas)

| Questão | Decisão |
|---|---|
| Tema padrão na primeira instalação | `dark` |
| Quantos temas | **3** — `espacial`, `claro`, `dark`. O quarto do pedido original era o "bege+vinho", que convergiu com o `espacial` |
| "Cor de destaque" em Configurações | **Sai.** O acento é por tema; escolher o tema já escolhe o acento |
| "Exibir imagem de fundo" desligado | Versão sólida da paleta do mesmo tema, sem a foto — mesma lógica que o `dark` já usa. A cena é uma camada sobre `--canvas`, então basta remover a camada; nenhuma cor nova precisa existir |
| Ciclo do dia (Camada 2) | Roda **só no tema `dark`**, o único sem imagem fixa. Nos temas fotográficos a imagem já retrata um momento específico do dia |
| Rótulo da nav | 14px (o medido), não 13px |

## Ainda em aberto

1. **Reconferir o contraste com a foto-fonte** (pendência 0a). As duas secundárias já
   foram derivadas até 4,5:1 no pior pixel, mas a medição saiu do screenshot; a imagem em
   resolução real pode ter faixa dinâmica maior nas altas luzes e exigir mais um passo de
   L no tema `claro`.
2. **A fonte serifada da saudação** — nenhuma foi escolhida, e a escolha exige self-host
   no bundle do Tauri (o `HANDOFF.md` trava "sem dependência de rede").
3. **Os lockups de `brand/logo/`** — continuam com o símbolo antigo. Regerar depende da
   decisão de fonte acima: o wordmark tem 40px de altura de tinta na folha do símbolo
   refinado e 100px no lockup antigo, e traçar letra nessa resolução entrega tipografia
   pior que a original. O caminho certo é compor o wordmark como texto quando a fonte
   estiver fechada.
4. **`brand/states/`** — os 3 renders com glow são do símbolo antigo e não derivam do
   vetor. Se a arquitetura do `SOLIS_SIGNATURE.md` for mantida (glow como camada CSS
   atrás da arte), eles deixam de ser necessários em vez de precisarem ser regerados.
5. **Referência visual do card Aparência** — ele vai ganhar o seletor de tema e o seletor
   Sidebar/Ícones, e perder "Cor de destaque". A referência atual
   (`telas/06-configuracoes.png`) é anterior a tudo isso.
