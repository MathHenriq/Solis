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

O modelo da Conversa é o marcado "Em uso" em Modelos locais. Clicar numa linha troca; sem
escolha, vale o primeiro modelo que conversa (embeddings nunca entra).

As conversas ficam num SQLite em `%APPDATA%\Solis\solis.db`. O app reabre a mais recente;
digitar `/nova` na Conversa começa outra (a anterior continua guardada).

## Testes

```powershell
python -m pytest
```

Não precisam do Ollama instalado — as respostas dele são simuladas.

## O que ainda não existe

- Lista de conversas antigas e botão de "nova conversa": as anteriores ficam no banco, mas
  ainda não há tela pra voltar a elas. Os dois precisam de referência visual.
- O Tauri não sobe este servidor sozinho. Hoje é `npm run backend` à mão; empacotar como
  sidecar fica pra quando o app for instalado de verdade.
- O preview na Vercel não tem servidor — lá a tela de Modelos mostra "Servidor do Solis
  desligado", e é o comportamento certo.
