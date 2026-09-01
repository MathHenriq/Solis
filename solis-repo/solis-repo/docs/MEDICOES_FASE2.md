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

### Horizonte do tema dark — **SUPERADO**

O `dark` usava um arco de luz sintético em CSS/SVG, medido coluna a coluna contra a
referência: parábola de vértice (750, 856), faixa acima de 50% de brilho indo de 44px no
centro a 25px 150px dali, erro somado de 18px em 11 colunas. **Isso saiu** — o tema passou
a usar `bg-dark.webp`, uma foto como os outros dois.

Fica registrado porque a medição continua descrevendo fielmente o que a referência mostrava,
e porque, se o arco sintético voltar algum dia como fallback para quando a foto não carrega,
os números já estão levantados.

## Tipografia

| | @1536 | **@1440** | família |
|---|---|---|---|
| Saudação "Olá, Matheus." | bbox 54–56px | **~52px** | **serifada** |
| Subtítulo | bbox 21–23px | **~20px** | sans |
| Rótulo da nav | cap 11px | **~14px** | sans |

**A serifada é Playfair Display**, self-hosted em `public/fontes/` (peso 400, subsets
`latin` e `latin-ext` — o português cabe inteiro neles). Não entra por `<link>` pro Google:
o `HANDOFF.md` trava "sem dependência de rede", e o Solis é local-first. **Confirmada pelo
Matheus — fechada.**

Trocar a genérica pela Playfair moveu o ritmo vertical: a métrica dela põe a tinta 3px mais
alto na mesma caixa, e a caixa maior empurrou composer e chips. Compensado — todos os
elementos voltaram a ±1px do medido.

O contraste serifada/sans está confirmado como intencional e **restrito à saudação**:
subtítulo, rótulos da nav, placeholder, chips de ação e o wordmark SOLIS são todos sans
nas três telas. A serifada entra como um token só (`fontFamilyDisplay`) usado num lugar
só. O wordmark SOLIS **não** é Playfair: é **DM Sans 500**, escolhida na folha de
candidatas (`design/comparar-wordmark.py`), também self-hosted e também num token só
(`fontFamilyWordmark`), usado num lugar só.

## Fundos

> **REVERTIDO.** Esta seção media a arquitetura anterior — uma foto compartilhada entre
> `espacial` e `claro`, e o `dark` sem foto. A decisão atual é **uma foto por tema**:
> `bg-espacial.webp`, `bg-claro.webp`, `bg-dark.webp`. A medição fica como registro, porque
> foi ela que sustentou a decisão anterior.

Correlação da faixa do horizonte entre as três telas de referência da Fase 2:

| par | correlação | leitura na época |
|---|---|---|
| espacial × claro | **0,98** | mesma foto, só re-gradeada |
| espacial × dark | 0,55 | cenas diferentes |
| espacial × `telas/07 - Background.png` | 0,49 | não era aquele arquivo |

O 0,98 continua sendo um fato sobre **aquelas telas**. O que mudou foi a decisão de produto,
que agora pede fotos distintas — as telas antigas não descrevem mais o alvo de fundo.

### Alinhamento do horizonte entre as fotos

Medido por detecção de crista (brilho de cada linha contra a tendência local, nas colunas
centrais) e conferido visualmente nas três:

| tema | horizonte na fonte | no arquivo final |
|---|---|---|
| Espacial | 74,2% | **74,0%** |
| Claro | 73,2% | **74,0%** |
| Dark | 71,9% | **74,0%** |

### Calibração do alinhamento

Medido no render (1440×930, animação de 90s congelada) pela linha mais brilhante por coluna
na faixa **x 1210–1420** — a única larga o bastante e livre de composer e chips. O desvio se
mantém estável entre colunas, o que confirma offset real e não ruído de detecção.

Protocolo final: pico de brilho por coluna em **x 1210–1380**, de 5 em 5px, mediana. A faixa
exclui x≥1381 porque ali entram os ícones de janela (minimizar/maximizar/fechar), que
contaminam a leitura.

| tema | `HORIZONTE` | mediana | min–max | vs espacial |
|---|---|---|---|---|
| espacial | 0,742 | **709,0** | 693–726 | baseline |
| claro | 0,732 → **0,752** | **709,0** | 694–727 | **0,0px** |
| dark | 0,719 → **0,752** | **709,0** | 694–726 | **0,0px** |

Os três convergiram para a mesma mediana, e as faixas min–max quase coincidem — o que mostra
que não é só o ponto medido que bateu, é a curva inteira do arco.

Antes dos ajustes: claro +19,5px e dark +32,0px em relação ao espacial.

Protocolos que **não** funcionam nestas imagens, todos testados: pico de brilho na coluna
central x=720 (no espacial acha o clarão do céu, não o horizonte, e a coluna atravessa o
composer e os chips), detecção de crista, de gradiente, de textura, e correlação cruzada
vertical. Cada um trava num traço físico diferente porque espacial e dark têm arco fino e
nítido enquanto o claro tem transição difusa. Só a faixa livre de UI, com a linha mais
brilhante por coluna, dá leitura estável nos três.

**A compensação por CSS não era possível.** A ideia era um `background-position-y` por
tema, mas com `background-size: cover` e imagem de aspecto 1,60 numa janela de 1,55 o
`cover` escala pela altura: a imagem cobre os 930px exatos e a folga sobra só na
horizontal. Sem folga vertical, `position-y` não tem efeito, e os três horizontes ficariam
em 690, 681 e 669px — 21px de diferença, travados.

