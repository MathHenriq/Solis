# _a-revisar/

Referências geradas que **divergem do que foi pedido**. Ficam fora de
`referencias/telas/` de propósito: a Regra 1 do `CLAUDE.md` diz que o que está lá é a
fonte da verdade, e tratar estas três como verdade contradiria decisões já fechadas.

Não construir nada a partir delas sem o Matheus decidir antes.

## `memoria-espacial.png` — paleta errada

O gerador leu "Espacial" como *espaço sideral* e entregou nebulosa rosa sobre fundo
escuro. O tema `espacial` do Solis é o oposto: canvas bege quente `#FAE7D0`, texto vinho
`#4A0A09`, destaque `#A25500` — é a paleta de `telas/tema-espacial-vinho.png`, já
aprovada e já implementada.

O layout da tela está certo. É só a paleta.

## `configuracoes-aparencia.png` — três divergências

1. **"Cor de destaque" voltou.** A fileira de 8 bolinhas coloridas foi removida por
   decisão registrada do Matheus: o accent é fixo por tema.
2. **Controles que não existem:** "Tamanho da fonte" e "Densidade da interface".
3. **Cards de tema são ilustrações** (lua, planeta, sol) em vez de miniaturas da própria
   tela, e o tema `dark` aparece como "Escuro".

Também introduz uma coluna de sub-navegação dentro de Configurações que não existe em
nenhuma outra tela — pode ser uma boa ideia, mas é decisão de produto, não algo a copiar
sem passar pelo Matheus.

## `conversa-barra-icones.png` — não é a barra de ícones

Mantém a sidebar e acrescenta uma barra de ferramentas **abaixo do campo de texto** (Novo
chat, Anexar, Buscar, Código, Imagem…). O pedido era o modo **alternativo à sidebar**: sem
coluna lateral nenhuma, com os 8 itens de navegação numa cápsula flutuante no rodapé.

O que veio é um complemento da sidebar, não a substituição dela. Continua sem resposta a
pergunta que travava: onde o fundo fotográfico começa quando não há divisória de sidebar.
