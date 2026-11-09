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
| `GET /conhecimento` | os arquivos do Conhecimento, do mais novo pro mais antigo: `nome`, `tipo` (`pdf` ou `nota`), `paginas`, `privado`, `trechos` e `indexados` (quantos já viraram vetor), `escaneadas` e `lidas` (páginas-imagem e quantas o OCR já leu) e `leitura_parada` (`ollama`, `ocr` ou `null`). `?q=` busca no nome e no texto (de fonte privada, só no nome) |
| `POST /conhecimento?nome=...&privado=false` | o arquivo cru no corpo (não multipart). Lê, corta em trechos e guarda; os vetores saem em segundo plano. `400` com `nao_leu` e o `motivo` (formato, PDF sem texto nem imagem, com senha, vazio). Página escaneada entra na fila do OCR, `409` com `ja_existe` se o mesmo conteúdo já entrou |
| `POST /conhecimento/pagina` | `{"url", "privado"}` → baixa o endereço (com ou sem `https://`), tira o conteúdo principal e guarda como os arquivos; endereço de PDF entra como PDF. Os mesmos erros do `POST /conhecimento` (o `motivo` diz: 404, precisa de login, não é página, montada por JavaScript) |
| `PATCH /conhecimento/{id}` | `{"privado"}` → sela (ou abre) o nome e o texto e tira (ou põe) do índice de busca |
| `DELETE /conhecimento/{id}` | apaga o documento e os trechos |
| `GET /tarefas` | as abertas e as feitas hoje, da mais perto do prazo pra mais longe (sem prazo por último): `texto`, `prazo` (AAAA-MM-DD), `hora` (HH:MM), `conversa` e `origem` (o título dela), `privada`, `feita` |
| `POST /tarefas` | `{"texto", "prazo", "hora", "privada"}` → cria. `400` com `texto_vazio`, `prazo_invalido` ou `hora_invalida` |
| `PATCH /tarefas/{id}` | só o que vier muda: `{"feita": true}` marca, `{"prazo": ""}` tira o prazo e a hora junto. `404` se não existe |
| `DELETE /tarefas/{id}` | apaga |
| `GET /agenda?de=AAAA-MM-DD&ate=AAAA-MM-DD` | os compromissos do período (sem `ate`, só o dia), do dia inteiro pro mais tarde: `titulo`, `dia`, `hora` (null = dia todo), `duracao` (minutos), `onde`, `conversa` e `origem`, `privado` |
| `POST /agenda` | `{"titulo", "dia", "hora", "duracao", "onde", "privado"}` → cria. `400` com `titulo_vazio`, `dia_invalido`, `hora_invalida` ou `duracao_invalida` |
| `PATCH /agenda/{id}` | só o que vier muda; `{"onde": ""}` tira o lugar. `404` se não existe |
| `DELETE /agenda/{id}` | apaga |
| `GET /fala/ajustes` | a voz e o modelo do Gemini escolhidos, e as opções (`vozes`, `modelos`) |
| `PUT /fala/ajustes` | `{"voz", "modelo"}` → guarda; trocar o modelo tira o Gemini do descanso (o limite é por modelo). `400` se a voz ou o modelo não existe |
| `POST /fala/partes` | `{"texto"}` → `{"partes", "lingua"}`: a resposta em pedaços pra falar um de cada vez (o primeiro curto) |
| `POST /fala` | `{"texto", "conversa", "voz"}` → o áudio do pedaço (wav ou mp3), com quem falou em `X-Solis-Voz` e por que as anteriores caíram em `X-Solis-Antes`. `voz` troca a do Gemini só neste pedido. `503` com `sem_voz` e os motivos se nenhuma voz deu |
| `GET /voz` | `{"disponivel", "modelo"}`: se o faster-whisper está instalado e o modelo na pasta |
| `POST /voz` | o áudio cru no corpo (webm/opus do navegador, wav...) → `{"texto", "segundos", "duracao", "modelo", "onde"}`. Nada é guardado. `503` com `sem_modelo`, `400` com `audio_ruim` |
| `GET /ativacao` | `{"chave", "palavra", "idioma"}`: o que já está no lugar pra ouvir "Solis" |
| `PUT /ativacao/chave` | `{"chave"}` → a AccessKey do Picovoice, conferida (com o modelo, se já houver) e guardada selada. Nunca volta. `400` com `chave_recusada` ou `modelo_recusado` |
| `PUT /ativacao/palavra` | o `.ppn` do console do Picovoice, cru no corpo → guarda depois de conferir com a chave. `400` com `chave_recusada` ou `modelo_recusado` |
| `DELETE /ativacao` | apaga a chave e o modelo da palavra |
| `WS /escuta` | o navegador manda quadros de 512 amostras PCM 16 bits a 16 kHz; volta `{"tipo": "ativou"}` ao ouvir a palavra e, quando a pessoa para de falar, `{"tipo": "texto", "texto"}` ou `{"tipo": "nada"}`. `{"pausa": true}` suspende (o Solis está falando). `{"tipo": "erro"}` se falta configuração |
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

