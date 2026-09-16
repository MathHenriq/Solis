"""Configuração do backend do Solis.

Tudo aqui é constante de processo, lida do ambiente uma vez na importação. Nada
de arquivo de config em disco por enquanto: o backend roda na mesma máquina que
o app, sem deploy e sem ambiente remoto pra diferenciar.
"""

import os

# --- Ollama ---------------------------------------------------------------

# 127.0.0.1 e não localhost de propósito: em máquina com IPv6 ativo o
# `localhost` resolve pra ::1 primeiro, o Ollama escuta em 127.0.0.1 e a
# primeira tentativa de conexão morre em timeout antes do fallback.
OLLAMA_URL = os.environ.get("SOLIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

# Modelo fixo, quando o usuário quiser um. Vazio = autodetecta o que estiver
# instalado (ver ModelGateway.modelo_padrao).
MODELO_PADRAO = os.environ.get("SOLIS_MODELO", "").strip() or None

# Conectar é rápido ou não vai acontecer — se o Ollama não está de pé, o erro
# tem que voltar em segundos, não depois de meio minuto de tela parada
# (ERROR_STATES.md §2: o símbolo nunca fica travado em `thinking`).
# Ler é outra história: um modelo local gerando texto longo passa fácil de 30s,
# e cortar isso seria transformar resposta lenta em erro falso.
TIMEOUT_CONEXAO = float(os.environ.get("SOLIS_TIMEOUT_CONEXAO", "5"))
TIMEOUT_LEITURA = float(os.environ.get("SOLIS_TIMEOUT_LEITURA", "180"))

# Modelos de embedding aparecem no /api/tags junto com os de conversa e não
# sabem conversar. Na autodetecção eles são descartados por nome.
MARCAS_DE_EMBEDDING = ("embed", "embedding", "bge-", "gte-", "minilm")

# --- Prompt ---------------------------------------------------------------

# O system prompt mora AQUI e só aqui. O frontend manda a mensagem do usuário e
# o histórico; quem monta a conversa que vai pro modelo é o backend. Assim o
# comportamento do Solis não depende de qual cliente chamou a API, e um turno
# com role "system" vindo de fora é descartado (ver main.py).
SYSTEM_PROMPT = os.environ.get("SOLIS_SYSTEM_PROMPT") or (
    "Você é o Solis, assistente pessoal local do Matheus. Roda inteiro na "
    "máquina dele: nada do que vocês conversam sai daqui.\n"
    "\n"
    "Como você fala:\n"
    "- Português do Brasil, direto, na segunda pessoa.\n"
    "- Frase curta e verbo ativo. Sem ponto de exclamação.\n"
    "- Não se desculpa, não bajula, não enche linguiça antes de responder.\n"
    "- Não sabe é 'não sei' — seguido do que dá pra fazer a respeito.\n"
    "- Diz o que aconteceu e o que fazer a seguir, nessa ordem.\n"
    "\n"
    "Formato: texto corrido em parágrafos curtos. Lista só quando os itens são "
    "mesmo uma lista, com '- ' no início da linha. Sem títulos em markdown, sem "
    "negrito decorativo, sem emoji."
)

# --- CORS -----------------------------------------------------------------

# Três origens, três jeitos de abrir o mesmo frontend:
#   5173  → `vite dev` no default do Vite
#   1420  → `vite dev` com a porta fixa que o Tauri exige (vite.config.ts)
#   tauri://localhost e https://tauri.localhost → o app empacotado, servindo o
#     bundle de dentro do webview (o esquema muda conforme a plataforma:
#     tauri:// no macOS e Linux, https://tauri.localhost no Windows).
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "tauri://localhost",
    "https://tauri.localhost",
]

# --- Servidor -------------------------------------------------------------

HOST = os.environ.get("SOLIS_HOST", "127.0.0.1")
PORT = int(os.environ.get("SOLIS_PORT", "8000"))

# Quantos turnos do histórico o backend aceita do cliente. O frontend manda ~6;
# o teto existe pra que um cliente distraído não empurre a conversa inteira a
# cada mensagem e estoure a janela de contexto do modelo.
HISTORICO_MAX = int(os.environ.get("SOLIS_HISTORICO_MAX", "12"))
