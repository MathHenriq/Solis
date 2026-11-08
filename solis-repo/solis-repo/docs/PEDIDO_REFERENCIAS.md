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

## 5. Lista de conversas e "Nova conversa" — pedido em 1º/11/2026

Problema 3 de `docs/ESCOPO.md` → "Próximas tarefas". Padrão pedido pelo Matheus: a interface
do Claude (lista de recentes + nova conversa), adaptada à identidade do Solis. Decisão de
desenho: a lista vive num painel dentro da tela de Conversa, e não na sidebar — a sidebar já
tem os 8 itens de navegação, e um painel próprio funciona igual nos dois modos de navegação.
**Revisto em 08/11/2026:** construída por esta referência, ficou pesada; a lista foi refeita no
padrão do próprio Claude, dentro da sidebar (ver `docs/ESCOPO.md`, problema 3).

Prompt entregue ao Matheus pra gerar no GPT (anexando `telas/18-conversa-thread.png` e
`telas/tema-dark.png`): ver o histórico da conversa de 1º/11 ou a resposta do Claude daquele
dia. O que a imagem tem que mostrar: painel com "Nova conversa", busca, grupos por data (Hoje,
Ontem, Últimos 7 dias), a conversa aberta destacada, um item em hover, e a thread à direita.

## 6. Etapas do pensamento — pedido em 1º/11/2026

Problema 2 de `docs/ESCOPO.md` → "Próximas tarefas". A thread no meio de uma resposta: o
símbolo do Solis no estado "pensando" e uma lista de etapas reais (memória buscada, cérebro
escolhido, o modelo pensando com o tempo correndo), mais uma resposta anterior já concluída
com as etapas recolhidas e a confirmação "Memória guardada".

## 7. Memória: esquecer e corrigir — pedido em 08/11/2026

O último item da fase "Memória completa" (`docs/ESCOPO.md`). Hoje a tela de Memória só lista e
busca: não dá pra apagar uma memória errada nem consertar uma meio certa. O servidor já
esquece (`DELETE /memorias/{id}`, e a memória que ela tinha substituído volta a valer); corrigir
entra junto com a tela. Também falta marcar na lista o que é privado (criptografado desde
08/11), que hoje aparece igual às outras.

**Base pra gerar:** `telas/_bases/memoria-atual-dark.png` — o print da tela como ela está hoje
no app (com os dados de exemplo da 09, a sidebar nova com os Recentes e um item em hover). É
melhor o gerador **editar** este print do que desenhar do zero: foi quando as gerações saíram
com a geometria certa. Valem as 6 regras do topo.

**Três imagens, no tema dark** (os outros dois temas depois, como sempre):

1. `21-memoria-acoes.png` — a lista com:
   - um item em hover mostrando as duas ações, **Corrigir** (lápis) e **Esquecer** (lixeira),
     à direita do item;
   - outro item **em edição**: o texto virou um campo editável, com o cursor, e os botões
     **Salvar** e **Cancelar** embaixo;
   - a memória "Tem alergia a frutos do mar." marcada como **privada** (um cadeado pequeno, ou
     "privada" junto de "de: Saúde e bem-estar").
2. `22-memoria-esquecer.png` — a confirmação de esquecer **no próprio item** (nada de janela
   no meio da tela): "Esquecer esta memória? O Solis deixa de usar isso." com **Esquecer** e
   **Cancelar**.
3. `23-memoria-esquecida.png` — logo depois: a lista sem aquele item e um aviso discreto
   embaixo, "Memória esquecida", com **Desfazer**.

**Prompt pro GPT** (anexando `telas/_bases/memoria-atual-dark.png`; um por imagem, trocando só
a lista de mudanças):

> Edite a imagem anexada, que é a tela de Memória de um app desktop chamado Solis. Mantenha
> TUDO idêntico — tamanho da imagem (1536×1024), sidebar inteira, cores, fontes, tamanhos de
> texto, espaçamentos, a lista e os textos das memórias. Não mude nada que não esteja na lista
> abaixo. Mude só:
> [para a 21] (1) no item "Está construindo o Solis…", que está em hover, mostre à direita do
> texto duas ações pequenas, um lápis com "Corrigir" e uma lixeira com "Esquecer", no mesmo
> cinza da data; (2) o item "Prefere ser chamado de Matheus, não de Mateus." está sendo
> editado: o texto virou um campo de texto com borda fina e o cursor no fim, e embaixo dele
> há dois botões, "Salvar" (destaque na cor dourada do app) e "Cancelar" (só texto); (3) no
> item "Tem alergia a frutos do mar.", ponha um cadeado pequeno antes de "de: Saúde e
> bem-estar", no mesmo cinza.
> [para a 22] no item "Trabalha melhor de manhã cedo, entre 6h e 10h.", troque a linha de
> baixo por uma confirmação na própria linha: "Esquecer esta memória? O Solis deixa de usar
> isso." e dois botões à direita, "Esquecer" (vermelho discreto) e "Cancelar" (só texto).
> [para a 23] tire o item "Trabalha melhor de manhã cedo, entre 6h e 10h." da lista (os de
> baixo sobem) e mostre, centralizado na parte de baixo da área da lista, um aviso pequeno e
> discreto, com fundo um pouco mais claro que o da tela e cantos arredondados: "Memória
> esquecida" e, à direita, "Desfazer" na cor dourada.
> Português do Brasil, com acentos corretos. Saída em PNG.

## O que eu NÃO preciso

- Lockups da marca — já são gerados do vetor (`design/gerar-lockups.py`).
- Renders de glow — o glow virou código (`src/components/SolisEstado.tsx`).
- Ícone de app e favicon — derivados do vetor (`design/gerar-assets.py`).
- Variações de cor da mesma tela: eu amostro por pixel e derivo o que precisar.
