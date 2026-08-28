# _fontes-candidatas/

TTFs usados pelas ferramentas de marca — `comparar-wordmark.py` e `gerar-lockups.py`.
São de **build**, não de runtime: o que o app serve é o `.woff2` em `public/fontes/`.

Só a DM Sans 500 fica versionada, porque é a fonte fechada e sem ela os lockups não são
reproduzíveis. As outras candidatas ficam de fora — são 51 arquivos e só serviram pra uma
comparação. Para refazer a folha:

    curl -A "Mozilla/4.0" "https://fonts.googleapis.com/css?family=Jost:300,400,500"

A API v1 do Google Fonts entrega TTF quando o User-Agent é antigo; a v2 só entrega woff2,
que o PIL não lê.

Licença: SIL Open Font License 1.1 — https://openfontlicense.org
