# referencias/

Fonte visual da verdade do Solis. Toda decisão de UI é validada contra estas imagens (ver
Regra 1 e 2 no CLAUDE.md da raiz). Os números já extraídos delas estão em
`docs/MEDICOES_FASE2.md` — consultar de lá em vez de re-medir.

## telas/

### Fase 2 — sistema de temas (as mais recentes; mandam no visual atual)

| Arquivo | Tema |
|---|---|
| `tema-espacial-vinho.png` | Cena fotográfica de nascer do sol, texto em vinho escarlate. Sidebar em 13,9% |
| `tema-claro-padrao.png` | **Mesma** cena fotográfica, texto em preto suave. Sidebar em 13,9% |
| `tema-dark.png` | Fundo quase preto, sem foto, só o glow sutil de horizonte. Sidebar em 14,1% |

Os temas "Espacial" e "Bege+vinho" do pedido original convergiram numa imagem só —
correlação medida de 0,98 entre as duas telas na faixa do horizonte confirma que é a mesma
foto, variando só a cor do texto/acento.

**Cuidado ao usar estas 3 telas:** elas valem pro *estilo* (cor, medida, tipografia). Elas
**não** valem pra lista de itens da navegação (aparecem com 7, faltando "Modelos locais")
nem pra composição do campo de entrada (o microfone não aparece). Os dois casos foram
confirmados como omissão do gerador de imagem, não decisão de produto — ver a tabela de
divergências em `docs/MEDICOES_FASE2.md`.

### Anteriores

| Arquivo | Tela |
|---|---|
| `01-conversa-inicio.png` | Conversa — estado vazio / abertura (com hero + horizonte grande) |
| `02-conversa-thread.png` | Conversa — com histórico de mensagens |
| `03-modelos-locais.png` | Modelos locais (Ollama) |
| `04-modelos-locais-alt.png` | Modelos locais — variação |
| `05-memoria.png` | Memória |
| `06-configuracoes.png` | Configurações |
| `07 - Background.png`, `08-Background Novo.png` | Estudos de fundo. **Não são** a cena usada nos temas da Fase 2 (correlação 0,49 e 0,32) |

Telas ainda sem referência dedicada (construir seguindo o padrão visual das existentes, e
pedir referência ao Matheus antes de finalizar): Ferramentas, Tarefas, Agenda, Conhecimento.

## brand/

### symbol-refinado/ — símbolo oficial atual

Substitui o símbolo anterior em todo o sistema (SolisSymbol, ícone de app, favicon, logo da
sidebar). Arco com pontas finas, curva mais graciosa. Aprovado em 24×24px real nos 4 fundos.

- `mono-wordmark.png` — monocromático com o wordmark SOLIS. **É a fonte de maior resolução**
  (387×221px de tinta) e por isso é dela que sai a vetorização.
- `sobre-fundo-escuro.png` / `-claro.png` / `-ambar.png` / `-creme.png` — aplicações de
  referência em cada fundo
- `folha-completa-comparacao.png` — a folha original inteira, contexto

**Nenhum destes tem canal alpha** — são RGB sobre branco `#FEFEFE`. Não recortar à mão pra
usar sobre fundo colorido: o vetor em `design/solis-symbol.svg` é o asset de uso.

Derivados do vetor, com alpha real, pros usos que não aceitam SVG:
`solis-symbol-mono-claro.png` (tinta `#F5F0E7`, pra fundo escuro) e
`solis-symbol-mono-escuro.png` (tinta `#071019`, pra fundo claro), ambos 2048px.

### app-icon/ e favicon/ — derivados do vetor

Gerados por `design/gerar-assets.py` a partir de `design/solis-symbol.svg`. Nenhum é
ampliação de outro PNG.

- `app-icon/` — `solis-app-icon.png` (1024), `icon-{16..1024}.png` e `solis.ico`
  (7 tamanhos embutidos, payload PNG por entrada).
- `favicon/` — `favicon.svg`, `favicon.ico` (16/32/48) e PNGs de 16/32/180.

Fundo `#07080D` (`themes.dark.canvas`, pra bater com o tema padrão do app) e tinta
`#F5F0E7` (`color.warmWhite`, a tinta medida na aplicação aprovada em
`symbol-refinado/sobre-fundo-escuro.png`). O símbolo ocupa 76% do quadrado nos tamanhos
grandes e cresce até 92% em 16–24px — ajuste óptico deliberado, porque a legibilidade foi
validada a partir de 24px **do símbolo**, e 76% de um canvas de 16px deixaria só 12px de
marca.

**Diferença de caráter em relação ao ícone anterior:** o antigo era um render com glow e
bloom; este é traço chapado, que é o que o vetor sustenta e o que a folha de aplicações
aprovada mostra. É também o que o mantém legível em 16px.

### logo/, states/ — geração anterior

Desenhados sobre o símbolo **antigo**, ainda não regerados. Ver `brand/_legado/README.md`
pro motivo de cada um. Pendência herdada: não há asset aprovado para o estado "Executando"
sem raios de sol (ver `docs/HANDOFF.md`).
