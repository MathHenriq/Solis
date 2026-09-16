# Backend do Solis

Processo auxiliar local. Fala com o Ollama pela API HTTP e serve três rotas pro
frontend. Roda em `127.0.0.1:8000` — não é serviço de rede.

## Rodar

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # uma vez
pip install -r requirements.txt                      # uma vez
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

O Ollama precisa estar de pé (`ollama serve`) com ao menos um modelo de
conversa instalado (`ollama pull qwen3:8b`). Sem ele o app continua abrindo: o
erro aparece como mensagem dentro da conversa, não como tela quebrada.

## Rotas

| Rota      | O que faz                                                        |
|-----------|------------------------------------------------------------------|
| `GET /health` | `{status, ollama: "online"\|"offline"}`. **Sempre 200**, mesmo com o Ollama parado. |
| `GET /models` | Modelos instalados + qual é o default. 503 se o Ollama não atender. |
| `POST /chat`  | `{message, model?, history?}` → `{response, model, eval_count, total_duration_ms}`. |

O system prompt é montado aqui (`config.SYSTEM_PROMPT`) e o campo `role` do
histórico não aceita `"system"` — o frontend manda o que foi dito, nunca quem o
Solis é.

Sem modelo informado, o backend autodetecta: o primeiro instalado que não seja
de embedding.

## Ajustes por ambiente

| Variável | Padrão | Pra quê |
|---|---|---|
| `SOLIS_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama em outra porta |
| `SOLIS_MODELO` | *(vazio)* | Fixar o modelo em vez de autodetectar |
| `SOLIS_TIMEOUT_CONEXAO` | `5` | Segundos pra conectar |
| `SOLIS_TIMEOUT_LEITURA` | `180` | Segundos pra gerar |
| `SOLIS_SYSTEM_PROMPT` | *(o de `config.py`)* | Trocar o prompt sem editar código |
| `SOLIS_PORT` | `8000` | Porta do backend (mudar aqui exige mudar `BASE_URL` em `src/lib/solisApi.ts`) |

## Qwen3 e modelos "thinking"

A resposta vem com o raciocínio embrulhado em `<think>…</think>`. O gateway
manda `think: false` pro Ollama e, como rede de proteção (nem todo modelo
respeita o parâmetro), remove os blocos do texto antes de devolver — inclusive
o bloco aberto e nunca fechado, que aparece quando a geração estoura o limite
de tokens no meio do raciocínio.
