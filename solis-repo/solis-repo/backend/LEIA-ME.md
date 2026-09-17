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
| `POST /chat`  | `{message, model?, history?, use_knowledge?}` → `{response, model, eval_count, total_duration_ms, sources, used_knowledge}`. |
| `POST /knowledge/documents` | Upload multipart (campo `file`). Devolve o documento com `status`. |
| `GET /knowledge/documents` | Lista os documentos. |
| `DELETE /knowledge/documents/{id}` | Remove o documento e, em cascata, seus trechos. 404 se não existir. |
| `POST /knowledge/search` | `{query, k?}` → consulta FTS5 gerada, chunks com score e `passou_no_gate`. Depuração. |

As rotas `/knowledge/*` **não dependem do Ollama** — indexar é trabalho de
SQLite. Dá pra montar o acervo com o motor desligado.

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
| `SOLIS_DB` | `~/.solis/solis.db` | Onde fica o banco (os testes apontam pra um temporário) |
| `SOLIS_RAG_K` | `5` | Quantos trechos a busca devolve |
| `SOLIS_RAG_MINIMO` | `0.3` | Cobertura mínima de termos pro contexto ser usado |
| `SOLIS_RAG_MAX_CHARS` | `6000` | Teto do bloco de trechos no system prompt |
| `SOLIS_MAX_UPLOAD_MB` | `25` | Teto do arquivo enviado |

## Base de conhecimento

Arquivo → texto (`ingest.extrair_texto`) → normalização → chunks
(`rag.chunk_text`) → SQLite + índice FTS5. A busca é léxica (BM25), sem
embeddings: num acervo pessoal ela acerta o bastante, e um modelo de embedding
local custaria RAM e um índice vetorial a mais pra manter. A coluna `embedding`
já existe em `chunks` pra quando isso mudar.

No `/chat`, o caminho é `build_fts_query` → `store.buscar` → `gate_relevancia`
→ `build_context`. O gate mede **cobertura de termos** (que fração das palavras
da pergunta aparece no melhor trecho), não limiar de BM25 — o score do BM25 não
é normalizado e muda conforme o acervo cresce. Reprovando o gate, a conversa
segue sem contexto.

O contexto entra **no system prompt** (`rag.PROMPT_RAG`), nunca colado na
pergunta: o histórico não pode carregar a mensagem adulterada, e o modelo não
pode tratar o conteúdo do documento como coisa que o Matheus escreveu.

PDF escaneado é imagem, não texto: ele entra com `status: 'erro'` e a mensagem
dizendo que precisa de OCR. Não há OCR embutido.

## Qwen3 e modelos "thinking"

A resposta vem com o raciocínio embrulhado em `<think>…</think>`. O gateway
manda `think: false` pro Ollama e, como rede de proteção (nem todo modelo
respeita o parâmetro), remove os blocos do texto antes de devolver — inclusive
o bloco aberto e nunca fechado, que aparece quando a geração estoura o limite
de tokens no meio do raciocínio.
