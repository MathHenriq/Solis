# fundos/

As três cenas de horizonte, **uma por tema**. É aqui que os arquivos entram:

| arquivo | tema | o que a cena mostra |
|---|---|---|
| `bg-espacial.webp` | Espacial | amanhecer dourado |
| `bg-claro.webp` | Claro | manhã pálida |
| `bg-dark.webp` | Dark | noite com fresta de luz |

Os nomes são fixos — `src/styles/tokens.css` aponta pra eles, e esse arquivo é **gerado**
de `docs/solis-tokens.json` → `scenes`. Trocar nome de arquivo significa mudar o JSON e
rodar `npm run tokens`, nunca editar o CSS à mão.

Enquanto os arquivos não estiverem aqui, a camada de horizonte simplesmente não pinta e
cada tema cai no seu canvas sólido. Isso é o mesmo caminho de "Exibir imagem de fundo"
desligado — um estado que o produto já tem, não uma tela quebrada.

## Ancoragem vertical

Cada tema tem seu próprio `background-position-y`, porque as três fotos têm o horizonte em
alturas diferentes dentro do arquivo (~3,4pp entre Claro e Dark). É uma exceção deliberada
ao princípio de fonte única do projeto — o racional completo e o que fazer se um quarto
tema aparecer estão em `docs/solis-tokens.json` → `scenes._excecao`.

Os valores atuais são ponto de partida, calculados a partir das alturas medidas. **Faltou
a calibração visual**, que depende dos arquivos.
