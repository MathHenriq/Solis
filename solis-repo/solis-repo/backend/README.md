# Servidor local do Solis

FastAPI rodando em `127.0.0.1:8765`. É a ponte entre o front e o que roda na máquina
(hoje o Ollama; depois SQLite, Whisper, Piper). Só escuta localmente.

## Primeira vez (Windows, PowerShell)

```powershell
cd solis-repo\solis-repo\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

## Todo dia

Três coisas rodando, cada uma no seu terminal:

```powershell
ollama serve                         # se o Ollama já não abriu sozinho na bandeja
npm run backend                      # na raiz do app; usa o Python do .venv sozinho
npm run dev                          # o front, em http://localhost:1420
```

O `npm run backend` (`backend/subir.mjs`) acha o Python do `.venv` sem precisar ativá-lo, e sem
`.venv` ele não sobe — diz como criar, em vez de rodar com o Python do sistema, que tem outras
bibliotecas. Outra porta: `npm run backend -- --port 8766`.

A tela de Modelos locais diz quem está faltando: "Servidor do Solis desligado" é o
`npm run backend`; "Ollama fora do ar" é o `ollama serve`.

## Rotas

| Rota | O que devolve |
|---|---|
| `GET /saude` | `{"ok": true}` |
| `GET /modelos` | modelos instalados no Ollama, com tamanho, quantização, contexto e se está carregado. `503` se o Ollama não responder |
| `GET /conversas/atual` | a conversa da mensagem mais recente, com as mensagens. `id: null` se ainda não houver nenhuma |
| `GET /conversas` | as conversas do Solis com mensagem, da mais recente pra mais antiga: `id`, `titulo` (o que o modelo local deu, ou a primeira fala numa linha) e `atualizada`. `?q=` busca no título e no texto. As importadas ficam de fora |
| `GET /conversas/{id}` | uma conversa, com as mensagens. `404` se não existir |
| `POST /conversas` | cria uma conversa vazia e devolve o `id` |
| `POST /conversas/{id}/mensagens` | `{"modelo", "texto"}` → guarda a mensagem, decide quem responde (modelo local, Claude ou Codex) e devolve eventos em NDJSON, um por linha: as etapas (ver abaixo), os pedaços do texto e, se ninguém responder, o erro. A resposta é guardada inteira mesmo se a janela fechar no meio. `404` se a conversa não existir; os outros erros chegam como o último evento: `{"erro": "ollama_indisponivel"}`, `{"erro": "modelo_inexistente"}` ou `{"erro": "cerebro_indisponivel", "cerebro": "Claude"}` (o cérebro pedido com `/claude` ou `/codex` falhou) |
| `GET /memorias` | as memórias guardadas, da mais nova pra mais antiga. `?q=` busca no texto e no tema (índice FTS5): todas as palavras, por prefixo, sem diferença de acento, da mais ligada à busca pra menos |
| `PATCH /memorias/{id}` | `{"texto"}` → corrige o texto de uma memória que vale (a privada continua selada; o vetor é refeito). `404` se não existe ou já foi substituída, `400` se vazio |
| `DELETE /memorias/{id}` | esquece uma memória. Se ela tinha substituído outra, a antiga volta a valer |
| `GET /conhecimento` | os arquivos do Conhecimento, do mais novo pro mais antigo: `nome`, `tipo` (`pdf` ou `nota`), `paginas`, `privado`, `trechos` e `indexados` (quantos já viraram vetor). `?q=` busca no nome e no texto (de fonte privada, só no nome) |
| `POST /conhecimento?nome=...&privado=false` | o arquivo cru no corpo (não multipart). Lê, corta em trechos e guarda; os vetores saem em segundo plano. `400` com `nao_leu` e o `motivo` (formato, PDF escaneado, com senha, vazio), `409` com `ja_existe` se o mesmo conteúdo já entrou |
| `PATCH /conhecimento/{id}` | `{"privado"}` → sela (ou abre) o nome e o texto e tira (ou põe) do índice de busca |
| `DELETE /conhecimento/{id}` | apaga o documento e os trechos |
| `GET /cerebros` | os cérebros na ordem em que são tentados: `nome`, `rotulo`, `tipo` (`local`, `cli` ou `api`), `ligado`, `instalado` (o CLI existe; na API, há chave), `modelo`, `nota` e `site` (só API) e `pausa` (`{"ate", "motivo"}` enquanto está de lado depois de falhar, senão `null`) |
| `PUT /cerebros` | `{"ordem": [{"nome", "ligado"}, ...]}` → guarda a ordem e o liga/desliga (Configurações → Cérebros). Nome repetido ou desconhecido dá `400`; quem ficar de fora vai pro fim. O local fica sempre ligado |
| `PUT /cerebros/{nome}/chave` | `{"chave"}` → pros cérebros por API: confere a chave no próprio serviço (`GET /models`), escolhe o modelo, guarda a chave selada e liga o cérebro. `400` com `chave_recusada` ou `chave_vazia`, `502` com `provedor_fora`, `404` se não for um cérebro por API. A chave nunca volta em nenhuma resposta |
| `DELETE /cerebros/{nome}/chave` | apaga a chave e o modelo e desliga o cérebro |
| `POST /cerebros/{nome}/retomar` | tira o cérebro da pausa antes da hora (a cota renovou, o login foi feito). `404` se o nome não existe |

O modelo da Conversa é o marcado "Em uso" em Modelos locais. Clicar numa linha troca; sem
escolha, vale o primeiro modelo que conversa (embeddings nunca entra).

As conversas ficam num SQLite em `%APPDATA%\Solis\solis.db`. O app reabre a mais recente;
digitar `/nova` na Conversa começa outra (a anterior continua guardada).

## Título da conversa

Depois da primeira resposta, o modelo local lê o começo da conversa e dá a ela um título de 2 a 6
palavras ("Sistema de NF-e da loja"), que a lista de conversas mostra no lugar da primeira fala. É a
primeira das etapas de depois da resposta (`titulo`), e roda uma vez só por conversa. Sem o
Ollama a conversa fica sem título, com a primeira fala na lista, e a próxima mensagem tenta de
novo.

## Raciocínio nas tarefas de fundo

Modelos que pensam antes de responder (qwen3) pensam também nas tarefas de fundo, e isso custa
tempo de GPU. Cada tarefa foi medida com e sem raciocínio no qwen3:8b (08/11/2026):

| Tarefa | Pensando | Sem pensar | Escolha |
|---|---|---|---|
| Título | 5 a 22 s | 0,2 a 0,4 s, títulos tão bons | sem pensar |
| Resumo (6 fatos-chave, 34 mensagens) | 6 de 6 em 20,5 s | 6 de 6 em 2,4 s | sem pensar |
| Aprendizado (12 casos) | 12 de 12, ~11 s | 10 de 12, ~1 s: perdeu uma preferência e a senha do wifi | **pensando** |

No mesmo teste o llama3.2:3b acertou 6 dos 12 casos do aprendizado — e trocou "Trabalha na
Syngenta" por "Mora em Sorocaba" —, e no resumo copiou a conversa em vez de resumir.

Por isso as tarefas de fundo têm modelo próprio, e não o da conversa: `SOLIS_MODELO_FUNDO`
(padrão `qwen3:8b`). Se ele não estiver instalado, ou o Ollama não responder à lista, vale o
modelo da conversa. Custo: o qwen3:8b ocupa ~5,6 GB de VRAM depois de cada mensagem (medido) —
questão em aberto em `docs/ESCOPO.md`.

## Memória

Depois de cada resposta, o servidor pergunta ao mesmo modelo, em segundo plano, o que a
mensagem tem de novo e duradouro sobre o Matheus, e guarda com um tema. Se a mensagem pede
pra guardar ("grave", "guarde", "anote", "memorize", "lembre", "registre"), algo é guardado
de qualquer jeito: se o modelo não achar nada, ou o Ollama estiver fora, vai a própria
mensagem, com o tema "Pedido direto".

**Memória que muda.** O extrator vê as 15 memórias mais ligadas à mensagem, numeradas, e pode
dizer que a nova substitui uma delas ("saí da Syngenta, agora trabalho na Vale"). A antiga não
é apagada: fica no banco com `substituida_por` apontando pra nova, e sai da tela e do prompt.
Se o modelo errar a substituição, nada se perdeu. Só vale número que o modelo viu na lista; e
o que era privado continua privado depois de atualizado.

**Privada.** O modelo marca como privada o que for saúde, senha, finanças ou documento
pessoal; e se a mensagem disser "privado", "confidencial", "sigiloso" ou "segredo", tudo que
sair dela é privado, concorde o modelo ou não. Nada privado vai pros cérebros de nuvem.

**Criptografada** (`solis/cofre.py`). O que é privado fica selado no `solis.db` com a DPAPI do
Windows, amarrada à sua conta: a memória, a mensagem que o disse e a resposta a ela, e — numa
conversa com algo privado — o título, o resumo e as etapas guardadas com as respostas (o chip
de memória guardada leva o texto). O Solis abre na leitura; a tela, os modelos locais e a busca
veem o texto normal. A memória privada sai do índice de busca e é procurada abrindo uma a uma.
Quando o sigilo só é descoberto pelo aprendizado, o que já tinha sido gravado legível é selado
ali, e o texto antigo é apagado do arquivo (`secure_delete`) e do `-wal` (checkpoint).

O que isso protege: o `solis.db` copiado pra outro computador ou outra conta — um backup que
vaza, um disco lido por fora. O que não protege: um programa rodando na sua própria conta, com
você logado, consegue pedir ao Windows pra abrir (é o mesmo nível das senhas salvas do Chrome).
E o que fica de fora: o tema da memória ("Saúde"), os vetores da busca por significado, e a
busca de conversas pelo texto, que não acha mensagem selada. **Atenção ao reinstalar o
Windows:** sem a mesma conta, o que é privado não abre mais (aparece "privado — não abre neste
computador"); o resto do banco continua legível. Fora do Windows não há DPAPI e fica como antes.

## Cérebros: quem responde

O Solis pode responder pelo modelo local (Ollama), pelo **Claude Code** e o **Codex** (CLI
oficial, com a assinatura do Matheus) e pelo **Groq**, **Gemini**, **Mistral** e **OpenRouter**
(API, no plano grátis de cada um) — nada pago por uso. Os CLIs precisam estar instalados e
logados no computador onde o servidor roda; as APIs, de uma chave colada em Configurações →
Cérebros.

- **Por API (`solis/apis.py`):** os quatro falam o formato `chat/completions` da OpenAI, então é
  um código só — cada serviço é um endereço, uma chave e um modelo. O modelo **não é fixado no
  código**: ao guardar a chave, o Solis lista os modelos do serviço e escolhe pela preferência
  (Groq: `openai/gpt-oss-120b`; Gemini: o Flash estável mais novo; Mistral:
  `mistral-medium-latest`; OpenRouter: um `:free`). A chave fica no banco selada pelo cofre
  (DPAPI) e nunca volta pro front. Limite grátis (`429`) pausa o cérebro até o `retry-after`;
  chave recusada, por um dia.
- **O preço do grátis**, que a tela mostra em cada um: o Gemini grátis pode usar o que recebe pra
  melhorar os produtos do Google; o Mistral treina até ser desligado no console; no OpenRouter
  quem roda o modelo grátis pode guardar o pedido. O que é privado não chega a nenhum deles.

- **Ordem de preferência:** escolhida em Configurações → Cérebros (ordem e liga/desliga,
  guardados no banco, tabela `ajustes`). Até a primeira escolha vale `SOLIS_CEREBROS` (padrão
  `claude,codex,local`). O local nunca desliga: é por ele que passa o que é privado. Cérebro
  desligado só responde chamado pelo comando. Quem não está instalado é pulado; quem falha antes
  da primeira palavra (sem login, cota acabada, travado) também, e fica de lado por um tempo — o
  Claude diz quando a cota renova; o Codex, 30 minutos. A tela mostra até quando e por quê, e
  "Tentar agora" encerra a pausa.
- **Travado:** o CLI que não escreve a primeira linha em 20 s, ou fica calado entre duas linhas
  mais de 20 s (Claude) ou 60 s (Codex, que gera calado e entrega tudo de uma vez), é morto. Antes
  da primeira palavra o próximo cérebro tenta; depois, a resposta fica cortada onde parou.
- **Comando na mensagem:** `/claude`, `/codex`, `/local`, `/groq`, `/gemini`, `/mistral` ou
  `/openrouter` na frente escolhe quem responde (mesmo desligado), sem
  plano B — se falhar, o aviso diz isso em vez de outro responder sem pedir.
- **Sigilo:** mensagem com "privado", "confidencial", "sigiloso" ou "segredo" só vai pro local.
- **O que nunca vai pra nuvem:** memória privada, mensagem privada (no histórico ou como trecho
  antigo) e o resumo de uma conversa que tenha algo privado.
- **Extração de memória, vetores e resumo rodam sempre no modelo local**, qualquer que seja
  quem respondeu: leem o que é privado e não podem gastar cota.
- Os CLIs rodam sem ferramentas (`--tools ""` no Claude, `--sandbox read-only` no Codex), numa
  pasta vazia do Solis. O prompt vai pela entrada padrão, nunca pela linha de comando.
- Custo de tempo: cada mensagem sobe um processo do CLI. Medido no notebook (1º/11/2026), do
  pedido à primeira palavra: Claude 4,5 a 5,3 s, Codex 3,9 a 7,1 s, modelo local carregado 0,1 s.
  As etapas de cada resposta ficam no log (abaixo) — é lá que se vê onde foi o tempo.

## Etapas da resposta

Cada resposta conta o que está fazendo, com o tempo desde o pedido (`t`, em segundos). Os
mesmos eventos vão pra tela (no stream) e pro log do servidor — no terminal e em
`%APPDATA%\Solis\solis.log`, que guarda até 4 MB — e ficam guardados com a resposta no banco.

| Etapa | Quando | Dados |
|---|---|---|
| `memoria` | a busca na memória terminou | `memorias`, `trechos` |
| `cerebro` | vai tentar este cérebro | `cerebro` |
| `processo` | o CLI foi iniciado (só Claude e Codex) | `cerebro` |
| `primeira_linha` | o CLI escreveu a primeira linha — já subiu | `cerebro` |
| `pensando` | o modelo começou a raciocinar (Claude, qwen3) | `cerebro` |
| `primeira_palavra` | a primeira palavra da resposta chegou | `cerebro` |
| `queda` | este cérebro falhou; vai o próximo | `cerebro`, `motivo` |
| `fim` | a resposta terminou; a tela libera o campo | `cerebro`, `cortada` se caiu no meio |
| `titulo` | depois da resposta, só na primeira vez: o título que a conversa ganhou | `titulo` |
| `aprendizado` | depois da resposta: memórias tiradas da mensagem | `novas`, `textos` |
| `indexacao` | depois da resposta: vetores calculados | `vetores` |
| `resumo` | depois da resposta: se a conversa foi resumida | `resumiu` |

O stream só fecha depois das etapas de depois da resposta: é por ele que a tela fica sabendo que a memória foi
guardada. No log, cada resposta termina numa linha só com todas as etapas:

```
13:04:58 solis.etapas conversa 3  resumo: memoria 0.16s · cerebro 0.16s · processo 0.18s · primeira_linha 0.81s · primeira_palavra 4.68s · fim 7.18s · aprendizado 8.37s · indexacao 8.41s · resumo 8.41s
```

O Codex foi integrado pela documentação e conferido rodando no notebook em 1º/11/2026: respondeu
pelo Solis (3,9 a 7,1 s do pedido à resposta) e o MCP de memória conectou.

## Servidor MCP: a memória do Solis no Claude Code e no Codex

`solis/servidor_mcp.py` deixa o Claude Code e o Codex consultarem a memória do Solis mesmo
quando usados direto no terminal, fora do Solis. Três ferramentas: `memorias_do_matheus`,
`buscar_na_memoria` e `guardar_memoria`. Nada privado aparece em nenhuma delas. Lê o
`solis.db` direto: funciona com o servidor do Solis desligado.

Registrar uma vez (troque o caminho pelo do seu clone):

```powershell
$backend = "C:\Users\Matheus\Documents\Solis\Projetos\Solis\solis-repo\solis-repo\backend"

