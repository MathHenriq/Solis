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
