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
npm run backend                      # na raiz do app, com o .venv ativado
npm run dev                          # o front, em http://localhost:1420
```

A tela de Modelos locais diz quem está faltando: "Servidor do Solis desligado" é o
`npm run backend`; "Ollama fora do ar" é o `ollama serve`.

## Rotas

| Rota | O que devolve |
|---|---|
| `GET /saude` | `{"ok": true}` |
| `GET /modelos` | modelos instalados no Ollama, com tamanho, quantização, contexto e se está carregado. `503` se o Ollama não responder |
| `GET /conversas/atual` | a conversa mais recente, com as mensagens. `id: null` se ainda não houver nenhuma |
| `POST /conversas` | cria uma conversa vazia e devolve o `id` |
| `POST /conversas/{id}/mensagens` | `{"modelo", "texto"}` → guarda a mensagem, decide quem responde (modelo local, Claude ou Codex) e devolve a resposta em texto puro, pedaço a pedaço; o cabeçalho `X-Solis-Cerebro` diz quem respondeu. A resposta é guardada no fim, mesmo se cortada no meio. `503` sem Ollama, `404` se o modelo ou a conversa não existirem, `502` se o cérebro pedido com `/claude` ou `/codex` falhou |
| `GET /memorias` | as memórias guardadas, da mais nova pra mais antiga |
| `DELETE /memorias/{id}` | esquece uma memória |

O modelo da Conversa é o marcado "Em uso" em Modelos locais. Clicar numa linha troca; sem
escolha, vale o primeiro modelo que conversa (embeddings nunca entra).

As conversas ficam num SQLite em `%APPDATA%\Solis\solis.db`. O app reabre a mais recente;
digitar `/nova` na Conversa começa outra (a anterior continua guardada).

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
sair dela é privado, concorde o modelo ou não. Hoje todo modelo é local, então nada sai de
qualquer jeito; a marca vale quando modelos de nuvem entrarem. Atenção: privada não é
criptografada — está em texto puro no `solis.db`.

## Cérebros: quem responde

O Solis pode responder pelo modelo local (Ollama) ou pelo **Claude Code** e o **Codex**,
chamados pelo CLI oficial com a assinatura do Matheus — nada de API paga. Os CLIs precisam
estar instalados e logados no computador onde o servidor roda.

- **Ordem de preferência:** `SOLIS_CEREBROS` (padrão `claude,codex,local`). Quem não está
  instalado é pulado; quem falha antes da primeira palavra (sem login, cota acabada) também, e
  fica de lado por um tempo — o Claude diz quando a cota renova; o Codex, 30 minutos.
- **Comando na mensagem:** `/claude`, `/codex` ou `/local` na frente escolhe quem responde, sem
  plano B — se falhar, o aviso diz isso em vez de outro responder sem pedir.
- **Sigilo:** mensagem com "privado", "confidencial", "sigiloso" ou "segredo" só vai pro local.
- **O que nunca vai pra nuvem:** memória privada, mensagem privada (no histórico ou como trecho
  antigo) e o resumo de uma conversa que tenha algo privado.
- **Extração de memória, vetores e resumo rodam sempre no modelo local**, qualquer que seja
  quem respondeu: leem o que é privado e não podem gastar cota.
- Os CLIs rodam sem ferramentas (`--tools ""` no Claude, `--sandbox read-only` no Codex), numa
  pasta vazia do Solis. O prompt vai pela entrada padrão, nunca pela linha de comando.
- Custo de tempo: cada mensagem sobe um processo do CLI. Medido aqui, o Claude Code levou 7,8 s
  do pedido à resposta curta — mais que o modelo local quando ele já está carregado.

O Codex foi integrado pela documentação: o CLI não estava instalado onde isto foi escrito.
Precisa ser conferido no notebook.

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

- Esquecer uma memória pela tela: a rota existe, o controle visual ainda não (sem referência).
- Lista de conversas antigas e botão de "nova conversa": as anteriores ficam no banco, mas
  ainda não há tela pra voltar a elas. Os dois precisam de referência visual.
- O Tauri não sobe este servidor sozinho. Hoje é `npm run backend` à mão; empacotar como
  sidecar fica pra quando o app for instalado de verdade.
- O preview na Vercel não tem servidor — lá a tela de Modelos mostra "Servidor do Solis
  desligado", e é o comportamento certo.
