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

- `states/` — listening, rings-soft, rings-strong, desenhados sobre o símbolo antigo.
  **Não precisam ser regerados:** o glow deixou de ser asset e virou código
  (`src/components/SolisEstado.tsx`), com filtro SVG sobre o próprio vetor. Ficam aqui
  porque foi neles que o perfil do halo foi medido — o corte perpendicular ao traço que
  definiu os dois desfoques do filtro saiu de `solis-state-listening.png`.