O Matheus entrega PDFs, `.md`, `.txt` e páginas da web pela tela Conhecimento
(`solis/conhecimento.py`).

- **O que fica:** só o texto, cortado em trechos de ~200 palavras com 40 de sobra entre um e o
  próximo (uma ideia que cai na emenda continua inteira em algum dos dois). No PDF, cada trecho
  sabe a página. O arquivo original não é copiado (a exceção é o PDF com página escaneada, guardado
  só até o OCR ler a última). O mesmo conteúdo não entra duas vezes (hash).
- **Página web** pela `trafilatura`: só o conteúdo principal, sem menu, rodapé e anúncio (o
  parser HTML da biblioteca padrão traria tudo junto). A página é identificada pelo endereço, que
  vai junto da fonte no pedido. Página montada por JavaScript ou atrás de login não tem o que ler.
- **PDF** pela `pypdf` (Python puro). Página com menos de 20 caracteres de texto e com imagem é
  escaneada: o PDF entra na hora, e essas páginas vão pra uma fila que o OCR lê em segundo plano.
- **OCR** (`solis/ocr.py`): o modelo de visão (`SOLIS_MODELO_VISAO`, padrão `qwen3.5:9b`) lê
  cada página renderizada a 150 dpi pelo PDFium (`pypdfium2`). Escolhido medindo, em 3 páginas de
  texto conhecido num PDF só de imagem (acerto por palavra):

  | Leitor | Digitalização boa (200 dpi) | Ruim (150 dpi, 10 pt, torta, JPEG forte) | Por página |
  |---|---|---|---|
  | OCR do Windows | 0,98 a 1,00 | 0,30 a 0,80 | 0,6 a 0,8 s, CPU |
  | qwen3.5:9b | 1,00 | 1,00 | 6 a 26 s, GPU |
  | gemma3:12b | 0,99 a 1,00 | — | 18 a 40 s, GPU |

  O OCR do Windows (`ocr_windows.ps1`, pelo PowerShell: o pacote WinRT pro Python é bloqueado pelo
  Controle de Aplicativo do Windows) é a reserva: lê quando o modelo de visão não está instalado,
  ou quando ele repete até o limite de saída. Não dá pra saber quando o Windows errou sem o texto
  certo, por isso ele não é o primeiro. A imagem vai pela entrada padrão: página de documento
  privado não passa pelo disco. Com o Ollama fora a fila espera (a página não fica lida pior pra
  sempre). Uma leitura por vez; cada `GET /conhecimento` retoma a fila se ela parou.
- **OCR e indexação não andam juntos:** indexar entre as páginas deixava o OCR 2,5× mais lento
  (16 s contra 6 a 7 s por página, medido — o modelo de embeddings e o de visão disputam a GPU).
  Enquanto o OCR lê, os trechos de arquivo esperam; a indexação roda quando a fila acaba.
