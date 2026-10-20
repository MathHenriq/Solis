"""Servidor local do Solis.

Roda em 127.0.0.1 e só ali — é local-first, nada escuta na rede. O front fala
com ele por HTTP tanto no `npm run dev` quanto dentro do Tauri.

    npm run backend        # a partir da raiz do app
"""
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

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


class Mensagem(BaseModel):
    papel: Literal['pessoa', 'solis']
    texto: str


class Pedido(BaseModel):
    modelo: str
    mensagens: list[Mensagem]


@app.post('/conversa')
async def conversa(pedido: Pedido):
    try:
        fluxo = await ollama.conversar(pedido.modelo, [m.model_dump() for m in pedido.mensagens])
    except ollama.OllamaIndisponivel:
        return JSONResponse({'erro': 'ollama_indisponivel'}, status_code=503)
    except ollama.ModeloInexistente:
        return JSONResponse({'erro': 'modelo_inexistente'}, status_code=404)
    # Texto puro, pedaço a pedaço: o front só concatena. NDJSON seria mais uma
    # camada de parse pra carregar um campo só.
    return StreamingResponse(fluxo, media_type='text/plain; charset=utf-8')
