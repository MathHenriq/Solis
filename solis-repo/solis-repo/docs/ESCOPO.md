# Escopo do Solis — onde estamos e para onde vamos

Documento vivo. Atualizar ao fechar cada fase. Última revisão: 1º de novembro de 2026.

## A visão

Um assistente pessoal que conhece o Matheus por inteiro: tudo o que ele manda é guardado,
tudo o que ele diz é entendido no contexto da vida dele, e o histórico é completo. A
referência é o Jarvis: prontidão, voz, acesso total ao computador.

O Solis tem **dois papéis**, e separar os dois resolve quase tudo:

1. **Ser a memória.** Tudo sobre o Matheus mora no Solis, na máquina dele. É a fonte da
   verdade — inclusive pros outros assistentes.
2. **Executar.** Responder, pesquisar, programar, controlar o PC. A inteligência vem de onde
   for melhor no momento: Claude Code e Codex (pela assinatura do Matheus, nunca API paga),
   APIs gratuitas, ou modelos locais quando a cota acabar ou o assunto for privado.

**O que isso entrega e o que não entrega.** A vantagem do Solis é o **contexto**: ele sabe
da Syngenta, dos estudos, das preferências, sem que nada precise ser repetido. Um modelo
local de 3B a 14B **não** raciocina como um modelo de nuvem de ponta — por isso o trabalho
pesado (código, sistemas grandes como a NF-e da loja) vai pros modelos de nuvem, e o Solis
entrega a eles o contexto certo.

## Decisões do Matheus

| Questão | Decisão |
|---|---|
| Prioridade | Um assistente que guarda e lembra de tudo. Sem ordem fixa além disso |
| Servidor | O PC de casa liga quando for usar; o notebook é a reserva, acordado por Wake-on-LAN |
| Privacidade | Modo privado: senhas, saúde e o que for marcado nunca saem da máquina. O resto pode ir pros modelos de nuvem |
| Tecnologias | Nenhum apego. Escolher medindo |
| Hardware | Notebook com 8 GB de VRAM (o principal). PC de casa com GTX 1650 de 4 GB |

## Arquitetura hoje

```
┌─────────────── Notebook do Matheus ───────────────┐
│                                                   │
│  Front (React, Vite)  ──HTTP──►  Servidor (FastAPI, 127.0.0.1:8765)
│  as 8 telas                       │        │
│                                   │        └──► SQLite (%APPDATA%\Solis\solis.db)
│                                   │             conversas · mensagens · memorias
│                                   └──► Ollama (127.0.0.1:11434)
│                                        os modelos de linguagem
└───────────────────────────────────────────────────┘
```

Tudo escuta só em `127.0.0.1`: nada sai da máquina e nada entra pela rede.

## O que já foi feito

### Front — fechado

- As 8 telas, construídas uma por vez contra as referências de `referencias/`.
- 3 temas (espacial, claro, dark) e 2 modos de navegação (sidebar e barra de ícones).
- Verificação automática: `npm run varrer` testa 96 combinações (telas × temas × modos ×
  tamanhos de janela) e `npm run checar` trava as regras que já foram quebradas antes.
- Preview na Vercel (só a casca visual; lá não há servidor).

### Servidor — primeira camada no ar

| O quê | Como funciona |
|---|---|
| Modelos locais | Lê do Ollama o que está instalado; clicar numa linha escolhe o modelo da Conversa |
| Conversa | A resposta chega em streaming; markdown vira parágrafo, lista e negrito |
| Histórico | Toda mensagem vai pro SQLite; o app reabre na última conversa; `/nova` começa outra |
| Memória | Automática (o modelo extrai fatos depois de cada resposta) e garantida quando pedida ("grave", "anote"...) |
| Busca por significado | Memórias e mensagens viram vetores; cada pedido leva as memórias e os trechos de conversas antigas mais parecidos com a mensagem |
| Modo privado | Memórias sensíveis são marcadas — pelo modelo, ou à força quando a mensagem diz "privado" |
| Memória que muda | Fato novo que desmente um antigo o substitui; o antigo fica guardado, fora da tela |
| Conversa longa | O começo vira resumo; as 20 últimas mensagens vão inteiras |
| Cérebros | Claude Code e Codex respondem pelo Solis com a assinatura; o modelo local é a reserva e o guardião do que é privado |
| MCP | O Claude Code e o Codex consultam a memória do Solis mesmo fora dele |
| Importação | O histórico do ChatGPT e do Claude entra na busca e na memória |
| Prompt honesto | O prompt de sistema diz o que o Solis **não** consegue fazer, pra ele não inventar |
| Erros | Cada falha diz quem falhou: servidor, Ollama ou falta de modelo |

78 testes automáticos no servidor, rodando sem precisar do Ollama.

### O que ainda é provisório

- Ferramentas mostra dados de exemplo (Tarefas e Agenda já têm dados reais, 09/11/2026).
- O piso de similaridade da busca foi escolhido sem dados reais; precisa calibrar no notebook.
- O servidor precisa ser ligado à mão (`npm run backend`).

## Próximas tarefas — do primeiro teste real (1º de novembro de 2026)

No notebook, com o Ollama, o Claude Code e o Codex de verdade, tudo funcionou: as respostas
pelo Claude e pelo Codex, a memória guardada e lembrada numa conversa nova, e o MCP conectado
nos dois CLIs. Três problemas, em ordem de prioridade:

### 1. Claude e Codex levaram quase um minuto pra responder — não se repetiu

No primeiro teste, logo depois de instalar os CLIs, duas mensagens levaram perto de um minuto:
"grave: trabalho na Syngenta..." (pelo roteador, foi pro Claude) e "/codex qual a capital da
França?". O modelo local era o padrão (llama3.2:3b).

**Medido no notebook depois, o minuto não voltou.** Os 69 s que estavam aqui foram medidos na
nuvem, não no notebook. Números reais (1º/11/2026):

| Medição | Tempo |
|---|---|
| CLIs chamados direto, sem o Solis | 2 a 5 s |
| Servidor do Solis inteiro, pedido → resposta | 2 a 11 s (o pico foi o qwen3:8b subindo pra GPU pro aprendizado enquanto o Codex respondia) |
| Claude pelo Solis, pedido → primeira palavra | 4,5 a 5,3 s (o CLI sobe em 0,6 a 1,2 s; o resto é o modelo) |
| Claude, primeira palavra → fim de uma resposta de uma palavra | era 2,5 a 3,6 s (o CLI demora pra fechar); agora 0,08 a 0,11 s — a resposta acaba no `message_stop` |
| Codex pelo Solis, pedido → resposta (chega de uma vez) | 3,9 a 7,1 s |
| Modelo local carregado (llama3.2:3b), pedido → primeira palavra | 0,1 s |
| Busca na memória com o nomic-embed-text frio / quente | 2,0 s / 0,02 a 0,16 s |
| Com o Ollama fora: busca / aprendizado / indexação | 2 s / 4 s / 2 s — o Windows leva 2 s pra recusar a conexão, e o front espera mais 2 s no `/modelos` antes de mandar |
| Maior silêncio entre linhas do CLI (resposta de 500 palavras e uma que pensa) | Claude 3,9 s; Codex 8,5 s (gera calado e entrega tudo de uma vez) |

O `--bare` do Claude Code não serve: na versão 2.1.316 ele só aceita `ANTHROPIC_API_KEY` e ignora
o login da assinatura. Desligar os MCP no `codex exec` economiza ~1 s.

Suspeitos do minuto: o MCP `node_repl` do Codex, que depende do app desktop do Codex e aceita até
120 s pra subir (o Codex sobe os MCP antes de escrever a primeira linha: 8,7 s frio, 0,45 s
quente); atualização do CLI no primeiro uso; e a espera de 90 s pela primeira palavra, que fazia um
cérebro travado custar um minuto e meio antes de cair pro próximo. **Trocada** por dois limites
medidos (`solis/cerebros.py`): a primeira linha em 20 s (é ali que um CLI trava) e o silêncio entre
linhas — 20 s no Claude, 60 s no Codex. Um CLI travado agora custa 20 s. **Para flagrar a próxima demora**, cada resposta
agora registra as etapas com os tempos no `solis.log` (ver `backend/README.md` → Etapas).