- **Vetores:** cada trecho vira vetor no `indexar_pendentes`, depois das memórias e mensagens
  (um PDF grande são centenas de trechos, e o que acabou de ser dito não pode esperar). A tela
  mostra o progresso real (`indexados` / `trechos`) e diz quando parou (Ollama fora). Enquanto
  falta trecho, cada `GET /conhecimento` tenta indexar de novo (uma indexação por vez): quando o
  Ollama volta, a indexação anda sozinha.
- **Na resposta:** até 4 trechos acima do piso do modelo de embeddings (0,37 no embeddinggemma)
  entram no pedido, com o nome do arquivo e a página (ou o endereço), numa seção própria. Pergunta
  em português acha texto em inglês (ver Busca por significado).
- **Privado:** fonte marcada como privada tem o nome e o texto selados pelo cofre, fica fora do
  índice de busca e nunca vai pros cérebros de nuvem — o mesmo filtro dos trechos de conversa.
- **Banco:** a conexão é uma só, então ler o PDF roda numa thread mas guardar não — escrever de
  várias threads embaralhava as transações quando vários arquivos chegavam juntos.
- O MCP (`buscar_na_memoria`) devolve os trechos de arquivo à parte, com o nome e a página.

## Tarefas

Criadas pela tela ou tiradas da conversa (`solis/memoria.py`): a mesma pergunta de fundo que tira as
memórias tira as tarefas, numa chamada só ao modelo de fundo. O pedido leva o calendário dos próximos
35 dias (dia da semana e data): o modelo copia a data em vez de fazer conta.

Medido no qwen3:8b em 20 mensagens (09/11/2026): "dia 15", "sexta às 14h", "fim do mês", "daqui a
duas semanas", duas tarefas numa mensagem, saúde e dinheiro, e o que não é tarefa (pergunta, "me
ajuda a escrever um email", o que já foi feito, fatos sobre ele): **20/20 tarefas com o prazo certo,
11/11 na privacidade, 20/20 nas memórias**, em ~10 s. O modelo é determinístico pra um mesmo
pedido, mas cada frase mudada na instrução trocava qual caso ele errava. Por isso as contas ficam
no código:
- prazo de hoje na hora exata do pedido é o "Agora" copiado: sem prazo;
- dia da semana dito e prazo em outro dia, ou "daqui a N dias/semanas": a data é recalculada (só
  com uma tarefa e uma expressão na mensagem);
- memória que só repete uma tarefa sai (o modelo fazia isso em 4 de 17 casos);
- tarefa com palavra de saúde, dinheiro ou documento é privada (pedido ao modelo, ele acertava 9 ou
  10 de 11). Errar pra mais privada só tira a tarefa do pedido à nuvem.

As 20 abertas mais próximas do prazo vão em cada pedido ao modelo, com a data de hoje; a privada não
vai pra nuvem. Conversa importada não vira tarefa.

**Compromissos (Agenda).** A mesma pergunta tira também os compromissos: o que tem dia (e quase
sempre hora) em que o Matheus vai estar em algum lugar — reunião, consulta, aula, viagem —, com a
duração e o lugar se ditos. "Pagar", "entregar", "marcar a consulta" continuam tarefa. Medido no
qwen3:8b em 22 mensagens (09/11/2026): 18/18 compromissos, 18/18 tarefas, 22/22 memórias, ~13 s. No
código: mensagem que cancela, desmarca ou adia não cria compromisso, e a tarefa que repete um
compromisso sai. Os dos próximos 7 dias (até 20) vão no pedido ao modelo; o privado (pedido de
sigilo, memória privada da mesma mensagem, ou saúde e dinheiro no título) não vai pra nuvem.
Repetição ("toda terça") não existe ainda: vira a próxima.

## O Solis falando

