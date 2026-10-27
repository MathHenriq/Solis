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
| `POST /conversas/{id}/mensagens` | `{"modelo", "texto"}` → guarda a mensagem, manda o histórico ao Ollama e devolve a resposta em texto puro, pedaço a pedaço. A resposta é guardada no fim, mesmo se cortada no meio. `503` sem Ollama, `404` se o modelo ou a conversa não existirem |
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

**Privada.** O modelo marca como privada o que for saúde, senha, finanças ou documento
pessoal; e se a mensagem disser "privado", "confidencial", "sigiloso" ou "segredo", tudo que
sair dela é privado, concorde o modelo ou não. Hoje todo modelo é local, então nada sai de
qualquer jeito; a marca vale quando modelos de nuvem entrarem. Atenção: privada não é
criptografada — está em texto puro no `solis.db`.

## Busca por significado

Cada memória e cada mensagem vira um vetor com o `nomic-embed-text` (precisa estar instalado
no Ollama). A cada mensagem nova, entram no pedido ao modelo:

- as memórias: todas, até 30; acima disso, as 12 mais parecidas com a mensagem mais as 5
  mais recentes;
- até 5 trechos de conversas antigas parecidos com a mensagem;
- as últimas 20 mensagens da conversa aberta.

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