### 2. Enquanto o modelo pensa, a tela não diz nada — resolvido

O servidor conta cada etapa com o tempo dela (NDJSON: `{"etapa": ...}`, `{"texto": ...}`,
`{"erro": ...}`), e o que acontece depois da resposta chega pelo mesmo stream, que só fecha
depois do aprendizado e do resumo. A tela, construída contra `telas/20-conversa-etapas.png`
(medidas em `layout.thread.etapas`):

- enquanto não há texto: o símbolo com glow no estado real (pensando, depois respondendo) e a
  lista de etapas — feitas com check, a atual com ponto e o tempo correndo ("O Claude está
  pensando… 4 s", ou "Abrindo o Codex…" enquanto o CLI sobe), as futuras esmaecidas;
- com a resposta pronta: a linha recolhida "4 etapas · 3,1 s" acima do cabeçalho, que abre a
  lista, e o chip "Memória guardada: ..." embaixo do texto. As etapas ficam no banco: a linha
  aparece também depois de reabrir o app.

Provisório, sem referência: o cérebro que falhou (anel e texto secundário, sem check) e o chip
"Conversa resumida". O glow do avatar foi ajustado contra a referência (`states.glow.avatar`):
o da folha de 190px sumia em 34px.

### 3. Lista de conversas e botão de nova conversa — feito, no padrão do Claude

A primeira versão seguiu `telas/19-conversa-lista.png`: um painel numa segunda coluna, com
divisória própria e botão e busca em caixas com borda. O Matheus achou pesado (as duas
divisórias lado a lado, o botão e a busca "forçados") e pediu o próprio Claude como base
(08/11/2026). Agora, como no Claude:
- **Modo sidebar:** "Nova conversa" (o + num círculo de accent), a busca e os "Recentes" vivem
  dentro da sidebar, abaixo da navegação, em linhas sem caixa e sem borda; a aberta só ganha
  um fundo. Aparecem em qualquer tela, inclusive na saudação.
- **Modo barra de ícones:** dois botões no canto esquerdo do topo, espelhando os da direita —
  o painel (abre a mesma lista numa gaveta) e o "+" (Nova conversa).

Busca no título e no texto; dá pra voltar a uma conversa antiga e continuar nela; o app reabre
na da mensagem mais recente. **PROVISÓRIO:** não há imagem do Claude em `referencias/` (o app do
Claude não pode ser capturado daqui, e o claude.ai pede login); as medidas seguem a grade da
sidebar validada (`layout.recentes`) e precisam do aval do Matheus.

Em aberto:
- **Títulos**: o modelo local dá um título curto depois da primeira resposta, como etapa de
  fundo, sem o modo de raciocínio. Conferido no notebook (08/11/2026) nas 9 conversas da cópia
  do banco: o qwen3:8b acerta quase todos ("Plano da semana", "Emissão de NF-e") em 0,2 a 0,4 s;
  o llama3.2:3b é igualmente rápido mas erra mais ("O que está de mais urgente"). Com um exemplo
  de título na instrução, o llama copiava o exemplo — a instrução ficou sem exemplos. Sem o
  Ollama vale a primeira fala, e a próxima mensagem tenta de novo. As conversas de antes disso
  ganham título na próxima mensagem que receberem.

## Para onde vamos

A regra: **primeiro o que torna o Solis útil, depois o que o torna impressionante.** Voz
sobre um assistente que esquece as coisas é só um assistente que esquece as coisas,
falando. As fases não têm ordem rígida (decisão do Matheus), mas as primeiras são a base
das outras.

### Memória completa — feito (08/11/2026)

- [x] Conversas guardadas; memória automática e pedida.
- [x] Busca por significado em memórias e conversas antigas (RAG).
- [x] Conversa longa: o começo vira resumo, o fim vai inteiro, sem buraco entre os dois.
- [x] Marca de privada.
- [x] Contradição: "saí da Syngenta" substitui a memória antiga (que fica guardada, marcada).
- [x] Lista de conversas antigas e "Nova conversa" (com a thread aberta).
- [x] Esquecer e corrigir memória pela tela — desenho próprio, sem referência (o Matheus liberou o
  front): ações no hover, edição e confirmação no próprio item, Desfazer, cadeado na privada.
- [x] Busca textual (FTS5) na tela de Memória: por palavra, por prefixo, sem diferença de acento.
- [x] Criptografar o que é privado (DPAPI do Windows): memória, mensagem, e o título, o resumo e
  as etapas de conversa com segredo. O que protege e o que não, em `backend/README.md` → Memória.

### Importar o passado — pronto, falta conferir com os arquivos reais

- [x] Importador do ChatGPT e do Claude (`python -m solis.importar`), sem duplicar ao repetir.
- [x] Conversas importadas entram na busca, com o autor certo ("ChatGPT disse").
- [x] Memórias tiradas do histórico, retomáveis, com data, sem substituir o presente.
- [ ] Conferir o leitor do Claude com uma exportação real (os campos não foram confirmados).

### Cérebros externos — pronto, falta conferir as APIs com chaves de verdade

- [x] Claude Code e Codex pelo CLI oficial, com a assinatura (`/claude`, `/codex`, `/local`).
- [x] Roteador por regras, com a preferência pelos mais fortes e queda pro próximo.
- [x] Nada privado vai pra nuvem; extração, vetores e resumo sempre locais.
- [x] Servidor MCP de memória, testado com o Claude Code de verdade.
- [x] Conferir o Codex rodando de verdade: no notebook, em 1º/11/2026, respondeu pelo Solis
  (3,9 a 7,1 s) e conectou o MCP de memória (ver "Próximas tarefas", problema 1).
- [x] APIs gratuitas como mais cérebros (08/11/2026): Groq, Gemini, Mistral e OpenRouter, por
  chave colada em Configurações → Cérebros. Decisão do Matheus: o Solis tem todos os modelos
  grátis que der, que é também o que o Laboratório de modelos vai comparar.
- [ ] Conferir cada API com uma chave de verdade (testadas só com o serviço simulado). Um relato
  antigo diz que o `/models` do Gemini pelo formato OpenAI dava `401` com chave boa; por isso,
  antes de recusar, o Solis pergunta pela API nativa do Gemini.
- [x] Escolher a ordem dos cérebros pela tela: Configurações → Cérebros (08/11/2026), com
  liga/desliga, o motivo e a hora de quem está pausado, e "Tentar agora". Desenho próprio,
  aprovado pelo Matheus pelos prints (`design/cerebros-validacao.png`).

### O Claude com ferramentas (Agent SDK) — feito, falta o uso real do Matheus (11/11/2026)

O primeiro marco da `VISAO.md`: o Matheus parar de usar o Claude Desktop.

- [x] O Claude pelo Claude Agent SDK (`backend/solis/agente.py`): as ferramentas do Claude Code
  (ler, escrever, editar, terminal, web, subagentes) e as do Solis por MCP (hora, lembrete,
  compromisso, agenda, tarefas, memória). Provado contra o Claude de verdade: leu dentro da
  pasta autorizada sem pedir, pediu pra ler o `win.ini` (recusado), pediu pra escrever (aprovado,
  criou), anotou o lembrete com dia e hora.
- [x] Cartão de aprovação na conversa (desenho próprio, PROVISÓRIO): conferido pelo app com dois
  pedidos reais, aprovado e recusado, nos 3 temas e 2 navs (`design/aprovacao-validacao.png`).
  O cartão apareceu 4 a 10 s depois do pedido; aprovado, o arquivo foi gravado; recusado, o
  Claude não gravou e disse isso.
- [x] Cota acabada pausa o Claude como antes; `SOLIS_CLAUDE_AGENTE=0` volta ao CLI só de conversa.
- [ ] Aval do Matheus no cartão (prints) e o uso dele no dia a dia, com a lista do que o Claude
  Desktop faz e o Solis ainda não.
- [ ] Decisão do Matheus: o Claude lê sem pedir nas pastas autorizadas (o conteúdo vai pra
  Anthropic) ou cada leitura pede, como a escrita? Hoje lê sem pedir; o modelo local continua
  sendo o padrão das perguntas sobre arquivos (`pc.do_pc`).
- [x] A sessão continua entre mensagens (11/11/2026): a conversa guarda a sessão do Claude, e a
  próxima mensagem vai só com a memória de agora, o que outro modelo respondeu no meio e a
  mensagem nova. Sessão que não continua vira uma nova com o histórico inteiro. Provado pelo app
  (ver `docs/PARIDADE.md`).
- [x] Parar, copiar, refazer e editar na conversa (11/11/2026), conferidos pelo app com o Claude
  num servidor de teste: parou em 70 palavras e guardou o pedaço; refazer e editar trocaram a
  resposta e o que vinha depois. Desenho próprio, PROVISÓRIO (`design/conversa-acoes-validacao.png`).
- [x] Anexar arquivo e imagem na conversa (11/11/2026): pelo +, arrastando ou colando um print.
  O arquivo vai pra `trabalho/anexos/AAAA-MM-DD/`, a mensagem leva o caminho e, com anexo, o
  Claude vai primeiro (o local não enxerga imagem). Conferido pelo app num servidor de teste: o
  Claude leu a placa e a cor de uma imagem e o número do pedido de um .txt. PROVISÓRIO
  (`design/conversa-anexos-validacao.png`).
- [x] O modelo do Claude e o quanto ele pensa, no campo de digitar (11/11/2026): Padrão da conta,
  Fable, Opus, Sonnet, Haiku; esforço de Pouco a Máximo. Conferido pelo app: escolhido Haiku, ele
  respondeu "rodando no Claude Haiku 5.5". PROVISÓRIO (`design/conversa-modelo-validacao.png`).
- [ ] **Defeito achado (11/11/2026):** o aprendizado vira pedido em tarefa — "Escreva um texto de
  500 palavras sobre o Sol" e "crie o arquivo nota.txt" viraram tarefas abertas; e uma memória
  antiga ("sair com os meninos") foi aprendida de novo numa conversa que não falava disso.
- [ ] O diff no cartão antes de aprovar uma edição; "aprovar sempre" por ferramenta. O resto do
  caminho está em `docs/PARIDADE.md`.

### Tarefas e Agenda — feitas e aprovadas (09/11/2026)

- [x] Tarefas no banco, pela tela (nova, editar com data e hora, marcar, apagar com Desfazer) e
  tiradas da conversa: "me lembra de pagar a luz dia 15" vira tarefa com o prazo em data, e o chip
  "Tarefa anotada" aparece embaixo da resposta. A mesma pergunta de fundo que tira as memórias tira
  as tarefas. Medido no qwen3:8b em 20 mensagens: 20/20 tarefas com o prazo certo, 11/11 na
  privacidade, 20/20 nas memórias (detalhes em `backend/README.md` → Tarefas).
- [x] As tarefas abertas vão no pedido ao modelo: "o que eu tenho pra fazer essa semana?" responde
  com elas. Tarefa de saúde ou dinheiro é privada e nunca vai pra nuvem.
- [x] Desenho novo da tela aprovado pelo Matheus pelos prints (`design/tarefas-validacao.png`): Nova
  tarefa, editar e apagar no hover, os grupos Atrasadas e Sem data, e o chip na conversa.
- [x] Agenda com compromissos de verdade: pela tela (novo, editar com dia, hora, duração e lugar,
  apagar com Desfazer, navegar pelos dias) e tirados da conversa, separados das tarefas ("quinta às
  15h tenho consulta" é compromisso; "pagar a luz dia 15" é tarefa). Medido no qwen3:8b em 22
  mensagens: 18/18 compromissos, 18/18 tarefas, 22/22 memórias. Os dos próximos 7 dias vão no pedido
  ao modelo: "o que eu tenho amanhã?" responde com eles. No dia de hoje, o que está acontecendo (ou
  o próximo) vira o cartão em destaque da referência.
- [x] A tela foi remedida contra a referência 16 (`layout.agenda`): a versão estática tinha os
  botões com 79px de altura (a largura do interruptor, o mesmo erro do Adicionar fonte), o título de
  cada compromisso em 20px em vez do corpo de 16, a linha do tempo quebrada, sem as divisórias, e o
  cartão da vez sem envolver a hora.
- [x] Desenho novo da Agenda aprovado pelo Matheus pelos prints (`design/agenda-validacao.png`): Novo
  compromisso, editar e apagar no hover, a edição com duração e lugar, "dia todo", o dia livre e o
  chip "Na agenda".
- [x] Avisos na hora (09/11/2026): a notificação do Windows 10 minutos antes do compromisso, na hora
  da tarefa, e um resumo às 8h com as tarefas do dia sem hora e os compromissos de dia inteiro. Sai
  do servidor (o front roda no navegador), pelo PowerShell do sistema; o privado não mostra o
  título. Conferido no notebook: o aviso saiu 1 s depois de o servidor subir, e chega à Central de
  Notificações em 0,8 s; o Matheus viu o aviso na tela. Enquanto o Solis não for um app instalado, o aviso aparece em nome do
  "Windows PowerShell" (com "Solis" na linha de baixo): ter nome e ícone próprios pede o app de
  verdade (Tauri, .msi), que registra a identidade dele no Windows.
- Limite conhecido: compromisso que se repete ("toda terça às 19h") vira só a próxima vez.
- Limite conhecido: a tarefa (e a memória) sensível é detectada DEPOIS da resposta. Se a mensagem não
  diz "privado" e um cérebro de nuvem está na frente, ela já foi pra nuvem — "quinta tenho consulta
  com o dentista" foi respondida pelo Claude no teste. O que fica guardado depois é selado e não volta
  pra nuvem.

### Servidor em casa e acesso de fora

- O PC de casa roda o servidor, o banco, os embeddings e um modelo pequeno (cabe na 1650).
- O notebook entra com os modelos maiores quando estiver ligado.
- **Tailscale** liga os aparelhos do Matheus numa rede privada: o Solis é acessado do
  celular ou de outro PC sem nada exposto na internet.
- Wake-on-LAN: funciona bem por cabo, mal ou nada por Wi-Fi, e precisa de algo acordado na
  rede de casa pra mandar o sinal. Se tudo estiver desligado, nada acorda nada.
- Dividir um modelo só entre as duas placas pela rede existe, mas a rede vira gargalo: cada
  máquina com um papel compensa mais.

### Conhecimento: os seus arquivos — feito (08/11/2026), falta conferir com os seus arquivos

- [x] PDF, `.md` e `.txt` pela tela: cada arquivo vira trechos com a página, cada trecho vira
  vetor, e os mais ligados à mensagem entram na resposta com o nome do arquivo e a página.
- [x] Progresso real da indexação, aviso quando ela para, busca pelo nome e pelo texto.
- [x] Fonte privada: selada, fora do índice e fora da nuvem. Remover com Desfazer.
- [x] Página web (09/11/2026): só o conteúdo principal, pela `trafilatura`.
- [x] **Pergunta em português acha texto em inglês** (09/11/2026). Com o `nomic-embed-text`, a
  pergunta sobre a página do FastAPI dava 0,57 em português (nota de ruído) e 0,79 em inglês.
  Medidos 4 modelos com as mesmas perguntas: o `embeddinggemma` acertou 10/10 e foi o único com
  folga entre o relevante e o ruído (tabela em `backend/README.md` → Busca por significado).
  Trocar de modelo refaz todos os vetores sozinho. Conferido de ponta a ponta: com o qwen3:8b, a
  resposta segue a página do FastAPI; o llama3.2:3b ignora os trechos (limite do modelo).
- [ ] Calibrar o piso (0,37) com os arquivos e as conversas de verdade do Matheus.
- [x] PDF escaneado (09/11/2026): as páginas-imagem entram numa fila e o qwen3.5:9b lê em segundo
  plano; o OCR do Windows é a reserva. Medidos os leitores com texto conhecido (tabela em
  `backend/README.md` → Conhecimento): o do Windows desaba em digitalização ruim (0,30 a 0,80 das
  palavras), o modelo de visão acertou todas. O cartão mostra "Lendo as páginas escaneadas… X%" com a
  mesma barra da indexação, aprovado pelo Matheus pelos prints (`design/conhecimento-ocr-validacao.png`). Custo: 6 a 26 s de GPU por
  página — um livro escaneado de 200 páginas é meia hora de GPU, a mesma disputa de VRAM anotada em
  "Questões pra depois".

### Voz

0. **Fish Audio em teste (11/11/2026)** — pedido do Matheus depois do vídeo "Dei Voz pros Meus
   Agentes de IA" (Fish Audio). A API dela tem um modelo grátis (`s2.1-pro-free`, o S2.1 Pro) por
   "um período inicial", sem data certa, com uso justo; os pedidos podem ser usados pra melhorar o
   modelo deles. Pago: US$ 15 por milhão de bytes de texto (~12 h de fala). Ligada como a primeira
   voz da cadeia quando há chave (Configurações → Voz, PROVISÓRIO, `design/voz-fish-validacao.png`);
   o privado continua na local. A chave é conferida nas vozes da conta (a lista pública aceita até
   chave inventada — visto no teste).
   **Medido com a chave dele (11/11/2026)**, 4 frases iguais, até o áudio inteiro: Fish 3,1 a 3,4 s
   de média (vozes padrão, Rafael, Beatriz, Verity — genéricas de assistente; a biblioteca pública
   em português é quase toda clone de gente real ou personagem, e ficou de fora), Gemini 3,9 s, Ava
   7,3 s (e falhou uma), Kokoro local 2,7 s. Lendo a Fish aos pedaços (`latency: balanced`), o
   primeiro pedaço de áudio chega em **0,7–0,8 s** (`normal`: 2,8–3,1 s). Ou seja: a Fish só fica
   rápida de verdade se o Solis tocar o áudio enquanto ele chega — hoje espera o pedaço inteiro.
   **Tocando aos pedaços (11/11/2026, pedido do Matheus):** o servidor repassa a Fish enquanto ela
   gera (`GET /fala/fluxo/{id}`, primeiro byte em 0,66 s) e a tela põe cada pedaço no áudio pela
   Media Source (`src/somAosPedacos.ts`) — o `<audio>` lendo direto da URL juntava ~2–3 s antes de
   tocar e não ganhava nada (medido). Primeiro som, do clique, num navegador: **0,85–1,7 s** aos
   pedaços contra 2,1–2,7 s inteiro. Falha antes do primeiro pedaço cai pra cadeia (inteiro).
   **Escolher a voz (11/11/2026, pedido do Matheus: "mais vozes, uma que faça mais sentido com o
   Solis"):** Configurações → Voz → Escolher voz abre a biblioteca da Fish — busca pelo nome, as
   etiquetas dela (masculinas, femininas, calmas, de conversa, narração, graves), português ou
   todas, as três ordens dela, 20 por vez. "Ouvir" fala a mesma frase do Solis em toda voz. Abre
   já buscando "assistente": vazia, a ordem da Fish começa nos clones de famosos. Conferido com a
   biblioteca real; PROVISÓRIO (`design/voz-fish-vozes-validacao.png`).
   **Falta:** o Matheus ouvir no app (contínuo?) e escolher a voz.

1. **Apertar pra falar** primeiro. **Feito (09/11/2026):** um clique no microfone ouve, outro para,
   e o texto entra na caixa pra conferir antes de enviar (Esc desiste). Whisper local (`small`, pelo
   faster-whisper) na GPU, com a cuBLAS que o Ollama já traz, e na CPU se a GPU não der. Medido em 8
   frases de texto conhecido, limpas e com ruído: com o vocabulário que o Solis já conhece (nomes das
   memórias, dos arquivos, dos modelos), o erro por palavra cai de 8,2% pra 2,1% e o small empata
   com o large-v3-turbo ocupando 455 MB de placa em vez de 1,2 GB; 0,5 s por frase na GPU, ~4 s na
   CPU (tabela em `backend/solis/voz.py`). De ponta a ponta no app: transcrito e na caixa em 4,5 s na
   primeira fala (2,5 s são o modelo subindo). Conferido pelo Matheus com a voz dele no headset
   (09/11/2026): saiu bem. Os estados do microfone (ouvindo, transcrevendo, erro) aprovados pelos
   prints (`design/voz-validacao.png`).
   **O Solis falando — feito e aprovado (09/11/2026):** um alto-falante na linha
   de cada resposta, e a resposta de uma mensagem ditada é falada sozinha. Cadeia de vozes: Gemini TTS
   (quando houver a chave do Gemini) → Ava, a voz do Copilot (sem chave, português e inglês) → Kokoro
   local (sem internet). Privado (conversa com algo privado, saúde, dinheiro) só na local.
   Como se chegou nisso: medidas 8 vozes locais pelo que o Whisper entende de volta (Kokoro 11,7%,
   Maria do Windows 13,7%, Piper 20 a 28% de perda) e ouvidas pelo Matheus — todas "horrendas" em
   português. O Chatterbox Multilingual pelo ONNX ficou melhor mas ainda esquisito, 5× mais lento que
   a fala na CPU e entrando em repetição; a versão original e o XTTS pedem o PyTorch, que o Controle
   Inteligente de Aplicativos do Windows bloqueia (o WSL2 é o caminho pra destravar sem desligar a
   proteção — decisão do Matheus). Decisão dele: nuvem melhor na frente, Ava de reserva nas duas
   línguas, a local não sai. Com a chave do Gemini: a voz **Aoede**, escolhida pelo Matheus ouvindo 8
   das 30, no **gemini-3.8-flash-lite-tts** grátis "por ora". O flash-tts grátis dá 10 pedidos por
   dia (cada resposta são 2 a 4) — pouco pra se acostumar; o limite do Lite está por descobrir no
   uso. Pago, pelo preço oficial: US$ 0,0015 (Lite) ou 0,00225 (Flash) a cada 10 s de fala até o fim
   de 2026, o dobro em 2027 — uns US$ 2 a 3 por mês com 20 respostas faladas por dia; e no pago o
   Google não usa o conteúdo (no grátis, usa). O botão de ouvir foi aprovado pelos prints
   (`design/fala-validacao.png`). Seletor em Configurações → Voz (voz do Gemini com amostra, Flash ou
   Flash-Lite, e "Responder falando"), com as peças já aprovadas da tela; aprovado pelo Matheus
   pelos prints (`design/voz-configuracoes-validacao.png`).
2. **Palavra de ativação** ("Solis"): hoje quem ouve é o **Whisper**. O Matheus escolheu o
   Porcupine, mas a conta do Picovoice passou a pedir e-mail de empresa e virou teste de 7 dias; a
   decisão dele foi "Whisper agora e depois focamos em ajustar". O navegador manda o microfone pro
   servidor do Solis (só em 127.0.0.1) por WebSocket; o começo de cada trecho de fala vai pro
   Whisper, e se começa com "Solis", um bipe, a caixa mostra "Ouvindo… pode falar" e a mensagem vai
   sozinha — com a resposta falada se "Responder falando" estiver ligado. Medido com vozes
   sintéticas: 31/32 acordaram, 0/40 alarmes falsos; a mensagem chega 4 a 5 s depois do fim da fala.
   O custo: a GPU trabalha a cada trecho de fala que o microfone pega. Linha em Configurações → Voz
   (só o interruptor), o "Ouvindo… pode falar" e o bipe: aprovados pelo Matheus pelos prints
   (`design/ativacao-validacao.png`). Falta: medir com a
   voz real do Matheus e ajustar (tempo de resposta, fim da fala); depois, o openWakeWord com um
   modelo "Solis" treinado no Colab, pra GPU não trabalhar à toa.
3. **Camada 3 da assinatura**: o brilho do símbolo do logo seguindo a voz enquanto o Solis ouve
   (microfone ou palavra "Solis"), medido no navegador, sem esperar o Whisper. Feito em
   09/11/2026 e aprovado pelo Matheus pelos prints (`design/brilho-voz-validacao.png`); os limites do nível saíram
   de vozes sintéticas e precisam de calibração com o microfone do Matheus. Detalhes e custo medido
   em `docs/SOLIS_SIGNATURE.md`. De quebra: o pulso do microfone passou pro ícone (custava ~330 ms
   de main thread em 6 s com o mouse em cima — `docs/PERFORMANCE.md` 1.1).
4. **Voz rápida no local** (11/11/2026, pedido do Matheus depois do primeiro teste com a voz dele:
   "que horas são" não precisa do Claude, e a voz falava demais). O pedido feito pela voz, com
   resposta falada, vai primeiro pro modelo local, sem raciocínio e sem ferramentas; a nuvem fica
   de reserva. Medido com o qwen3:8b: primeira palavra em 0,07 a 0,2 s e resposta inteira em
   0,5 a 0,7 s, contra 7 a 10 s do Claude só até a primeira palavra; 13 de 14 pedidos certos
   (hora, data, conta, agenda, tarefas, lembretes). Com raciocínio: 5 s. A hora de um lembrete
   ("daqui a 30 minutos", "às 15h") é calculada em código antes da resposta, e a mesma vai pra
   resposta falada e pro aviso. Pergunta de arquivo pela voz vai com raciocínio e ferramentas.
   O modelo é carregado na GPU quando a escuta ouve "Solis", enquanto ainda falta o pedido.
   Todo cérebro recebe a data e a hora, e os de nuvem respondem como o Solis (sabem que ele
   anota lembretes e avisa na hora).
   No segundo teste (11/11/2026, 10:21) a primeira palavra levou 9,4 s: o modelo estava frio. As
   tarefas de fundo devolviam o prazo dele na GPU pro padrão (5 min), e o aquecimento não sabia
   qual modelo usar depois de o servidor reiniciar. Agora todo pedido mantém o modelo 15 min, o
   modelo da conversa fica guardado, e quente a primeira palavra sai em 0,06 a 0,9 s. Lembrete com
   hora ("me lembra de X daqui a 20 minutos") vira tarefa na hora, em código, antes da resposta —
   a extração de fundo levava ~25 s. Depois do "Solis", a escuta espera 8 s pelo pedido (eram 5).
   Terceiro teste (11/11/2026, 10:38): ouviu "Quero ação" no lugar de "que horas são", buscou na
   memória pra isso, inventou a hora (10:48 com o relógio em 10:38) e o aviso do Windows não saía
   (o servidor com --reload não abre processos com asyncio; agora abre numa thread). Decisão: o
   básico não passa pelo modelo. Hora, data, lembrete com hora, agenda e tarefas de hoje/amanhã são
   respondidos em código (`rapidas.py`), em milissegundos, sem busca e sem modelo, e tolerantes aos
   erros de ouvido medidos ("E horas são", "a manhã", "me lembro"). O Whisper passou pro
   large-v3-turbo: em 24 comandos de voz baixa com ruído os três modelos erram 3, mas o small erra
   longe ("E oração") e o turbo perto; custa 0,15 s a mais. A voz é o gargalo que sobra: 3 a 6 s
   pra uma frase curta (o Gemini grátis acabou a cota do dia; a Ava leva 4 a 6 s; o Kokoro na
   CPU, 5,6 s).
5. **Voz em primeiro (16/11/2026, `docs/IDEIAS.md`: "nada novo antes de a voz passar no teste").**
   - **O teste de qualidade:** Configurações → Voz → Teste da escuta (`voz_teste.py`). Um roteiro
     de ~3,5 min com 12 chamadas (baixinho, de longe, rápido, com pausa) e 6 trechos sem "Solis"
     (fala normal, "sol", "Lis", "solista", silêncio). A escuta roda sobre a gravação como ao vivo
     e conta: acordou, entendeu (as palavras do pedido), alarmes falsos e o tempo do fim da fala
     (marcado pelo Silero VAD) ao texto. Meta: 9 em 10, sem alarme falso.
   - **Achado 1 — o Whisper do PC de verdade era outro:** o `large-v3-turbo` só existia numa
     pasta isolada das ferramentas do Claude Code (baixado por um processo delas em 11/11). No
     Windows de verdade só há o `small`. O Solis procurava o turbo e não achava, então nem a
     escuta nem o microfone transcreviam. Agora usa o melhor que estiver na pasta (turbo, medium,
     small) e diz no log.
   - **Achado 2 — 2 s perdidos em toda transcrição:** antes de cada uma, o Solis perguntava ao
     Ollama os modelos instalados (pro vocabulário). Com o Ollama desligado, o Windows leva ~2 s
     pra desistir da porta. Agora a lista fica guardada e é atualizada em segundo plano. Medido na
     mesma gravação: do fim da fala ao texto, de 3,25 s pra 1,02 s; o Whisper por trecho, de
     2,35 s pra 0,11–0,18 s.
   - **A base, com voz sintética (Maria do Windows) e o `small`:** acordou 12 de 12, entendeu 7 de
     12, 0 alarmes falsos, 1,0 s. O que sobra do tempo é a espera de 0,9 s de silêncio pra dar a
     fala por acabada.
   - **O turbo no PC de verdade** (16/11/2026, 1,62 GB, baixado pelo terminal do painel). O Solis
     troca de modelo sozinho quando um melhor chega na pasta.
   - **O Silero VAD** (o detector de fala de 2 MB que já vem com o faster-whisper), quadro a
     quadro, como opção da escuta (`SOLIS_ESCUTA_VAD=silero`); fim da fala depois de 0,6 s de
     silêncio, contra 0,9 s da energia. Na mesma gravação sintética:

     | Escuta | Acordou | Entendeu | Falsos | Fim da fala → texto |
     |---|---|---|---|---|
     | energia + small | 12/12 | 7/12 | 0 | 1,02 s |
     | Silero + small | 12/12 | 7/12 | 0 | 0,76 s |
     | energia + turbo | 12/12 | 6/12 | 0 | 1,12 s |
     | Silero + turbo | 12/12 | 7/12 | 0 | 0,88 s |

     Os erros que sobram são do Whisper com a voz robótica da Maria ("beber ígua", "desliga a
     MCC"). O padrão não muda com base nela: a gravação do Matheus é medida com as duas escutas, e
     a decisão sai da voz dele.
   - **A voz do Matheus (16/11/2026, 09:09, o microfone do notebook, o turbo):** a escuta de hoje
     (energia) acordou 10 de 12, entendeu 10 de 12, 0 alarmes falsos (nem com "sol", "Lis",
     "solista"), ~1,0 s do fim da fala ao texto. Com o Silero: 8 de 12 ("Dizlega, Muzica", "agenda
     de cesta" — corta a fala em lugares piores pro Whisper): **o padrão continua a energia.**
     As duas que faltaram: "Ei Solis…" virou "É isso, Solis." e foi descartado (o "Solis" só valia
     na primeira palavra ou depois de ei/oi/ok); e "mais baixo que o normal" não passou nem pelo
     Silero (baixo demais pro microfone). Agora o "Solis" vale depois de até duas palavras curtas
     ("é isso, Solis", "olha, Solis"), e não com três ou mais ("me passa o Solis"). Na mesma
     gravação: **acordou 11 de 12, entendeu 10 de 12, 0 falsos.** O que sobra: o Whisper ouviu
     "Conta 15 vezes 3" no lugar de "quanto é quinze vezes três", e a fala baixa demais.
     A régua também foi corrigida: o fim da fala é o do pedaço que acabou antes do texto, contado
     desde o "Prepare-se" (havia tempos negativos), e o que o Whisper ouviu e foi descartado fica
     guardado na medida.
   - **A resposta inteira, por voz (16/11/2026, no servidor de verdade):**

     | Parte | Tempo |
     |---|---|
     | fim da fala → texto (escuta) | ~1,0 s |
     | texto → primeira palavra, hora/data/lembrete/agenda (`rapidas.py`, em código) | 0,03 s |
     | texto → primeira palavra, pergunta comum (Claude) | 3,5 a 13,7 s |
     | primeira frase → primeiro som (Fish Audio) | 0,7 a 0,8 s |

     Achados: (1) o Ollama desligado custava 2 s em toda consulta (o `connect=2.0` esperando o
     Windows desistir): na memória antes de cada resposta, no modelo local da voz. Agora a falha
     vale por 60 s (`ollama.FORA_S`): medido, 2,1 s na primeira e 0,01 s nas seguintes. (2) Uma
     resposta por voz de verdade (09:10) passou do local (fora) ao Claude (20 s e caiu) e ao Codex
     (primeira palavra em 27 s). Agora, na voz, os cérebros de API vêm antes dos que sobem um CLI.
     (3) O Gemini grátis respondeu 503 (sobrecarregado) e o Claude ficou de reserva. O que falta
     pro "perto de 1 s" do `IDEIAS.md` é um cérebro rápido pra voz: o local (Ollama ligado) ou
     uma chave grátis da Groq.
   - **O local na voz, medido com o Ollama ligado (16/11/2026):** o Matheus escolheu "os dois"
     (local primeiro, Groq de reserva), e o Solis passou a ligar o Ollama sozinho. Medido com a
     placa livre: o qwen3:8b deu a primeira palavra em 11 a 38 s nas perguntas comuns e errou
     fatos ("Não sei" pra capital da Austrália; "o Sol é a única estrela que não é azul"); só a
     conta saiu em 0,2 s. O motivo da lentidão: o aprendizado de depois de cada resposta roda no
     mesmo modelo, e a pergunta seguinte espera (a memória chegou a 22 s esperando os vetores).
     Pela regra-mãe ("nada de lorota"), o local não serve de primeiro na voz nesta máquina. Ligar o
     Ollama sozinho ficou desligado por padrão (`SOLIS_LIGAR_OLLAMA=1` liga), e o Ollama que o
     Solis tinha ligado foi desligado. Ficaram: com o modelo vazio (a tela leu a lista com o
     Ollama fora), o servidor usa o último escolhido; e um cérebro de API que não começa a
     responder em 15 s cai pro próximo (o Gemini grátis tinha ficado 60 s calado).
   - **A Groq na voz (16/11/2026, chave grátis do Matheus, `openai/gpt-oss-120b`):** nas mesmas
     perguntas, a primeira palavra em 0,6 a 1,5 s depois do texto, e as cinco certas ("Canberra",
     "quarenta e cinco"). Decisão do Matheus: **na voz, a Groq primeiro** — os de API na ordem
     escolhida, depois o local, e o Claude e o Codex por último; o privado continua só no local;
     hora, data, lembrete e agenda continuam em código, antes de tudo. Uma pergunta comum por voz
     fica em ~2,5 a 3 s do fim da fala ao primeiro som (escuta ~1,0 s + Groq ~0,7–1,5 s + Fish
     ~0,75 s); antes, 5 a 30 s. Falta pro "perto de 1 s": transcrever enquanto ele fala e a voz
     começar pela primeira frase (a cascata do `IDEIAS.md`).
   - **A escuta presa depois de uma resposta falada (16/11/2026):** o Matheus chamou, ouviu a
     hora, e depois dez "Solis" sem resposta. No log: as duas respostas foram faladas, ele foi
     pra Memória logo depois, e nenhum áudio chegou mais ao servidor. A escuta pausa enquanto o
     Solis fala, e o "parei de falar" vinha do estado da tela de conversa — saindo dela, o aviso
     nunca vinha e a escuta ficava pausada pra sempre. Agora: quem fala fica num registro
     global, e sair da tela conta como "parei" (`src/fala.ts`); o áudio que não abre em 5 s ou
     fica 15 s sem avançar conta como falha (`src/somAosPedacos.ts`); e uma pausa de mais de
     90 s volta a ouvir sozinha (`src/escuta.ts`). Falta conferir no uso dele.
   - **A primeira chamada perdida (16/11/2026):** o Whisper saía da memória depois de 10 min
     sem fala, e voltar custa caro — medido nesta máquina (RTX 4060 8 GB, turbo): carregar
     5,5 s e a primeira transcrição 1,2 s, contra 0,3 s com ele carregado. O primeiro "Solis"
     depois de um tempo quieto esperava ~7 s pelo bipe; e o prazo de 8 s pra começar o pedido
     contava do "Solis", não do bipe — sobrava 1 s, ou nada. Agora: com a escuta ligada, o
     Whisper fica carregado e já sobe (com uma transcrição de silêncio, que carrega a cuBLAS)
     quando ela abre — a primeira chamada medida em 0,32 s; e uma decisão que demora estica o
     prazo do pedido pelo mesmo tempo (até 10 s). O preço: **1,1 GB de VRAM** enquanto a
     escuta estiver ligada (desligando, os 10 min voltam a valer). O log anota quando uma
     decisão passa de 1,5 s — só o tempo, nunca o que foi dito. Não dá pra afirmar que foi
     isso naquela manhã (o log não guarda o que o Whisper ouviu), mas é o caminho medido que
     perdia a chamada.
   - **"Às vezes demora": a etapa da memória (16/11/2026).** No log, ela ia de 0,05 s a 22 s
     antes de cada resposta. Duas causas, as duas no vetor da pergunta (o embeddinggemma no
     Ollama):
     - **Ollama desligado:** a porta recusada custa **2,05 s** no Windows (medido). A
       lembrança de "fora" durava 60 s, e na voz as perguntas vêm a mais de um minuto uma da
       outra: quase toda pergunta por voz pagava os 2 s (a de 11:14:57 ficou em 2,36 s). Agora,
       passado o prazo, as perguntas continuam falhando na hora, e uma sonda em segundo plano
       (uma conexão numa thread, a cada 5 s) vê quando ele volta. Medido com o Ollama fora: a
       primeira busca 2,2 s, as seguintes **0,01 s** — inclusive depois do prazo.
     - **Ollama ocupado** (o aprendizado de fundo rodando no mesmo Ollama): 22, 18 e 11 s no log.
       Agora o vetor tem **1,5 s**; passado isso, a resposta segue sem os trechos de conversas
       antigas (as memórias vão todas até 30, como já ia com o Ollama fora), e o pedido do
       vetor continua, pra deixar o modelo carregado. Não medido ao vivo com o Ollama ocupado
       (ele estava desligado na hora): os números são os do log.
   - **A cascata (16/11/2026).** Medido antes, no servidor de verdade, do envio do texto ao
     primeiro byte de som: memória 0,02–0,04 s, primeira palavra da Groq 0,47–0,93 s, o resto da
     resposta e os pedidos da fala +0,08 s, o primeiro byte da Fish +0,64–0,73 s — 1,2 a 1,7 s;
     antes disso, os 0,9 s de silêncio e ~0,3 s de Whisper na escuta. O que mudou:
     - **A escuta transcreve no silêncio.** Calado há 0,35 s, o que ele disse já vai pro
       Whisper (com o silêncio completado até 0,9 s repetindo o ruído do cômodo — cortado
       ali, o Whisper errava mais: "sexta" virou "cesta"). Se ele continuar calado, o texto já
       está pronto; se for pergunta ("?"), acaba em 0,6 s. Voltou a falar, vale o de antes. A
       conferência cedo que não acha "Solis" é refeita no fim, inteira ("Solis, desliga a
       música" virou "Sani, Zizlega" cedo): custa um Whisper a mais por fala sem "Solis" (na
       gravação, 37 contra 29).
       Na gravação do Matheus, num processo só e duas rodadas iguais:

       | | acordou | entendeu | falsos | latência mediana | p90 |
       |---|---|---|---|---|---|
       | antes | 11 | 10 | 0 | 1,03 s | 1,12 s |
       | cascata | 11 | **11** | 0 | **0,61 s** | 0,81 s |

       O teste da escuta passou pela primeira vez (11 de 12, a meta é 9 de 10).
     - **A Groq pensa pouco na voz** (`reasoning_effort: low` no gpt-oss): 10 perguntas de
       fato, 10 certas nos dois; a primeira palavra mediana de 0,68 s pra 0,47 s.
     - **Conexões guardadas com a Groq e a Fish** (`conexoes.py`), abertas quando a escuta ouve
       "Solis": a conexão nova custava 0,05 a 0,25 s a mais que a reusada.
     - **Na voz, 5 s do pedido à primeira palavra**: com a Groq no limite, o Gemini levou 12 s
       só pra devolver 503, e a resposta saiu em 22 s; agora quem não começa em 5 s passa a vez.
     - Medido depois, as mesmas 4 perguntas: o primeiro byte de som de 1,22–1,72 s pra
       1,17–1,37 s. A tela ainda espera a resposta inteira pra começar a falar; com a Groq isso
       custa ~0,06 s (a resposta curta acaba logo), por isso ficou pra depois.
   - **Nada de lorota na voz (16/11/2026).** Com a Groq na frente, os pedidos de ação do roteiro
     do teste da escuta receberam: "Desliga a música." → "Música desligada."; "Abre a minha agenda
     de sexta." → "Abrindo sua agenda de sexta."; "Anota que gastei trinta reais" → "Anotei" —
     nada disso aconteceu (o "anotei" porque o aprendizado roda sempre no modelo local, e o Ollama
     estava desligado). E "pesquisa o preço do dólar" → "Não sei". Agora (`roteador.py`):
     - quem não tem ferramenta (Groq, Gemini, Mistral, OpenRouter) é avisado de que só escreve
       texto e nunca diz que fez algo; se o pedido precisar de ação, internet ou do que mudou hoje,
       responde só a marca `[FERRAMENTA]` e o pedido passa direto pro Claude (o único que age, pelo
       Agent SDK), sem perguntar os outros de API; sem o Claude na fila, diz que não consegue;
     - com o Ollama fora, todos são avisados de que o aprendizado está desligado: ninguém diz que
       guardou (o Claude ainda cria lembrete e compromisso pelas ferramentas `mcp__solis__`).
     Medido com `/groq` na frente (só a Groq, sem passar): os 6 pedidos de ação honestos ("Desculpe,
     não consigo desligar a música agora."; "agora não dá pra guardar isso; volta quando o Ollama
     estiver ligado"). As 10 perguntas de fato continuam na Groq (nenhuma passou por engano), 9 de
     10 certas — o "Dom Casmurro" deu "Não sei" uma vez e 4 de 4 certas repetido sozinho (acaso do
     modelo pensando pouco). **Não medido ao vivo:** o pedido passando pro Claude, porque ele age
     de verdade no PC (pausar a música, abrir programa) — fica pro Matheus testar. E o Claude pela
     voz leva 3,5 a 14 s: falta o Solis dizer algo enquanto isso (a narração do `IDEIAS.md`).
   - **O aprendizado na Groq com o Ollama fora (16/11/2026, decisão do Matheus).** O aprendizado
     roda no modelo local (lê o privado, não gasta cota); com o Ollama desligado — o padrão desde
     que ligar sozinho ficou desligado — nada era guardado. Agora, se o local não responde, o que
     não é privado aprende na Groq: sem a mensagem privada, e sem as memórias e as falas privadas
     que iriam junto. No gpt-oss-20b, porque o limite grátis da Groq é por modelo e o 120b fica pra
     voz. O limite por minuto (tokens: ~1.300 de entrada por aprendizado, 2 a 3 por minuto no
     grátis) é esperado sozinho, até 30 s, e o JSON fora do esquema é refeito uma vez. O aviso
     "aprendizado desligado" pros cérebros só vale agora sem o Ollama e sem a Groq.
     **O teste do aprendizado** (`aprendizado_teste.py`, `POST /aprendizado/teste?onde=groq|local`):
     14 casos inventados (fato, pergunta, pedido de guardar, mudança de cidade e de emprego com
     substituição, tarefa, compromisso com dia e hora, saúde marcada privada, agradecimento) pela
     extração, sem guardar nada. Na Groq (gpt-oss-20b): **14 de 14**, 0,82 s cada (o qwen3:8b levava
     11 a 13 s). O título e o resumo da conversa continuam só no local.
   - **A narração (16/11/2026).** Pela voz, quando o pedido vai pro Claude ou pro Codex (passou
     pra quem tem ferramentas, ou os rápidos caíram), a tela fala na hora uma frase fixa: "Vou
     passar pro Claude, um instante." — eram 3,5 a 14 s de silêncio. A frase é gravada uma vez com
     a voz escolhida (`GET /fala/frase/{nome}`, `fala.FRASES`) e fica no disco
     (`%LOCALAPPDATA%\Solis\voz\frases`); trocou a voz, grava de novo; a voz de reserva (a Fish
     caiu) não fica gravada. O servidor grava as que faltam quando sobe (só com a Fish). Medido: a
     primeira vez 2,47 s (a Fish gerando), depois **0,004 a 0,013 s**. A resposta espera a frase
     acabar em vez de cortá-la, e a escuta pausa durante ela. **Não visto ao vivo:** precisa de um
     pedido por voz que passe pro Claude, que age de verdade no PC — fica pro Matheus testar
     ("Solis, pesquisa o preço do dólar hoje").
   - **A voz fala enquanto a resposta chega (16/11/2026).** Antes a tela esperava a resposta
     inteira; agora cada frase completa (ponto, exclamação ou interrogação seguidos de espaço —
     "3.5" não corta) vai pra voz assim que termina, e o resto no fim (`fala.ts`: `acompanhar`,
     uma fila que toca em ordem e já carrega o pedaço seguinte). Visto no navegador, num
     servidor de teste com um cérebro falso que manda três frases a 1,5 s uma da outra: a voz da
     primeira foi pedida 0,09 s depois dela chegar, a da segunda 0,04 s depois, a última no fim —
     antes, tudo só depois do fim, **4,45 s mais tarde** nessa resposta. Com a Groq (a resposta
     curta acaba em ~0,06 s) quase não muda; com o Claude, são os segundos da resposta inteira.
     Resposta que falha no meio fecha a fila (a escuta não fica pausada); depois de tudo, a tela
     volta a "parado".
   - **A chamada que nunca acorda: "mais baixo que o normal" (16/11/2026).** É a única que falha
     no teste da escuta, antes e depois da cascata. Medido na gravação: as chamadas normais têm
     pico de −19 a −25 dBFS sobre um ruído de −39 a −44; a baixa, pico −32,7 e quase toda em −39,
     só 4 a 10 dB acima do ruído — 0,1 s passa do limiar (+7 dB), e trecho com menos de 0,2 s é
     tratado como estalo. Testado na gravação: limiar +5 dá o mesmo (11 de 12); +4 cai pra 8 e +3
     pra 7 com um falso acordar (o ruído gruda na fala); energia **ou** Silero, 10 de 12. E no
     trecho dela o Silero não marca fala nenhuma, e o Whisper, com o trecho inteiro amplificado,
     ouve "Obrigado por assistir." (o que ele inventa no silêncio). Ou seja: nessa gravação a voz
     baixa está no nível do ruído do cômodo — nenhum detector tira ela dali. O caminho é o
     microfone (o `IDEIAS.md` já diz: o do notebook piora; testar com headset). Ficou do estudo
     só uma correção: o limiar era o valor padrão do argumento, congelado quando o módulo
     carregava, e mudar ACIMA_DO_PISO no teste não mudava nada.
   - **O visual da voz no app (16/11/2026, aprovado pelo Matheus pelos prints).** Pedido no
     `IDEIAS.md` (a tela escurece e uma esfera mostra o estado real). Já existia a ilha
     (`Chamada.tsx`, pedida em 10/11), que segue os estados de verdade. Decisão do Matheus: com a
     janela do Solis na frente, o visual dentro do app; atrás ou minimizada, a ilha por cima das
     outras janelas (`janelaEmFrente.ts`). A primeira versão, um sol redondo, foi recusada ("ficou
     com cara de emoji, quero o Solis"): agora é o **símbolo do Solis com os estados já aprovados**
     (`SolisEstado`, `states.glow`), a 190 px — a largura em que o halo foi medido contra as
     referências da marca, então aparece como a folha de estados aprovada. Ouvindo = `listening`
     com o brilho seguindo o microfone (o mesmo do logo); pensando = `thinking`, e embaixo o que
     ele ouviu; falando = `responding`, e embaixo o começo da resposta (`EsferaVoz.tsx`,
     `layout.esfera`). O fundo é um gradiente da janela inteira centrado no símbolo (97% no
     centro, 62% nos cantos): 66% uniforme deixava a legenda em cima do "Fale com o Solis…", uma
     clareira oval virou mancha, e com 94% a saudação aparecia pelo arco vazado. Medido nos 24
     prints (3 temas × 2 navegações × 4 estados): o símbolo no centro da área de conteúdo, o
     texto a 51–53 px dele, o halo a até 18 px da arte, e o pior contraste é 14,98:1 no estado e
     11,83:1 na legenda. Custo em 6 s: pensando +8 ms e falando +15 ms de main thread sobre a mesma
     tela sem o visual, zero layouts. Folha: `design/esfera-validacao.png`; prints por
     `design/capturar-esfera.mjs`. De quebra: a ilha ficava em "respondendo" (sem texto) enquanto a
     narração tocava — agora fica em "pensando" até a resposta ter texto.

### Controle do PC e visão da tela

- Um agente leve em cada máquina que o Solis controla: arquivos, comandos, programas,
  navegador.
- Permissão por nível: ler é livre; escrever e executar pedem confirmação ou estão numa
  lista aprovada; tudo fica registrado. Motivo técnico: com acesso total e lendo páginas e
  e-mails, um texto malicioso pode mandar o Solis executar coisas (prompt injection).
- Visão sem gastar GPU: a tela é capturada continuamente só na RAM (últimos segundos), junto
  com o título da janela e o texto da interface pela acessibilidade do Windows. O modelo de
  visão só roda quando o Matheus pergunta. Capturas nunca vão pro disco.

### Laboratório de modelos

As mesmas perguntas em vários modelos, com resposta, tempo e nota guardados no SQLite. Serve
pra escolher modelos medindo — e é um projeto de análise de dados com dados reais.

### App de verdade e celular

- O Tauri sobe o servidor sozinho; instalador `.msi`; inicia com o Windows.
- Telegram como canal pelo celular (bot oficial e gratuito). WhatsApp só pela API oficial
  da Meta; as bibliotecas não oficiais violam os termos e podem banir o número.

## Voz e a GPU: como funciona a escuta contínua

A preocupação: "pra me ouvir o tempo todo, uma LLM tem que ficar rodando e vai comer a
placa de vídeo". Não precisa. Assistentes de voz resolvem isso em **camadas**, e só a
primeira fica ligada o tempo todo:

| Camada | O que faz | Roda | Custo |
|---|---|---|---|
| 1. Palavra de ativação | Só reconhece "Solis". Não entende mais nada | **Sempre**, na CPU | Mínimo: um modelo minúsculo |
| 2. Detector de voz (VAD) | Sabe quando você começou e parou de falar | Depois da ativação, CPU | Mínimo |
| 3. Transcrição (Whisper) | Transforma o áudio em texto | Só no trecho que você falou | Segundos de GPU ou CPU, depois para |
| 4. Modelo de linguagem | Pensa a resposta | Só quando há pergunta | O de hoje |
| 5. Voz (TTS) | Lê a resposta em voz alta | Só enquanto fala | Pequeno; o Kokoro roda até na CPU |

A camada 1 é parecida com o "Ok Google" do celular: um modelo de poucos megabytes treinado
pra uma palavra só, que roda na CPU sem a GPU perceber. Nada de LLM ligada o tempo todo. A
GPU só trabalha nos segundos depois que você diz "Solis".

**O LLM também não fica na GPU pra sempre.** O Ollama descarrega o modelo depois de alguns
minutos parado (configurável). O preço disso: a primeira resposta depois de uma pausa
demora mais, porque o modelo precisa ser carregado de novo. Dá pra escolher entre "GPU
livre" e "resposta instantânea" — é uma configuração, não uma limitação.

**Orçamento de 8 GB de VRAM.** Whisper, LLM e voz disputam a mesma memória. Modelo que não
cabe inteiro vai em parte pra RAM (offload) e fica várias vezes mais lento:

| Modelo | Tamanho | Cabe inteiro em 8 GB? |
|---|---|---|
| qwen3:8b | 5,2 GB | Sim, com folga |
| qwen3.5:9b | 6,6 GB | Sim, com pouca folga |
| gemma3:12b | 8,1 GB | Não |
| qwen3:14b | 9,3 GB | Não |

### Candidatos (nada fechado — escolher medindo)

| Função | Candidatos | Observação |
|---|---|---|
| Palavra de ativação | **Whisper** (hoje); openWakeWord (aberto, modelo treinado no Colab); Porcupine (agora só empresas) | Treinar "Solis" no openWakeWord aqui pede o PyTorch, bloqueado |
| Detector de voz | Silero VAD | Já vem junto do openWakeWord e do faster-whisper |
| Transcrição | faster-whisper (Whisper otimizado), whisper.cpp | O tamanho do modelo é a troca entre precisão e velocidade |
| Voz | Kokoro (82M, tem vozes pt-BR), Piper (mais leve) | Testar os dois em português antes de escolher |

## Questões pra depois do Solis completo

Anotadas pra não se perderem. Não são pra agora: ficam pra quando o Solis estiver inteiro.

### A GPU disputada: o Solis enquanto o Matheus joga

Levantada pelo Matheus em 08/11/2026. As tarefas de fundo (título, aprendizado, resumo) rodam no
qwen3:8b, que sobe pra GPU a cada mensagem: medido, ficam **5,6 GB de VRAM** ocupados depois de
uma mensagem só. Com um jogo aberto no notebook (8 GB), pedir pro Solis gravar uma coisa ou
anotar uma tarefa estoura a VRAM — o jogo ou o Solis perde.

O que se sabe até aqui, sem solução escolhida:
- **Ponte temporária:** o PC de casa (GTX 1650, 4 GB) atender as tarefas de fundo. Resolve o
  notebook, mas só enquanto o PC estiver ligado, e 4 GB não cabem o qwen3:8b.
- **A solução tem que ser definitiva**, e servir também quando o Solis for usado de outras
  máquinas, que não o notebook nem o PC de casa.
- Peças que já existem pra pensar nisso: o Ollama descarrega o modelo depois de alguns minutos
  parado; as tarefas de fundo não precisam ser na hora (dá pra guardar o pedido e aprender
  depois); o modelo de fundo é uma variável (`SOLIS_MODELO_FUNDO`); e a ideia de cada máquina
  com um papel (seção "Servidor em casa e acesso de fora").

## Pontos de atenção

- **Privacidade:** tudo fica num arquivo só. O que é privado vai criptografado (DPAPI, amarrado
  à conta do Windows); o resto é texto puro. Backup é copiar o `solis.db` — mas o que é privado
  só abre na mesma conta do Windows: reinstalar o Windows sem ela perde o que é privado.
- **Peso em disco:** texto pesa pouco (estimativa de ~20 MB por ano de uso diário). Os
  modelos é que ocupam gigabytes.
- **Qualidade da extração:** um modelo pequeno guarda coisas inúteis e deixa passar fatos.
  O pedido explícito ("grave") existe por isso. Medido em 12 casos (08/11/2026, números em
  `backend/README.md` → Raciocínio): qwen3:8b pensando acerta 12; llama3.2:3b acerta 6, troca a
  memória errada numa mudança ("me mudei pra Sorocaba" apagou "Trabalha na Syngenta") e, com
  "isso é privado: tenho asma desde criança", fica 120 s sem responder até o limite cortar —
  reproduzível, nas duas medições. Por isso as tarefas de fundo usam o qwen3:8b (`SOLIS_MODELO_FUNDO`),
  e não o modelo da conversa — com o custo de VRAM anotado em "Questões pra depois do Solis
  completo".
- **Pedido atendido por engano — corrigido:** num "grave: ...", o llama3.2:3b devolvia uma
  memória já guardada de outro assunto, e o pedido contava como atendido sem guardar nada. Agora
  a repetida só atende o pedido se tiver palavra de conteúdo em comum com a mensagem; senão vai a
  mensagem crua.

## Como o trabalho acontece

- **No notebook:** Claude Code local. Ele roda o app de verdade contra o Ollama real.
- **Longe do notebook:** Claude Code na nuvem, com o Ollama simulado e testes automáticos.
- **O GitHub é o ponto de encontro:** `git pull` antes de começar, commit e push ao terminar.
