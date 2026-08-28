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
só. O wordmark SOLIS **não** é Playfair — é uma sans geométrica leve com tracking largo, e
qual sans é essa continua em aberto (é o que trava os lockups de `brand/logo/`).

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

## Ainda em aberto

1. **A sans do wordmark SOLIS** — é o que trava os lockups de `brand/logo/`, que continuam
   com o símbolo antigo. O wordmark tem só 40px de altura de tinta na folha do símbolo
   refinado e 100px no lockup antigo: traçar letra nessa resolução entrega tipografia pior
   que a original. O caminho certo é compor o wordmark como texto de verdade, e para isso
   falta identificar (ou escolher) a sans geométrica leve da folha. Não é a Playfair — essa
   é só da saudação. Enquanto isso a sidebar renderiza SOLIS em `system-ui` com tracking de
   0,34em, que é substituto, não a fonte final.
2. **`brand/states/`** — os 3 renders com glow são do símbolo antigo e não derivam do
   vetor. Se a arquitetura do `SOLIS_SIGNATURE.md` for mantida (glow como camada CSS
   atrás da arte), eles deixam de ser necessários em vez de precisarem ser regerados.
3. **Referência visual do card Aparência** — ele vai ganhar o seletor de tema e o seletor
   Sidebar/Ícones, e perder "Cor de destaque". A referência atual
   (`telas/06-configuracoes.png`) é anterior a tudo isso.
