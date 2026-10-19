"""Servidor local do Solis.

Roda em 127.0.0.1 e só ali — é local-first, nada escuta na rede. O front fala
com ele por HTTP tanto no `npm run dev` quanto dentro do Tauri.

    npm run backend        # a partir da raiz do app
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import ollama

app = FastAPI(title='Solis')

# As origens de onde o front é servido: o Vite em dev, e o WebView do Tauri
# (tauri://localhost no macOS/Linux, http://tauri.localhost no Windows).
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:1420', 'tauri://localhost', 'http://tauri.localhost'],
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)


@app.get('/saude')
async def saude():
    return {'ok': True}


@app.get('/modelos')
async def modelos():
    try:
        return {'modelos': await ollama.listar_modelos()}
    except ollama.OllamaIndisponivel:
        # 503 e não 500: o servidor do Solis está bem, quem falta é a dependência.
        # O front usa essa diferença pra dizer QUEM está fora do ar.
        return JSONResponse({'erro': 'ollama_indisponivel'}, status_code=503)