`solis/fala.py`: a resposta vira voz por uma cadeia, na ordem — Gemini TTS (voz Aoede, modelo
`gemini-3.8-flash-lite-tts`, pelo endpoint `interactions`, com a chave do Gemini dos Cérebros; trocar
pela rota `/fala/ajustes`. O `gemini-3.8-flash-tts` grátis dá só 10 pedidos por dia) → Ava (`en-US-AvaMultilingualNeural`,
o serviço de leitura do Edge pelo `edge-tts`: sem chave, sem garantia — medido de 1,3 a 9 s por
frase) → Kokoro local (`kokoro-onnx`, pf_dora em português e af_heart em inglês, em
`%LOCALAPPDATA%\Solis\voz\kokoro`). A que falhar por limite ou chave (401/403/429) descansa 10 min.
Privado (conversa com algo privado, ou saúde, dinheiro e documento no texto) só vai pra local. O
texto é limpo pra fala (sem markdown, código vira "um trecho de código", endereço vira "o link") e
cortado em pedaços — o primeiro com até 90 caracteres, pra começar a falar logo. Os 64 últimos
pedaços ficam em memória. A Kokoro instala à parte: `pip install --ignore-requires-python -r
requirements-fala.txt`.

## Voz

`solis/voz.py`: apertar pra falar. O front grava pelo microfone do navegador e manda o áudio; o
Whisper (`small`, pelo faster-whisper) transcreve no computador e o texto volta pra caixa. O áudio só
vive no pedido.

