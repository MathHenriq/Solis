# _legado/

Assets desenhados sobre o **símbolo antigo**, mantidos só como histórico. Não usar em
tela nova.

- `symbol/` — substituído integralmente por `design/solis-symbol.svg` (vetor, escala em
  qualquer tamanho) e pelos PNGs com alpha em `brand/symbol-refinado/`.

Continuam fora desta pasta, ainda em uso, mas também desenhados sobre o símbolo antigo:

- `brand/logo/` — os dois lockups (horizontal e vertical). **Pendente de regeneração**, e
  ela depende de uma decisão que não é minha: o wordmark tem 40px de altura de tinta em
  `symbol-refinado/mono-wordmark.png` e 100px no lockup antigo. Traçar letra nessa
  resolução entrega tipografia pior que a original — o caminho certo é fechar a fonte do
  DS (hoje `PROVISÓRIO` nos tokens, entre Inter/Sora/Manrope/Poppins) e compor o wordmark
  como texto, que aí escala e continua editável. Enquanto isso não acontece, o lockup fica
  com o símbolo antigo.
- `brand/states/` — listening, rings-soft, rings-strong. São renders com glow, não
  desenho de traço: não dá pra derivar do vetor. Vale notar que o `SOLIS_SIGNATURE.md` já
  prevê o glow como **camada CSS separada atrás da arte** — se essa arquitetura for
  mantida, estes 3 arquivos deixam de ser necessários em vez de precisarem ser regerados.
