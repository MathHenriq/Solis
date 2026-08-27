# fundos/

As três cenas de horizonte, **uma por tema**.

| arquivo | tema | cena |
|---|---|---|
| `bg-espacial.webp` | Espacial | amanhecer dourado |
| `bg-claro.webp` | Claro | manhã pálida |
| `bg-dark.webp` | Dark | noite com fresta de luz |

2880×1800, WebP q88, ~0,1–0,2 MB cada. Os nomes são fixos: `src/styles/tokens.css` é
**gerado** de `docs/solis-tokens.json` → `scenes`, então trocar nome de arquivo significa
mudar o JSON e rodar `npm run tokens` — nunca editar o CSS à mão.

## Por que os arquivos foram recortados

As fotos originais tinham o horizonte em alturas diferentes dentro do arquivo (74,2% /
73,2% / 71,9%). A intenção era compensar isso com um `background-position-y` por tema, mas
**essa compensação não funciona nesta geometria**: com `background-size: cover` e imagem de
aspecto 1,60 numa janela de 1,55, o `cover` escala pela altura — a imagem cobre os 930px
exatos e a folga sobra só na horizontal. Sem folga vertical, `position-y` não move nada, e
os três horizontes ficariam travados em 690, 681 e 669px.

Então os três foram **reenquadrados** para o horizonte cair em 74,0% em todos, com o mesmo
aspecto. Cada um perdeu 4% da altura e 4% da largura; nada foi redesenhado nem esticado. Com
isso existe **um único `positionY`** em vez de três, e a exceção ao princípio de fonte única
que a decisão original assumiria deixa de ser necessária.

Se as fotos forem trocadas, o horizonte da nova precisa cair em 74,0% da altura — ou os três
precisam ser reenquadrados juntos para uma nova altura comum.
