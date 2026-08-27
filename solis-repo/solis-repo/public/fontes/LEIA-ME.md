# fontes/

Playfair Display, self-hosted — **não** via CDN. O `docs/HANDOFF.md` trava "fonte ativa sem
dependência de rede", e um `<link>` para fonts.googleapis.com seria exatamente essa
dependência: o Solis é local-first e desktop, então o título não pode depender de a máquina
estar online para renderizar.

Só o peso 400 e os subsets `latin` e `latin-ext` estão aqui — é o que a saudação usa, e o
português cabe inteiro neles. O peso 500 servido pelo Google é byte a byte idêntico ao 400
(vem do mesmo variable font), então carregar os dois seria peso morto.

Licença: SIL Open Font License 1.1 — https://openfontlicense.org
