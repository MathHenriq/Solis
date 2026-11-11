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