- **Modelos** em `%LOCALAPPDATA%\Solis\whisper\` (baixados do Hugging Face: `Systran/faster-whisper-small`,
  e pra comparar `-medium` e `deepdml/faster-whisper-large-v3-turbo-ct2`). `SOLIS_WHISPER` troca.
- **GPU** (`int8_float16`, 455 MB) com a cuBLAS do Ollama (`lib/ollama/cuda_v12`, posta no PATH do
  processo); se não carregar — ou falhar na primeira transcrição, que é quando a cuBLAS é aberta —,
  CPU (`int8`) dali em diante. `SOLIS_WHISPER_DISPOSITIVO=cpu|cuda` força.
- **Vocabulário:** o `initial_prompt` do Whisper leva os nomes que o Solis conhece (os das memórias,
  dos títulos das conversas, dos arquivos do Conhecimento e as famílias dos modelos instalados). Foi
  o que mais pesou na medição: erro de 8,2% pra 2,1%.
- O modelo sobe na primeira fala (~2,5 s) e sai da memória depois de 10 min sem fala.
- O `decode_audio` do faster-whisper 1.2.1 não funciona com o `av` 19 (passa um parâmetro que saiu):
  a decodificação é feita direto pelo PyAV (`voz.decodificar`).

## Palavra de ativação

`solis/ativacao.py`: dizer "Solis, ..." sem clicar. O navegador abre o microfone, um AudioWorklet
(`public/escuta-processador.js`) entrega o áudio em 16 kHz e o WebSocket `/escuta` o traz pra cá. O
**Porcupine** (Picovoice) ouve a palavra na CPU; depois dela, o fim da fala é achado pela energia do
som e o trecho vai pro Whisper (`voz.py`). O texto volta pro navegador e vira mensagem na conversa. O
áudio não vai pro disco nem sai do computador.

- **O que o Matheus põe:** a AccessKey (conta grátis no console.picovoice.ai) e o modelo `solis.ppn`
  treinado lá (português, Windows), os dois em Configurações → Voz → Palavra de ativação. A chave
  fica selada no cofre (`chave:picovoice`).
- **Arquivos** em `%LOCALAPPDATA%\Solis\voz\porcupine\`: o `.ppn` e o `porcupine_params_pt.pv`
  (984 KB, baixado do repositório oficial do Porcupine na primeira vez; o pacote só traz o inglês).
- **Fim da fala** (PROVISÓRIO até medir com a voz real): pelo menos 0,4 s de fala, 0,9 s de
  silêncio encerra, no máximo 15 s; sem falar nada em 5 s depois da palavra, desiste. O silêncio é
  medido contra o ruído do ambiente (12 dB acima do piso, que se ajusta sozinho).
  `SOLIS_ATIVACAO_SENSIBILIDADE` (0,5) troca a sensibilidade do Porcupine.
- Enquanto o Solis fala, a escuta pausa — senão ele se ouviria.
- A DLL do Porcupine carrega sob o Controle Inteligente de Aplicativos (conferido); o WebSocket
  usa o `wsproto` (Python puro).

## Avisos na hora

`solis/avisos.py`, um laço do servidor que confere a cada 30 s. A notificação do Windows sai pelo
`avisar_windows.ps1` (PowerShell do sistema: o pacote WinRT pro Python é bloqueado pelo Controle de
Aplicativo do Windows, como no OCR).

| O quê | Quando | Se o servidor ligou depois |
|---|---|---|
| Compromisso com hora | 10 min antes | avisa até o compromisso começar |
| Tarefa com hora | na hora | avisa até 1 h depois |
| Resumo do dia (tarefas sem hora, compromissos de dia inteiro) | 8h, um aviso só | avisa até as 20h |

Cada aviso mostrado fica anotado (tabela `avisos`, migração 13) pela chave do item e da hora: nada
se repete, nem depois de religar, e mudar a hora de um compromisso faz ele avisar na hora nova. Aviso
que falha não é anotado e tenta de novo na volta seguinte. Item privado não mostra o título nem o
lugar (o aviso aparece até na tela bloqueada). Desligar: o ajuste `avisos` = `false`, ou
`SOLIS_AVISOS=0`. Enquanto o Solis não é um app instalado, o aviso sai em nome do "Windows
PowerShell", com "Solis" na linha de atribuição.

## Busca por significado

Cada memória, cada mensagem e cada trecho de arquivo vira um vetor com o **`embeddinggemma`**
(621 MB, roda na CPU; precisa estar instalado no Ollama: `ollama pull embeddinggemma`).
`SOLIS_EMBEDDING` troca o modelo.

**Escolhido medindo** (09/11/2026): 10 perguntas em português contra páginas reais em inglês
(FastAPI, SQLite, Tauri) e textos em português, mais 5 perguntas sem relação nenhuma.

| Modelo | Fonte certa em 1º | Menor nota certa | Maior nota de ruído | Folga |
|---|---|---|---|---|
| nomic-embed-text (o de antes) | 7/10 | 0,54 | 0,65 | −0,10 |
| qwen3-embedding:0.6b | 10/10 | 0,38 | 0,42 | −0,03 (e 11× mais lento) |
| bge-m3 | 9/10 | 0,48 | 0,56 | −0,09 |
| embeddinggemma | 10/10 | 0,45 | 0,29 | +0,16 |

O nomic quase não ligava português com inglês ("como rodo uma tarefa depois de devolver a
resposta no FastAPI?" dava 0,57 na página certa, nota de ruído). O embeddinggemma é o único em
que um piso separa o que importa do ruído: 0,37, no meio da folga. Cada modelo usa os prefixos
com que foi treinado (`busca.MODELOS`).

**Trocar de modelo refaz os vetores.** Vetores de modelos diferentes não se comparam; o banco
guarda qual modelo fez os seus (`ajustes`, `modelo_vetores`) e, se não for o atual, apaga todos
e o servidor os refaz em segundo plano ao subir. Nenhum texto é tocado.

A cada mensagem nova, entram no pedido ao modelo:

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
trechos antigos) e o que não foi vetorizado fica pendente pra próxima vez. Os pisos
(`busca.MODELOS`) foram medidos com um conjunto pequeno e precisam ser calibrados com as
conversas e os arquivos de verdade.

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