A saída foi **reenquadrar os três assets** para um horizonte comum de 74,0%, que é
exatamente o que a nota da decisão apontava como correção certa caso o desalinhamento
aparecesse fora de 1440px. Ele aparece *em* 1440px. Cada foto perdeu 4% da altura e 4% da
largura, com o deslocamento calculado a partir da medição; nada foi redesenhado nem
esticado. Resultado: **um `positionY` só**, e a exceção ao princípio de fonte única deixa
de existir.

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
| Ciclo do dia (Camada 2) | ~~Roda só no tema dark~~ → **REMOVIDO**. Cada tema passou a ter foto própria, e cada foto já retrata um momento do dia; recalcular cor por hora do relógio brigaria com essa narrativa |
| Fundos | ~~Uma foto compartilhada entre espacial e claro, dark sem foto~~ → **uma foto por tema** |
| Rótulo da nav | 14px (o medido), não 13px |

## Contraste sobre as fotos — reprovava, e por quê

Medido com a UI escondida (só a camada da cena), nas regiões onde texto efetivamente cai.
Com a foto esticada atrás da tela inteira:

| tema | secundário | pior caso | veredito |
|---|---|---|---|
| espacial | `#894D43` | **1,89:1** | reprova |
| claro | `#726E6A` | **1,00:1** | reprova |
| dark | `#82786D` | **1,28:1** | reprova |

O primário sobrevivia quase todo (hero entre 9,1:1 e 15,2:1), com uma exceção: os rótulos da
nav no `espacial` caíam a 3,14:1.

**A causa não era a cor do texto.** A faixa de luminância do fundo dentro de um mesmo tema é
de 13× a 21× (espacial 0,014–0,981; claro 0,028–1,000; dark 0,000–1,000). Nenhuma cor
chapada sustenta 4,5:1 contra essa variação — uma cor que passa no claro reprova no escuro
e vice-versa. Véu de tela cheia também não resolvia: a opacidade mínima que devolveria
4,5:1 era de 82% no espacial, 95% no claro e 99% no dark — apagaria a foto.

