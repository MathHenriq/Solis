# VISÃO — o que o Solis é, e pra onde ele vai

Nas palavras do Matheus (11/11/2026), organizadas. Este documento é o norte: o `PLANO.md` é o
mapa do que falta, o `ESCOPO.md` o registro do que foi feito e medido. Quando uma decisão de
detalhe não estiver clara, a pergunta é "isso aproxima o Solis do que está aqui?".

## O que ele é

**O Jarvis do Matheus — e, um dia, um produto.** Um sistema que centraliza a vida dele: dia a dia,
trabalho, desenvolvimento, agentes, automação. Não um app de chat: o lugar onde todas as IAs dele
trabalham juntas, com o contexto dele.

- **Centraliza todas as IAs.** Claude, GPT, Gemini, o modelo local — quem tem várias conecta as
  chaves e as contas, e o Solis é quem junta o conhecimento entre elas. Trocar de IA não perde o
  contexto: ele mora na máquina, no Solis, não no fornecedor. Hoje, quem troca do Claude pro GPT
  começa do zero; no Solis, não.
- **Local primeiro, nuvem quando ajuda.** O modelo local é escolhido por nós como o melhor
  possível e baixado sozinho na instalação. O contexto fica na máquina; mais pra frente, ao fim de
  um assunto, ele sincroniza (os vetores) com a nuvem e passa a buscar lá também — o Claude
  Desktop busca o que está na nuvem dele, o Solis tem que buscar o que é do Matheus, onde estiver.
- **Um modelo próprio.** Depois dos testes, escolher um modelo que funcione bem e fazer fine-tuning
  nele: um modelo completo, do Solis.

## O que ele faz (os pilares — nenhum é "menos importante": o conjunto é o produto)

1. **Memória de verdade.** Lembra de tudo, busca por significado (RAG), sabe de onde veio cada
   coisa. Hoje existe, mas o Matheus não sente que funciona "perfeito" — tem que ficar visível e
   confiável.
2. **Conversa excelente.** O chat é o centro e ainda não está bom o bastante.
3. **Age, não só responde.** Ler e mexer no computador, pesquisar na web em paralelo enquanto o
   Matheus pesquisa de outro jeito, marcar na agenda, lembrar, avisar.
4. **Agentes, fáceis pra qualquer um.** A "fábrica do Solis": uma aba onde os agentes aparecem,
   num modelo 3D, indo e voltando dos lugares onde trabalham. Pra quem usa Claude é fácil; o
   Solis tem que ser fácil pra quem só quer uma ferramenta que funcione.
5. **Automação dentro.** Um formato como o n8n, mas dentro do Solis.
6. **Presença — o Jarvis.** Chamado pela voz, aparece na tela (a ilha), responde falando quando a
   voz está ligada e por aviso quando não. A voz importa: é o sonho do Jarvis.
7. **Em todo lugar.** Pelo WhatsApp, como o Meu Assessor: "Solis, vê no meu PC", "o que eu tenho
   amanhã?", "busca tal coisa". E em reuniões: legendar e anotar ao vivo, inclusive em outra
   língua ("não estou entendendo o que a minha chefe está falando, anota pra mim").

## As restrições reais

- **Uma placa de 8 GB não faz tudo ao mesmo tempo.** Modelo de conversa (5,2 GB) + Whisper (~1 GB)
  + voz na GPU (3,6 GB medidos) não cabem. Daí o **modo sem placa** e a hipótese do **segundo PC
  ligado como servidor** do Solis (ele guarda tudo e roda o pesado; este PC e o celular são
  clientes).
- **O que é privado não sai da máquina** — vale pra cada pilar.

## A barra de qualidade

"Não dá pra fazer migué." O Matheus quer, um dia, fazer como o Felipe Titto com o Meu Assessor:
vender. E um dono de empresa sem um produto que funcione não tem nada. Então:

- **Cada peça é testada no uso real antes de ser dada como pronta** — como a voz foi testada com
  a voz dele, não só com testes automáticos. Teste automático passando não é "funciona".
- **O que está mais ou menos feito volta pra fila**, com o defeito escrito — não fica esquecido
  embaixo da próxima frente.
- **O básico tem que ser impecável antes do vistoso.** Errar a hora, não ouvir a palavra, não
  avisar o lembrete: cada um desses frustra mais do que qualquer função nova encanta.
