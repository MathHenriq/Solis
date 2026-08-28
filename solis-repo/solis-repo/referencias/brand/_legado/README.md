# _legado/

Assets desenhados sobre o **símbolo antigo**, mantidos só como histórico. Não usar em
tela nova.

- `symbol/` — substituído integralmente por `design/solis-symbol.svg` (vetor, escala em
  qualquer tamanho) e pelos PNGs com alpha em `brand/symbol-refinado/`.

- `logo/` — os dois lockups (horizontal e vertical) desenhados sobre o símbolo antigo.
  **Substituídos** por `brand/logo/`, agora gerados de `design/solis-symbol.svg` mais o
  wordmark composto como texto em DM Sans 500 (ver `design/gerar-lockups.py`). Ficam aqui
  porque eram a única leitura existente do arranjo horizontal — as proporções do lado a
  lado (cap 24,74% e folga 23,26% da largura do símbolo) foram medidas neles.

Continua fora desta pasta, ainda em uso, mas também desenhado sobre o símbolo antigo:

- `brand/states/` — listening, rings-soft, rings-strong. São renders com glow, não
  desenho de traço: não dá pra derivar do vetor. Vale notar que o `SOLIS_SIGNATURE.md` já
  prevê o glow como **camada CSS separada atrás da arte** — se essa arquitetura for
  mantida, estes 3 arquivos deixam de ser necessários em vez de precisarem ser regerados.