**A causa era a geometria.** As secundárias tinham sido derivadas contra as telas de
referência, cujo fundo é chapado na área de texto. Nas referências a cena ocupa só a parte de
baixo — é o que o `SOLIS_SIGNATURE.md` sempre disse na Camada 1 ("ocupando a parte inferior de
toda tela"). Esticar a foto atrás da tela inteira foi um desvio meu da referência, não uma
decisão de produto.

## Cena ancorada na parte de baixo — correção

`.cena-camada` deixou de ser uma camada de tela cheia e virou uma banda:

| parâmetro | valor | de onde veio |
|---|---|---|
| `left` | `var(--sidebar-width)` | nas 3 referências a coluna da sidebar fica em canvas chapado até a base |
| `height` | `55vh` | escolhida junto com o `positionY` para pôr o ápice do horizonte em ~85% |
| `background-size` | `cover` | a banda é bem mais larga que 1,6:1, então o cover escala pela **largura** e sobra folga vertical — é isso que faz o `position-y` voltar a ter efeito |
| `background-position-y` | `66%` | resolve o ápice em 85% da altura da janela |
| máscara | alpha 0 → 1 entre **68% e 83%** da altura da janela, em smoothstep de 9 paradas | 68% é o piso do texto mais baixo da Conversa (os chips terminam a 607px de 930 = 65,3%) com folga; smoothstep em vez de rampa linear porque o gradiente ocupa 15% da tela e rampa crua deixa banding de Mach nas duas pontas |

Tudo isso vive em `solis-tokens.json → scenes` e é gerado pra `tokens.css`.

### Contraste depois — passa

Medido com `design/medir-caixas.mjs` + `design/medir-contraste.py`, janela 1440×930, animação
congelada no frame 0%. Em **todos** os 19 alvos das 3 telas o pior pixel e o melhor pixel dão
o mesmo número — ou seja, o fundo debaixo de todo texto é chapado, a cena não encosta em
nenhum.

| tema | pior texto | valor |
|---|---|---|
| espacial | placeholder `#90554B` | 4,85:1 |
| claro | subtítulo / chips `#726E6A` | 4,75:1 |
| dark | subtítulo / chips `#82786D` | 4,63:1 |

### Altura do horizonte — bate com a referência

`design/medir-horizonte.py`, mesma faixa medida no app e na referência:

| tema | ápice (app) | ápice (ref) | borda do planeta x1210–1380 (app) | borda (ref) |
|---|---|---|---|---|
| espacial | 85,7% | 85,0% | 90,1% | 90,3% |
| claro | 84,7% | 85,0% | 95,4% | 96,4% |
| dark | 85,2% | 84,5% | 90,0% | 89,9% |

Espalhamento entre os 3 temas: **9px** no ápice e **50px** na borda — menor que o
espalhamento da própria referência (66px na borda). O recorte dos assets feito antes
continua sendo o que sustenta isso.

Estável fora de 1440×930 (ápice, os 3 temas):

| janela | aspecto | espacial | claro | dark |
|---|---|---|---|---|
| 1440×1200 | 1,20 | 84,6% | 83,8% | 84,2% |
| 1280×800 | 1,60 | 85,6% | 84,6% | 85,1% |
| 1366×768 | 1,78 | 86,2% | 85,2% | 85,7% |
| 1600×900 | 1,78 | 86,2% | 85,1% | 85,7% |
| 1920×1080 | 1,78 | 86,2% | 85,1% | 85,8% |

Comparação visual antes/depois/referência: `design/fundo-ancorado.png`.

### Cor de destaque — derivada até 4,5:1

Não tinha relação com o fundo: é o par `--accent` × `--canvas`, chapado contra chapado, e já
era assim antes da mudança de fundo. O accent não pinta só ícone — ele pinta o rótulo da nav
ativa, que é texto de 14px. Por isso o critério é 4,5:1 e não os 3:1 de componente gráfico.

| tema | medido na referência | derivado | antes | depois | ΔEOK |
|---|---|---|---|---|---|
| espacial | `#DA7B22` | **`#A25500`** | 2,55:1 | 4,54:1 | 0,1450 |
| claro | `#E18A21` | **`#A56100`** | 2,51:1 | 4,58:1 | 0,1545 |
| dark | `#F0BA46` | (mantido) | 11,26:1 | — | — |

ΔEOK de ~0,15 é grande — o limiar de percepção lado a lado fica em torno de 0,02. O laranja
da marca escurece visivelmente nos dois temas claros. Aprovado pelo Matheus.

**Uma correção no método.** A primeira derivação saiu com o matiz torto: 57,4° → 51,1° no
espacial. Causa: nesse L o laranja original não cabe no gamut sRGB, o canal azul ia pra
negativo e o `clamp` em 0 torcia o matiz — exatamente o que "derivar do medido, não trocar
por outra cor" não aceita. `design/derivar-cor.py` ganhou `croma_no_gamut()`: quando o par
(L, croma) sai do gamut, o **croma** cede até caber e o matiz fica travado. Resultado:

| tema | matiz | croma |
|---|---|---|
| espacial | 57,4° → 57,1° | 0,1506 → 0,1285 |
| claro | 64,1° → 64,5° | 0,1507 → 0,1255 |

As secundárias de texto não mudaram: elas já estavam dentro do gamut, então o clamp nunca
tinha entrado nelas.

## Wordmark SOLIS — DM Sans 500

Fechada. O wordmark da folha do símbolo refinado tem só 40px de altura de tinta: traçar
letra nessa resolução entrega tipografia pior que a original, então ele é composto como
**texto**, e por isso escala e continua editável. `design/comparar-wordmark.py` mede a
referência e compara candidatas de licença aberta — a única coisa que o `HANDOFF.md`
permite, porque a fonte é servida do próprio bundle.

Em frações da altura de caixa alta:

| | O (larg/alt) | S | L | haste |
|---|---|---|---|---|
| referência | 0,940 | 0,730 | 0,635 | 0,135 |
| **DM Sans 500** | 0,940 | 0,685 | 0,580 | 0,135 |

O `O` e a haste batem exatamente; o `S` e o `L` saem ~6% mais estreitos. A Lexend 400
ganhava no erro numérico e perdia no olho — o `I` dela tem terminais alargados e o da
referência é haste reta.

**Não é a fonte original.** É a mais próxima em licença aberta. Se a original aparecer, o
troco custa um token.

**Dois trackings, de propósito.** A marca e a interface espaçam diferente:

| | largura/cap | tracking na DM Sans 500 |
|---|---|---|
| lockup (folha da marca) | 7,250 | 0,652em |
| sidebar (as 3 telas) | 6,545 | 0,524em |

**Correção de tamanho junto.** O `system-ui` que estava na sidebar era substituto e saía
pequeno: cap de 8px contra os 10,3px medidos na referência, e 30% mais estreito. O tamanho
agora sai da proporção com o símbolo (cap = 14,5% da largura do símbolo, folga = 14,5%),
que é a razão medida na referência — assim o bloco continua coerente com o símbolo em
qualquer tamanho que ele venha a ter.

### Lockups regerados

`design/gerar-lockups.py` monta os dois a partir de `design/solis-symbol.svg` mais o
wordmark como texto. Nada é ampliado de PNG. Os antigos foram para
`referencias/brand/_legado/logo/`.

| | proporção | de onde veio |
|---|---|---|
| vertical | cap 10,34% e folga 8,53% da largura do símbolo; wordmark com 74,94% da largura | medido em `mono-wordmark.png`, a apresentação aprovada da marca nova |
| horizontal | cap 24,74% e folga 23,26% da largura do símbolo | medido no lockup antigo — é a única leitura que existe do arranjo lado a lado |

A primeira tentativa escalou o horizontal pela **altura** do símbolo (a razão 57,6% do
lockup antigo) e a arte estourou a moldura: o símbolo novo é proporcionalmente mais alto
que o antigo (0,571 contra 0,429), e o wordmark saiu 20% mais largo que a arte inteira do
lockup antigo. O script hoje tem uma asserção que barra isso.

## Logo da sidebar — fechado em 71px

Medições, todas normalizadas para uma janela de 1440px:

| | símbolo | bloco (símbolo + wordmark) |
|---|---|---|
| referência `espacial` | 71 × 43 | 71 × 63 |
| referência `claro` | 71 × 44 | 71 × 63 |
| leitura do Matheus | — | ~61 × 63 |
| app antes | 110 × 63 | 110 × 97 |
| **app agora** | **71 × 41** | **72 × 63** |

A altura do bloco na referência (63px) bate exatamente com a leitura do Matheus. O 110px
saiu de tratar esses 63px como altura do **símbolo**, quando são a altura do **bloco
inteiro**. A hipótese já estava anotada em `solis-tokens.json` ("se a medida era do bloco
símbolo+wordmark, o valor certo é outro") e a medição confirmou.

O que estava mesmo pequeno era o **wordmark**, não o símbolo — ele saía com cap de 8px
contra os 10,3px da referência. Corrigido junto com a troca de fonte.

Bloco final: **72 × 63** contra os 71 × 63 da referência, 1px de diferença.

### O bloco inteiro é proporcional ao token

Nada dentro do bloco tem px solto. Tudo sai de `--sidebar-logo`:

| | fração |
|---|---|
| altura do símbolo | 57,37% (aspecto do viewBox do SVG) |
| folga símbolo → wordmark | 14,5% |
| `font-size` do wordmark | 20% (dá cap de 14,5%) |
| deslocamento óptico à esquerda | −7,27% |

O respiro até o primeiro item da nav também é calculado daí
(`calc(225px - 87px - var(--sidebar-logo) * 0.9187)`), para que redimensionar o logo não
empurre a navegação. O primeiro item continua a 225px do topo, medido antes e não tocado
aqui.

Comparação visual: `design/logo-sidebar.png`.

## Ritmo vertical da sidebar — alinhado à referência

**Como normalizar.** A referência tem janela útil de 1532 × 1020 e o alvo é 1440 × 930 —
aspectos diferentes (1,50 contra 1,55). Então: horizontal e tamanhos escalam por
1440/1532; posições verticais de coisas ancoradas no **topo** também; mas o bloco de perfil
é ancorado na **base**, e para ele o que se normaliza é a distância até a base. Normalizar
o perfil pelo topo erra o bloco inteiro — foi o que me fez ler 19px de erro onde havia 47.

**Topo da tinta, em px numa janela de 1440 × 930:**

| | referência | app antes | app agora |
|---|---|---|---|
| símbolo | 69 | 87 | **69** |
| wordmark | 122 | 154 | **123** |
| 1º rótulo da nav | 223 | 247 | **223** |
| 2º rótulo | 281 | 302 | **278** |
| passo entre itens | 57,0 | 55 | **57** |
| avatar do perfil | 827,5 | 854 | **829** |
| "Matheus" | 833 | 880 | **831** |
| "Online" | 849 | 896 | **852** |

Do 3º item em diante o app fica um passo abaixo da referência — **é esperado**: a
referência tem 7 itens de nav e o app tem 8, porque "Modelos locais" foi reintroduzido por
decisão de produto.

**O passo era 57, não 55.** A medição anterior saiu do centro da tinta do rótulo, e
"Memória" tem acento e "Configurações" tem cedilha e til: a caixa de tinta delas é mais
alta e o centro desce ~2px. Medindo pelo **topo** da tinta, do 1º ao 7º rótulo dão 60,83px
de passo em 1536 = 57,0 em 1440.

**O perfil não é centrado no bloco.** O conteúdo fica no alto e sobram ~62px de canvas
vazio abaixo do avatar — é assim na referência, nos três temas. O avatar mede 41 × 41 (era
32), a 20px da esquerda. A divisória fica a 113px da base; só o tema `dark` a mostra
visivelmente na referência, nos claros ela existe mas quase não contrasta contra o canvas.

**Nada disso tem px solto.** Todas as posições saem de tokens em
`solis-tokens.json → layout.sidebar`, e o respiro entre o bloco do logo e a nav é calculado
a partir de `--sidebar-logo`, de forma que mexer no tamanho do logo não desloca a
navegação.

Comparação visual: `design/sidebar-vertical.png`.

## Glow reativo — CSS aguenta, e agora tem número

**Pergunta:** o glow precisa ser totalmente natural; se o CSS mantiver o mesmo nível de
qualidade, fica; se não, outro método. **Resposta: fica em CSS/SVG.**

### O que a referência faz

Perfil medido em `brand/states/solis-state-listening.png`, num corte perpendicular ao traço
(traço de 4–5px, pico L=170 sobre fundo `#000410`):

| distância do traço | luminância acima do fundo | % do pico |
|---|---|---|
| ±6px | 15,5 | 9,1% |
| ±12px | 8,7 | 5,1% |
| ±18px | 4,2 | 2,5% |
| ±27px | 2,9 | 1,8% |
| ±33px | 1,9 | ruído de fundo |

Não é uma gaussiana. Uma que fecha em 6px morre bem antes dos 27; a que chega aos 27 borra
o traço. São **duas somadas** — núcleo apertado mais rabo largo e fraco. É por isso que o
filtro tem dois `feGaussianBlur` (σ 2,0 e 9,0) e não um.

### Por que filtro SVG e não `radial-gradient`

O `SOLIS_SIGNATURE.md` previa `radial-gradient` porque a marca era um PNG achatado do qual
não dava pra separar o glow. **A premissa caiu na Fase 2:** a marca é vetor. Um gradiente
radial só sabe iluminar um ponto, e o símbolo é um arco curvo e assimétrico — o halo saía
como uma bolha atrás da arte em vez de luz saindo dela. Com o vetor, o filtro age sobre o
próprio caminho e o halo acompanha o traço.

### O custo, medido

`design/medir-custo-animacao.mjs`, 5 estados animando ao mesmo tempo, janela de 6s a 60fps:

| | tarefa (main thread) | recálculos de estilo |
|---|---|---|
| camada certa (`opacity` + `transform`) | **4ms** | **0** |
| `filter` dentro do keyframe | 133ms | 360 (um por frame) |

33× mais trabalho pelo mesmo efeito. A regra 1 do `PERFORMANCE.md` deixou de ser asserção.

**Contar frames com `requestAnimationFrame` não serve para isso.** Numa cena pequena as duas
versões batem 60fps e a diferença some — as três primeiras medições que fiz deram
p95 = 16,7ms para tudo. O rAF mede cadência do main thread; o que separa uma camada
rasterizada uma vez de uma que refaz o filtro a cada frame é o **trabalho**. Daí a medida
vir do CDP (`Performance.getMetrics`).

### Um erro que a validação visual pegou

A primeira versão seguia o exemplo do `PERFORMANCE.md` ao pé da letra: `opacity` de 0,55 a
0,95 e `scale` de 1,0 a 1,06. Num blob radial pequeno isso funciona. Num símbolo de 190px
de largura, escalar a camada de brilho em 6% desloca o halo ~11px nas pontas e **ele descola
da arte** — vira um fantasma laranja ao lado do traço, visível na folha.

Na referência o brilho pulsa em **intensidade**, não em tamanho. O `scale` caiu para
1,006–1,022 conforme o estado, e quem carrega a respiração passou a ser o `opacity`.

Folha de validação: `design/estados-glow.png` (os 5 estados, em duas fases do ciclo).
Os renders antigos em `brand/states/` foram para `_legado/`: o glow deixou de ser asset e
virou código.

## Como medir uma referência nova — o gerador não segura geometria

Vale para toda tela daqui para frente, e custou duas gerações para ficar claro.

**O gerador de imagem não obedece medida absoluta.** Tentado duas vezes:

| | sidebar (normalizada para 1440) | caixa alta do rótulo da nav |
|---|---|---|
| app (aprovado, construído) | 200px | 10,2px |
| 1ª geração | 267px | 14,1px |
| 2ª geração, com "213px" repetido em maiúscula no prompt | **297px** | **16,9px** |

A segunda tentativa foi **mais longe**, não mais perto. Insistir no prompt não resolve.

**Reconciliar pela sidebar também não serve.** As duas gerações dão fatores diferentes
(0,724 e 0,604) e portanto valores diferentes para a mesma coisa — o título sairia 34px por
uma e 28px pela outra. O gerador escala a sidebar independentemente do conteúdo, então ela
não é régua.

**O que é estável são as razões dentro da área de conteúdo:**

| razão | 1ª geração | 2ª geração |
|---|---|---|
| título / texto do item | 2,11 | 2,00 |
| origem / texto do item | 0,88 | 0,89 |
| data / texto do item | — | 0,94 |

### O método

1. Da referência vêm **estrutura, composição, hierarquia, conteúdo e proporção**.
2. A **escala** vem do design system já construído e aprovado.
3. Âncora: o **corpo de texto**, 16px, fechado desde a tela de Conversa. Todo tamanho de
   tipo da tela nova sai de uma razão contra ele, medida na referência.
4. Geometria horizontal e vertical: medida **relativa à divisória da sidebar** e às
   proporções internas, nunca em px absoluto tirado da imagem.

Isso muda os prompts também: **parar de pôr especificação de pixel neles.** Pedir estrutura,
conteúdo e hierarquia, e deixar a escala comigo — é menos frágil e o resultado sai melhor.

### O que a Memória construída ganhou com isso

Os valores já entregues sobreviveram às duas medições:

| | construído | 2ª geração (razão × 16px) |
|---|---|---|
| título | 34px | 32,0px |
| origem | 14px | 14,2px |
| data | 14px → **15px** | 15,1px |

Só a data mudou, de 14 para 15px.

## Configurações → Aparência, e o modo barra de ícones

Medido em `telas/11-configuracoes-aparencia.png`, com o método das razões: tipografia
ancorada no corpo de 16px, geometria em fração da área de conteúdo.

| | razão contra o corpo | px |
|---|---|---|
| título da tela | 1,89 | 34px (o mesmo token da Memória) |
| "Aparência" (título da seção) | 1,22 | 20px |
| rótulo do controle | 1,00 | 16px |
| descrição sob o rótulo | 0,94 | 15px |

Miniaturas de 279 × 182 (razão 1,53), 27px de folga; seletor segmentado de 387 × 62;
interruptor de 79 × 41. Cápsula da barra de ícones: 805 × 124, centrada na janela, a 38px
da base.

### As miniaturas de tema não são desenho, são a coisa

Cada miniatura é um `data-theme` local, e desenha a prévia com as **custom properties do
tema que ela representa** — inclusive a foto do horizonte, ancorada embaixo pelo mesmo
mecanismo da tela real. Consequência: elas não podem divergir do tema de verdade, porque
leem exatamente os mesmos tokens. Uma ilustração pintada à mão divergiria na primeira vez
que uma cor mudasse — e neste projeto as cores já mudaram três vezes.

### "Barra de ícones" é substituição, não complemento

Foi o erro da primeira geração da referência, e o produto não pode repeti-lo: com esse modo
a sidebar **deixa de existir**. O que muda no código:

- `App` não monta a `Sidebar`; monta a `BarraIcones`, que consome o mesmo `nav-items`.
- A camada da cena passa a começar na borda da janela, não na divisória — por
  `:root[data-nav="icones"] .cena-camada { left: 0 }`.
- A Conversa deixa de ser uma coluna encostada à esquerda e vira um bloco centralizado.

O modo vai pro DOM como atributo (`data-nav`) pelo mesmo motivo do tema: quem precisa saber
é o CSS, e atributo só repinta.

**Falta o cabeçalho desse modo.** A referência mostra, no topo, o símbolo com a palavra
SOLIS na horizontal e, no canto direito, um ícone de sino e um de perfil. Não foi
construído: são componentes novos e dois ícones que ainda não existem em `icons.tsx`.

## As telas restantes — fechadas

Modelos locais, Ferramentas, Tarefas, Agenda, Conhecimento e a Conversa com thread.
Referências `telas/13-` a `18-`, medidas pelo método das razões.

### Uma moldura só, não seis

`src/components/Tela.tsx` carrega o padrão que se repete em todas: título, subtítulo,
ação opcional à direita, e a área de conteúdo que rola até a base. As referências das seis
confirmam o mesmo padrão que Memória e Configurações já tinham — e ter um componente só é o
que garante que ele continue igual quando uma delas mudar.

### Decisões de forma que a referência não decide sozinha

**Modelos locais.** "Em uso" é etiqueta preenchida, "Embeddings" é só texto. Um é estado do
sistema agora, o outro é uma função permanente; dar o mesmo peso visual esconderia qual
modelo está rodando.

**Ferramentas.** Os sete interruptores ficam numa coluna alinhada, inclusive o da linha com
permissão negada — que numa das gerações saía da coluna. Esta é uma tela de confiança antes
de ser de configuração: é onde a pessoa vê de uma olhada o alcance que deu ao assistente, e
uma coluna quebrada justo na linha mais delicada atrapalha exatamente onde não pode.

**Tarefas.** A caixa de seleção é desenhada, não `<input type=checkbox>`: o nativo não aceita
cor de traço nem raio consistentes entre sistemas, e esta interface precisa parecer a mesma
no Windows e no Mac. O papel fica pelo `role`/`aria-checked`.

**Agenda.** Linha do tempo do dia, não grade de mês. A grade responde "que dia é hoje"; a
linha do tempo responde "o que vem agora", que é a pergunta que se faz a um assistente. Os
buracos entre horas são informação: mostram onde sobra tempo.

**Conhecimento.** Grade de cartões e não lista, porque cada fonte é um objeto com identidade
— nome, tipo, tamanho, estado de indexação —, não uma linha de texto. É o que separa esta
tela de Memória, onde cada item é uma frase.

**Conversa com thread.** A diferença entre quem fala é deliberadamente sutil:

- a pessoa vem à direita, num bloco com véu e teto de 66% da largura, porque o que ela
  escreve é curto e delimitado;
- o Solis vem à esquerda, sem fundo, ocupando a largura toda. A resposta dele é texto longo,
  e texto longo dentro de um balão vira uma coluna estreita e cansativa.

**Não há confirmação de leitura.** Uma das gerações trouxe os dois tiquinhos de "lida" e foi
descartada: não existe entrega nem leitura aqui. O Solis roda na mesma máquina, não há rede
entre as pontas e não há outra pessoa do outro lado — o indicador contaria uma história falsa
sobre o que o app é.

### Variantes descartadas

Três gerações alternativas foram para `referencias/telas/_variantes/`, com o motivo de cada
descarte escrito. Duas referências da mesma tela dentro de `telas/` seriam uma contradição
esperando pra virar bug.

### Cabeçalho do modo barra de ícones

Fechado. Sem sidebar a marca sumia da tela, e com ela a única âncora que diz onde a pessoa
está. O cabeçalho devolve a marca ao topo, na horizontal, com os dois atalhos que na sidebar
viviam no bloco de perfil. É `fixed` e não no fluxo: neste modo a Conversa centraliza o
conteúdo na altura da janela, e um cabeçalho no fluxo empurraria esse centro.

Comparação visual: `design/telas-restantes.png`.

## Varredura de fechamento — 8 telas × 3 temas

`npm run varrer` (com o preview de pé) percorre toda combinação de tela e tema procurando o
que só aparece quando se olha tudo junto:

- **erro de runtime** em qualquer combinação;
- **estouro horizontal** — conteúdo mais largo que a janela;
- **contraste de cada texto contra o fundo que ele realmente tem**, lido do DOM e não do
  token. É o que pega o texto que herdou a cor errada, e nenhuma medição por token pegaria.

A primeira rodada achou dois: `"Permissão negada"`, em Ferramentas, a 3,11:1 no `claro` e
2,75:1 no `espacial`. A cor de erro do DS (`#E4674A`) foi desenhada contra fundo escuro e não
aguenta canvas claro.

Derivada por tema, pelo mesmo método das secundárias e do accent — só o L em OKLCh, matiz
travado:

| tema | antes | derivado | depois | ΔEOK |
|---|---|---|---|---|
| espacial | 2,75:1 | `#BA4024` | 4,52:1 | 0,1212 |
| claro | 3,11:1 | `#C44A2E` | 4,52:1 | 0,0914 |
| dark | 6,04:1 | (mantido `#E4674A`) | — | — |

Ela virou papel de tema (`--erro`), não constante global — pelo mesmo motivo que canvas e
divisória são: o valor certo depende do fundo em que a cor cai.

Segunda rodada: **limpa**. 8 telas × 3 temas, sem erro, sem estouro, nada abaixo de 4,5:1.

## Depois de ver no ar — o que a Vercel revelou

Sete coisas apareceram só com o app rodando, e cinco delas não apareceriam em captura
nenhuma. Vale registrar por quê.

### 1. Não havia movimento nenhum

O clique era corte seco: a tela trocava no mesmo quadro. Sem transição, uma interface não
parece rápida — parece que pisca. Foi a primeira coisa que o Matheus sentiu, e "muito forte".

Entrou:

| | duração | o quê |
|---|---|---|
| troca de tela | 190ms | `opacity` 0→1 com 10px de deslocamento |
| passar o mouse | 140ms | opacidade, fundo e cor |
| apertar | 90ms | `scale(0.97)` |

Medido quadro a quadro: 0ms em opacity 0 e 10px deslocado, 78ms em 0,66, 150ms em 0,97,
213ms parado. Só `transform` e `opacity`, como manda o `PERFORMANCE.md` — e aqui isso não é
só disciplina de performance, é o que permite animar em cada clique sem custo. Medido com
`npm run varrer` e `design/medir-custo-animacao.mjs`: **9ms** de main thread em 6 segundos,
zero recálculo de estilo.

As regras usam `:where()`, que mantém a especificidade em zero — qualquer regra do
componente continua ganhando.

### 2. A barra de ícones estava 35% grande demais

805 × 124. A medida saiu da referência, mas a referência foi desenhada numa escala ~35%
maior que a do app — o mesmo desvio já documentado em `layout.memoria._escala`. Numa janela
de 866px de altura, 124px era 14% da altura só de navegação: ela competia com o conteúdo em
vez de servi-lo. Agora **620 × 76**.

### 3. Flutuar virou cobrir

A cápsula e o cabeçalho são `fixed`. Nas telas de conteúdo isso escondia a última linha — em
Configurações, "Exibir imagem de fundo" ficava atrás da barra. No modo `icones` as telas
passaram a reservar o espaço dos dois.

### 4. O fundo translúcido não funcionava

A cápsula tinha véu, e o texto de trás aparecia através dela. Virou quase opaca
(`color-mix` com 92% do canvas) mais uma sombra estática.

**Sem `backdrop-filter` de propósito.** Vidro embaçado obriga o navegador a repintar a região
a cada scroll, e o `PERFORMANCE.md` pede o contrário. Fundo quase opaco resolve a
legibilidade pelo mesmo preço — que é zero.

### 5. Os chips flutuavam sobre a foto

Contorno fino sozinho, sobre o horizonte, sumia: a borda delimitava um retângulo que o olho
não fechava. Ganharam superfície própria, com o mesmo véu do canvas — não opaca a foto atrás.
E um véu mais forte no hover, porque sobre uma superfície que já tem véu o hover normal seria
invisível.

### 6 e 7. Composer e chips altos demais

79 → **64px** no composer, 58 → **46px** nos chips, com o texto de 15 para 14. Ambos eram
medida de referência que, na escala real, dava peso a mais para o que os elementos contêm —
uma linha de texto e um rótulo curto.

### 8. O composer era largura fixa

805px numa janela de 1900 deixava o campo desproporcional, com vazio dos dois lados.
Virou `clamp(560px, 65%, 980px)`.

**65% não abandona a medida — é a mesma medida escrita como proporção.** Os 805px são
exatamente 65% da área de conteúdo na janela de 1440 em que a referência foi medida, e o
app renderiza 806px lá. O piso de 560 impede que ele fique estreito demais numa janela
pequena; o teto de 980 impede que uma linha de texto vire uma faixa larga demais pra ler de
um golpe de olho.

| janela | composer | % da área de conteúdo |
|---|---|---|
| 1280 × 800 | 702px | 65% |
| 1440 × 930 | **806px** | 65% |
| 1900 × 866 | 980px | 58% (no teto) |
| 2560 × 1080 | 980px | 42% (no teto) |

**Uma armadilha de CSS no caminho.** A primeira tentativa deu 615px em vez de 806: a coluna
tinha `paddingLeft: 191`, e uma largura em porcentagem resolve contra o bloco que a contém —
os 191px entravam na conta. Trocado por `marginLeft`, que não muda a base do cálculo.

Os chips seguem a mesma largura. Antes cada um tinha medida independente, e numa janela larga
um esticava e o outro não — o tipo de desalinho que só aparece fora dos 1440px da referência.

### 9. E aí a âncora de 191px virou o novo torto

Com o composer elástico, o campo para de crescer no teto de 980px — mas a coluna continuava
presa aos 191px medidos da sidebar. Numa janela de 1900 isso dava **360px de vão à esquerda e
516px à direita**: o bloco inteiro escorado no canto esquerdo com um vazio maior do outro lado.
A âncora só é uma proporção enquanto o campo ainda acompanha a janela; passado o teto, ela vira
exatamente o desalinho que o clamp foi consertar.

A regra saiu do style inline e foi pro CSS, onde `max()` sobre porcentagem cabe:

```css
.conversa-coluna {
  width: var(--composer-width);
  margin-left: max(var(--conversa-ancora), (100% - var(--composer-max)) / 2);
  max-width: calc(100% - var(--conversa-ancora));
}
```

Abaixo do teto o `max()` devolve os 191px e **nada muda** — a medida de 1440 continua exata.
A partir do teto ele devolve a metade da sobra, e a coluna centraliza.

| janela | composer | vão esquerdo | vão direito |
|---|---|---|---|
| 1280 × 800 | 702px | 191 | 187 |
| 1440 × 930 | **806px** | **191** | **243** (a referência, intacta) |
| 1900 × 866 | 980px | 360 | 360 |
| 2560 × 1080 | 980px | 690 | 690 |

O teto e a âncora viraram tokens próprios (`composer.maxWidth`, `composer.anchorLeft`) porque
agora um depende do outro — deixar os 980 escritos em dois lugares era garantir que um dia
divergissem.

### 10. E o erro maior: todo o ritmo vertical era px absoluto

O composer foi consertado no eixo horizontal e o problema real estava no vertical.

**A janela de referência não existe no navegador.** Tudo na Fase 2 foi medido em
1440 × 930 — a altura útil de um app desktop. Um notebook de 1920 × 1080 a 125% de escala
dá 1536 × 864 CSS, e o Chrome come ~170px em aba, barra de endereço e favoritos. Sobram
**693px**. Medido no app com o ritmo em px absolutos, nessa janela:

| | 1440 × 930 (referência) | 1532 × 693 (navegador) |
|---|---|---|
| altura que a sidebar pede | 769px | 769px |
| altura disponível | 930px | **693px** |
| a página rola? | não | **sim** |
| bloco de perfil | 113px | **53px, espremido e cortado** |
| topo do "Olá, Matheus." | 298px = 32% da janela | 298px = **43% da janela** |

Os três sintomas são o mesmo defeito. A sidebar tem um piso duro — 8 itens de 57px, mais o
bloco do logo, mais o perfil — e quando ele não cabe, o flex espreme o que puder e o resto
vira barra de rolagem. E um título ancorado a 43% da altura empurra o bloco inteiro pra
metade de baixo, esmagando a faixa do horizonte contra o rodapé.

**A solução é a mesma do composer, no outro eixo.** Cada medida vertical vira a proporção
que ela tinha em 930, com piso e teto:

```
clamp(V × 0,80,  (V / 9,3)vh,  V)
```

Em 930px de altura o `vh` bate exatamente no teto e **a referência fica intacta, px a px**.
Abaixo disso tudo encolhe junto — passo, respiro, bloco do logo, altura do perfil, topo do
título — então a relação entre os elementos é preservada. Não é cada valor achatando por
conta própria.

O piso de 0,80 não é arbitrário: a 0,80 a sidebar fecha em 613px e cabe numa janela de 640,
que é o que um notebook de 1366 × 768 entrega com o Chrome aberto.

Medido depois:

| janela | página rola | passo da nav | perfil | topo do título |
|---|---|---|---|---|
| 1440 × 930 | não | **57px** | **113px** | **298px** |
| 1532 × 693 | não | 46px | 90px | 238px |
| 1366 × 640 | não | 46px | 90px | 238px |
| 1920 × 1080 | não | **57px** | **113px** | **298px** |

A linha de 1440 e a de 1920 são idênticas à referência — o teto garante isso.

Duas correções estruturais foram junto, porque o clamp sozinho não bastava:

- **`shrink-0` no bloco de perfil.** Ele tem altura medida, não é folga. Sem isso o flex o
  espremia de 113 para 53px e o "Online" saía cortado ao meio.
- **`min-h-0` + `overflow-y` na lista de itens**, e `overflow: hidden` na sidebar. A lista é
  a única parte que pode rolar; a coluna nunca empurra a página.

A constante de 23px entre o topo da caixa do item e a tinta do rótulo virou 40,35% do passo.
Ela era metade da folga do passo — com o passo encolhendo, uma constante fixa subiria o
primeiro rótulo. Em 930: 57 × 0,4035 = 23,0, a medida da referência.

### A varredura ganhou a janela do navegador

Nada disso aparecia na varredura porque ela rodava só em 1440 × 930. Agora roda em duas
janelas e checa mais duas coisas: se a **página rola** (o Solis é app — o que rola é a área
de conteúdo, nunca o documento) e se alguma caixa **corta conteúdo**.

A segunda existe porque a primeira sozinha era guarda falsa: o `overflow: hidden` que eu
tinha acabado de pôr na sidebar troca a barra de rolagem por conteúdo cortado, que é pior e
não aparece em nenhuma medida de altura. Testado reinjetando as medidas antigas no app
corrigido: a checagem de rolagem não acusou nada, a de corte acusou
`<ul> precisa de 456px e tem 380px`. Uma guarda que não falha quando deveria não vale nada.

### O que continua sendo diferença de web para app

A janela do navegador não é a janela do Tauri: barra de endereço, aba e a proporção que o
sistema dá. Parte do "não está encaixado no PC" é isso e some no empacotamento. O que **não**
era isso — e foi consertado — é tudo acima.

## Ainda em aberto

1. **Backend** — SQLite+FTS5, Ollama, Whisper, Piper. Nada começou, por decisão: primeiro o
   preview do front no ar. Ver `PREVIEW.md` na raiz do repositório.

## Fechado nesta rodada

- **Posição vertical da sidebar.** Estava marcada como pendente por engano — foi resolvida
  junto com o ritmo vertical: símbolo em 69 contra 69 da referência, primeiro rótulo da nav
  em 223 contra 223, avatar em 829 contra 827,5. Não há divergência.
- **Referência do card Aparência.** Chegou em `telas/11-configuracoes-aparencia.png`, com os
  três controles corretos e sem "Cor de destaque".
