# O que eu preciso que você gere de referência

Ordem de prioridade. O item 1 é o único que está travando trabalho agora.

## Regras que valem para todas

Estas não são preferências — sem elas eu não consigo medir, e medir é o que a
Regra 2 do `CLAUDE.md` exige.

1. **Mesma janela das 3 telas de tema.** `1536 × 1024`, janela cheia, sem sombra de
   página em volta e sem moldura de navegador. As referências boas que já temos
   (`telas/tema-espacial-vinho.png`, `tema-claro-padrao.png`, `tema-dark.png`) são o
   padrão — se der, gere a partir de uma delas, pedindo para trocar só o conteúdo da
   área à direita da sidebar.
2. **PNG, sem compressão com perda.** JPEG borra a borda do traço e eu perco 1–2px em
   toda medição de espaçamento.
3. **A sidebar tem que aparecer inteira**, do logo ao bloco de perfil. É ela que me dá a
   escala: eu normalizo tudo pela largura da janela e pela posição da divisória.
4. **Um tema por arquivo, os 3 temas.** Não preciso das 3 de cara — mande o `dark`
   primeiro, eu construo, e aí você gera os outros dois para eu conferir as cores. Mas
   preciso saber que os 3 vão existir, porque cor eu amostro por pixel e não converto
   entre temas.
5. **Nada de texto inventado em português macarrônico.** Se o conteúdo de exemplo tiver
   erro de acentuação, eu não consigo distinguir "é assim que tem que ser" de "o gerador
   errou" — e já perdemos tempo com isso (o microfone e o "Modelos locais" sumiram das 3
   telas por omissão do gerador, não por decisão).
6. **Estado cheio, não vazio.** Tela com conteúdo de verdade me dá espaçamento entre
   itens, altura de linha, comportamento de lista. Tela vazia só me dá a moldura.

---

## 1. Memória — TRAVANDO

`referencias/telas/05-memoria.png` é da geração antiga: símbolo antigo, sidebar larga,
paleta anterior aos 3 temas. Construir por ela produz uma tela que destoa da Conversa.

**O que a tela precisa mostrar:**

- A sidebar já validada, com **Memória** como item ativo.
- Uma **lista de memórias** com pelo menos **6 itens visíveis** e o 7º cortado pela
  borda de baixo — é o corte que me diz a altura real da linha e se a lista rola.
- Cada item com: o texto da memória (uns com 1 linha, uns com 2, pelo menos um com 3 —
  preciso ver como a altura da linha responde), uma **data ou "há X dias"**, e alguma
  marca de origem (de qual conversa veio).
- Um **campo de busca** no topo, porque Memória é FTS5 e busca é a função principal.
- Pelo menos **um item selecionado ou em hover**, para eu amostrar a cor do estado.
- Um **cabeçalho** com o nome da tela e a contagem ("128 memórias", por exemplo).

**O que me ajuda muito e é fácil de esquecer:**

- Uma segunda imagem com **o estado vazio** ("nenhuma memória ainda"). O
  `docs/ERROR_STATES.md` cobra isso e eu não tenho referência de nenhum estado vazio.

**Símbolo.** Se a tela precisar do símbolo, use os arquivos com alpha real:
`referencias/brand/symbol-refinado/solis-symbol-mono-claro.png` (para fundo escuro) e
`solis-symbol-mono-escuro.png` (para fundo claro). Não use os lockups de `brand/logo/`
como recorte — eles têm o wordmark junto.

---

## 2. Configurações → card Aparência

A referência atual (`telas/06-configuracoes.png`) é anterior ao sistema de temas.

Mudou o que o card contém:

- Entrou o **seletor de tema** com os 3 nomes: Espacial, Claro, Dark.
- Entrou o **seletor de navegação**: Sidebar ou Barra de ícones.
- Entrou o **interruptor "Exibir imagem de fundo"**.
- **Saiu "Cor de destaque"** — decisão sua, o accent passou a ser fixo por tema.

Preciso ver como esses controles são desenhados: o seletor de tema é uma linha de
miniaturas? radio? Isso muda o componente inteiro.

---

## 3. Barra de ícones (o modo alternativo de navegação)

Existe uma decisão registrada de que a navegação é configurável — sidebar **ou** barra de
ícones. A referência `telas/01-conversa-inicio.png` mostra a barra de ícones, mas é da
geração antiga.

Preciso da **mesma tela de Conversa que já está construída**, só que com a barra de ícones
no lugar da sidebar, no tema `dark`. Sem isso eu não sei onde o fundo fotográfico começa
nesse modo (hoje ele começa na divisória da sidebar), nem a altura da barra.

---

## 4. As telas seguintes, quando chegarmos nelas

Na ordem do `CLAUDE.md`: Modelos locais, Ferramentas, Tarefas, Agenda, Conhecimento.
Não precisa gerar agora — uma por vez, quando a anterior fechar. Mas quando for gerar,
valem as mesmas 6 regras do topo, mais o "estado cheio".

---

## O que eu NÃO preciso

- Lockups da marca — já são gerados do vetor (`design/gerar-lockups.py`).
- Renders de glow — o glow virou código (`src/components/SolisEstado.tsx`).
- Ícone de app e favicon — derivados do vetor (`design/gerar-assets.py`).
- Variações de cor da mesma tela: eu amostro por pixel e derivo o que precisar.
