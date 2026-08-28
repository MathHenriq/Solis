# fontes/

Playfair Display, self-hosted — **não** via CDN. O `docs/HANDOFF.md` trava "fonte ativa sem
dependência de rede", e um `<link>` para fonts.googleapis.com seria exatamente essa
dependência: o Solis é local-first e desktop, então o título não pode depender de a máquina
estar online para renderizar.

Só o peso 400 e os subsets `latin` e `latin-ext` estão aqui — é o que a saudação usa, e o
português cabe inteiro neles. O peso 500 servido pelo Google é byte a byte idêntico ao 400
(vem do mesmo variable font), então carregar os dois seria peso morto.

Licença: SIL Open Font License 1.1 — https://openfontlicense.org

---

**DM Sans**, peso 500 — a sans do wordmark SOLIS. Escolhida na folha
`design/wordmark-candidatas.png`, gerada por `design/comparar-wordmark.py`, que compara
candidatas de licença aberta contra o wordmark de
`referencias/brand/symbol-refinado/mono-wordmark.png`. **Não é a fonte original da folha** —
é a mais próxima disponível em licença aberta, que é o que o `HANDOFF.md` permite.

Só o subset `latin`. O wordmark tem quatro glifos distintos (S, O, L, I), todos em latim
básico: `latin-ext` aqui seria peso morto. Também só o peso 500 — nenhum outro é usado.

Licença: SIL Open Font License 1.1 — https://openfontlicense.org
