# PARIDADE — o Solis no lugar do Claude Desktop e do Claude Code

O primeiro marco (`VISAO.md`), nas palavras do Matheus (11/11/2026): "quando tiver tudo que tem no
Claude aqui [...] eu não precisar mais usar o Claude para nada, eu usar somente o Solis, aí sim
nós podemos falar que nosso checkpoint foi alcançado". Tudo é tudo: o Claude Desktop (a conversa,
o Cowork, os conectores) e o Claude Code (trabalhar num projeto). Pode ser numa versão menor, mas
cada coisa tem que funcionar igual.

**O que "não usar o Claude" quer dizer, com precisão:** não abrir mais os apps da Anthropic. O
cérebro por baixo continua sendo o Claude, pela assinatura do Matheus, pelo Claude Agent SDK — o
mesmo motor do Claude Code, como biblioteca. O SDK só fala com modelos Claude; o que ele traz de
pronto (ler, escrever, terminal, web, subagentes, sessões, skills) vem desse motor.

**Se a cota do Claude acabar:** o Solis segue pelo próximo cérebro da ordem (modelo local, Groq,
Gemini...), mas sem as ferramentas do Claude Code — o local só tem as de ler arquivo (`pc.py`).
Os caminhos pra não ficar sem ferramenta (a decidir com o Matheus, medindo):
1. **O mesmo SDK por chave de API da Anthropic** quando a assinatura acabar: igual em tudo, pago
   por uso. É também o caminho obrigatório do produto vendido (política da Anthropic).
2. **Um laço de ferramentas do próprio Solis** pros outros modelos (o do local já existe, em
   `ollama.py`): as mesmas ferramentas, implementadas no Solis, servindo qualquer modelo. Mais
   trabalho, e a qualidade cai com modelos mais fracos — mas é o que torna o Solis independente.

Legenda: ✅ feito e conferido · 🟡 em parte · ⬜ não existe. P1 é o que mais faz o Matheus voltar
pro Claude hoje; P3 é o que dá pra viver sem por um tempo.

## A conversa (Claude Desktop / claude.ai)