# Claude Code
claude mcp add solis --scope user -e PYTHONPATH=$backend -- "$backend\.venv\Scripts\python.exe" -m solis.servidor_mcp
```

Codex, em `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.solis]
command = 'C:\Users\Matheus\Documents\Solis\Projetos\Solis\solis-repo\solis-repo\backend\.venv\Scripts\python.exe'
args = ['-m', 'solis.servidor_mcp']
cwd = 'C:\Users\Matheus\Documents\Solis\Projetos\Solis\solis-repo\solis-repo\backend'
```

Verificado com o Claude Code de verdade: ele subiu o servidor, chamou `memorias_do_matheus`,
respondeu com as memórias públicas, e a privada não apareceu.

## Importar o histórico do ChatGPT e do Claude

Peça a exportação em cada serviço (ChatGPT: Configurações → Controles de dados → Exportar;
Claude: Configurações → Privacidade → Exportar). Chega um .zip por e-mail. Com o `.venv`
ativado, na pasta `backend`:

```powershell
python -m solis.importar C:\caminho\da\exportacao.zip
python -m solis.importar C:\caminho\da\exportacao.zip --aprender --modelo qwen3:8b
```

- O formato é reconhecido sozinho. Importar o mesmo arquivo de novo não duplica nada.
- As conversas importadas entram na busca: perguntar ao Solis sobre algo que você conversou
  com o ChatGPT traz o trecho, marcado como dito pelo ChatGPT. Elas não viram a conversa aberta.
- `--aprender` tira memórias de cada conversa no modelo local — é lento (uma chamada por
  conversa). Ctrl+C pra parar; rodar de novo continua de onde parou. Fato antigo vem com a data
  ("Em 2023, trabalhava na X.") e **nunca substitui** uma memória atual: o passado não apaga o
  presente.
- O que foi dito em sigilo lá ("isso é privado...") é privado aqui também.

Formatos lidos de exportações reais por outros projetos — nenhum dos dois serviços publica o
esquema. O do Claude ainda precisa ser conferido com um arquivo seu: se a importação dele
disser "0 conversas novas" com o arquivo cheio, é o leitor que precisa de ajuste.

## Conhecimento: os arquivos

O Matheus entrega PDFs, `.md` e `.txt` pela tela Conhecimento (`solis/conhecimento.py`).

- **O que fica:** só o texto, cortado em trechos de ~200 palavras com 40 de sobra entre um e o
  próximo (uma ideia que cai na emenda continua inteira em algum dos dois). No PDF, cada trecho
  sabe a página. O arquivo original não é copiado. O mesmo conteúdo não entra duas vezes (hash).
- **PDF** pela `pypdf` (Python puro). PDF escaneado é imagem: sem OCR não há texto, e ele é
  recusado dizendo isso em vez de entrar vazio.
- **Vetores:** cada trecho vira vetor no `indexar_pendentes`, depois das memórias e mensagens
  (um PDF grande são centenas de trechos, e o que acabou de ser dito não pode esperar). A tela
  mostra o progresso real (`indexados` / `trechos`) e diz quando parou (Ollama fora).
- **Na resposta:** até 4 trechos com similaridade de pelo menos 0,65 entram no pedido, com o nome
  do arquivo e a página, numa seção própria. O piso foi medido (`busca.py`): perguntas sobre os
  arquivos deram 0,68 a 0,82, perguntas sem relação 0,56 a 0,60. Falta calibrar com arquivos de
  verdade.
- **Privado:** fonte marcada como privada tem o nome e o texto selados pelo cofre, fica fora do
  índice de busca e nunca vai pros cérebros de nuvem — o mesmo filtro dos trechos de conversa.
- **Banco:** a conexão é uma só, então ler o PDF roda numa thread mas guardar não — escrever de
  várias threads embaralhava as transações quando vários arquivos chegavam juntos.
- O MCP (`buscar_na_memoria`) devolve os trechos de arquivo à parte, com o nome e a página.

## Busca por significado

Cada memória e cada mensagem vira um vetor com o `nomic-embed-text` (precisa estar instalado
no Ollama). A cada mensagem nova, entram no pedido ao modelo:

- as memórias: todas, até 30; acima disso, as 12 mais parecidas com a mensagem mais as 5
  mais recentes;
- até 5 trechos de conversas antigas parecidos com a mensagem;
- da conversa aberta: o resumo do começo, se ela for longa, mais todas as mensagens depois
  dele.

**Conversa longa.** Quando as mensagens depois do resumo passam de 30, as mais velhas entram no
resumo e ficam as 20 últimas inteiras. Resumir em lote, e não a cada mensagem, evita uma
terceira chamada ao modelo em toda resposta. O que virou resumo ainda pode voltar como trecho
exato pela busca.

Sem o modelo de embeddings, volta pro comportamento anterior (as memórias mais recentes, sem
trechos antigos) e o que não foi vetorizado fica pendente pra próxima vez. O piso de
similaridade dos trechos (`PISO_TRECHO` em `solis/busca.py`) foi escolhido sem dados reais e
precisa ser calibrado.

## Testes

```powershell
python -m pytest
```

Não precisam do Ollama instalado — as respostas dele são simuladas.

## O que ainda não existe

- O Tauri não sobe este servidor sozinho. Hoje é `npm run backend` à mão; empacotar como
  sidecar fica pra quando o app for instalado de verdade.
- O preview na Vercel não tem servidor — lá a tela de Modelos mostra "Servidor do Solis
  desligado", e é o comportamento certo.