| | Coisa | No Solis hoje | P |
|---|---|---|---|
| ✅ | Resposta saindo ao vivo, com as etapas | Thread, etapas | |
| 🟡 | Markdown: títulos, listas, negrito, código | negrito e código em linha; **bloco de código (```) aparece cru, sem indentação** (visto no teste do projeto, 12/11/2026); falta tabela, realce de sintaxe e copiar o código | P1 |
| ✅ | Parar a resposta no meio | 11/11/2026: o enviar vira o parar; interrompe até o Claude no meio de uma ferramenta; o que chegou fica guardado. Provado pelo app | P1 |
| ✅ | Copiar uma resposta | 11/11/2026, ao lado da hora; falta copiar só um bloco de código | P1 |
| ✅ | Editar a mensagem e mandar de novo; refazer a resposta | 11/11/2026; diferente do Claude, a versão antiga não fica guardada como ramo (sai) | P1 |
| ✅ | Anexar arquivo e imagem na conversa (arrastar, colar) | 11/11/2026: pelo +, arrastando ou colando; o arquivo vai pra pasta de trabalho e o Claude lê (texto, PDF, imagem). Provado pelo app: leu a placa QXT-4F92 e a cor verde-limão de uma imagem e o pedido 55120 de um .txt. Falta a miniatura da imagem na ficha | P1 |
| ✅ | Escolher o modelo (Fable, Opus, Sonnet, Haiku) e o quanto ele pensa | 11/11/2026, no campo de digitar da conversa; os quatro conferidos na conta do Matheus (Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5). Falta na tela vazia da Conversa (aprovada pela referência: precisa do aval) | P1 |
| ✅ | Lista de conversas e busca nelas | sidebar, busca | |
| ⬜ | Renomear e apagar conversa | — | P2 |
| ✅ | Memória | a do Solis (melhor: local, editável, com privado) | |
| ✅ | Pesquisar e ler na web | pelo Claude (agente) | |
| ⬜ | Pesquisa longa (research): muitas fontes, relatório com citações | o Claude pode por subagentes; falta o modo e as fontes na tela | P2 |
| ⬜ | Projetos: instruções e arquivos fixos por assunto | — | P2 |
| ⬜ | Artefatos: página, documento, gráfico, app que abre do lado | — | P2 |
| ⬜ | Criar arquivo de verdade: .docx, .xlsx, .pptx, .pdf | — (o Claude pode escrever arquivo, falta o jeito de cada formato) | P2 |
| ⬜ | Conectores: Gmail, Google Agenda, Drive, GitHub, Canva, Figma, Vercel, Supabase... | — | P1 |
| ⬜ | Estilos de resposta (conciso, explicativo...) | — | P3 |
| 🟡 | Voz | a do Solis (ativação, ilha, fala) | |

## Agir no computador (Cowork, Claude in Chrome, computer use)

| | Coisa | No Solis hoje | P |
|---|---|---|---|
| ✅ | Ler arquivos nas pastas autorizadas | local (`pc.py`) e Claude | |
| 🟡 | Escrever e editar arquivos | Claude, com o cartão; falta o diff antes de aprovar | P1 |
| 🟡 | Terminal | Claude, com o cartão; falta a saída ao vivo na tela | P1 |
| ⬜ | "Aprovar sempre" esta ferramenta / esta pasta | cada uso pede | P1 |
| ⬜ | Lista de tarefas do próprio trabalho (o plano que ele mostra fazendo) | o Claude usa (TodoWrite), a tela não mostra | P2 |
| ⬜ | Navegador: abrir, ler, clicar, preencher | — | P2 |
| ⬜ | Controle da tela (ver, clicar, digitar em qualquer app) | — | P3 |
| ⬜ | Tarefas agendadas e recorrentes | — (os avisos de lembrete existem) | P2 |
| ⬜ | Skills: roteiros que o Matheus escreve uma vez | — | P2 |

## Trabalhar num projeto (Claude Code)

| | Coisa | No Solis hoje | P |
|---|---|---|---|
| ✅ | A sessão continuar entre mensagens (o que ele leu e fez fica com ele) | 11/11/2026: provado pelo app — leu um arquivo, respondeu só "li", e na mensagem seguinte disse o conteúdo sem reler; primeira palavra em 4,0 s contra 12,1 s da sessão nova | P1 |
| ✅ | Abrir uma pasta de projeto e trabalhar nela (o repositório como lugar de trabalho) | 12/11/2026: a barra acima do campo de digitar (colar o caminho, recentes); ler lá dentro é livre. Provado pelo app com um projeto de teste | P1 |
| ✅ | Ler o CLAUDE.md do projeto | 12/11/2026: com projeto, o SDK lê o CLAUDE.md e a configuração dele; a regra do projeto de teste foi seguida em toda resposta | P1 |
| ✅ | Modos: planejar antes, aceitar edições, pedir tudo | 12/11/2026: na barra. Aceitar: editou o projeto sem cartão (comando ainda pede). Planejar: o plano inteiro no cartão; aprovado, executou pedindo a escrita. Falta: depois do plano aprovado o modo da conversa continua "planeja antes" (no Claude Code ele volta) | P1 |
| ⬜ | Ver o diff do que mudou; voltar atrás (checkpoints) | — | P1 |
| ⬜ | Git: status, commit, push, PR | pelo terminal, com aprovação; sem tela | P2 |
| ⬜ | Comandos em segundo plano (servidor, teste longo) e acompanhar | — | P2 |
| 🟡 | Subagentes | o Claude pode; a tela não mostra | P2 |
| ⬜ | Servidores MCP configuráveis | só o do Solis | P2 |
| ⬜ | Hooks | — | P3 |
| ⬜ | Custo e uso da cota na tela | só no log | P3 |

## A ordem

Uma frente por vez, cada uma testada no uso real antes da próxima (`VISAO.md`, a barra de
qualidade):

1. ✅ **A sessão continuar** — sem ela, o Claude esquece o que leu e fez a cada mensagem; é a base
   de todo o resto.
2. ✅ **A conversa básica do Desktop:** parar, copiar, editar e refazer, anexar, escolher o modelo.
3. **Trabalhar num projeto:** abrir pasta, CLAUDE.md, modos, diff, "aprovar sempre".
4. **Conectores** (os que o Matheus usa no claude.ai).
5. **Criar documentos, artefatos, projetos, pesquisa longa.**
6. Navegador, agendadas, skills, o resto.
