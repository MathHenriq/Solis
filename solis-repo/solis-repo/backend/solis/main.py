"""Servidor local do Solis.

Roda em 127.0.0.1 e só ali — é local-first, nada escuta na rede. O front fala
com ele por HTTP tanto no `npm run dev` quanto dentro do Tauri.

    npm run backend        # a partir da raiz do app
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from . import banco, memoria, ollama

app = FastAPI(title='Solis')

# As origens de onde o front é servido: o Vite em dev, e o WebView do Tauri
# (tauri://localhost no macOS/Linux, http://tauri.localhost no Windows).
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:1420', 'tauri://localhost', 'http://tauri.localhost'],
    allow_methods=['GET', 'POST', 'DELETE'],
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


@app.get('/conversas/atual')
async def conversa_atual():
    """A conversa mais recente, pra o app reabrir onde parou. Sem nenhuma ainda,
    id null — a primeira só é criada quando houver o que guardar."""
    conversa = banco.ultima_conversa()
    return {'id': conversa, 'mensagens': banco.mensagens(conversa) if conversa else []}


@app.post('/conversas')
async def criar_conversa():
    return {'id': banco.nova_conversa(), 'mensagens': []}


class Envio(BaseModel):
    modelo: str
    texto: str


@app.post('/conversas/{conversa}/mensagens')
async def enviar(conversa: int, envio: Envio):
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)

    # A mensagem da pessoa é guardada antes de perguntar ao modelo: o que ela
    # disse aconteceu, mesmo que o Ollama esteja fora. O aviso de erro não é
    # guardado — é estado do sistema naquele momento, não fala de ninguém.
    banco.adicionar(conversa, 'pessoa', envio.texto)
    historico = [{'papel': m['papel'], 'texto': m['texto']} for m in banco.mensagens(conversa)]

    try:
        fluxo = await ollama.conversar(envio.modelo, historico, banco.memorias())
    except (ollama.OllamaIndisponivel, ollama.ModeloInexistente) as e:
        # Sem modelo não há extração — mas um pedido de guardar não pode se perder
        # porque o Ollama estava fora. Guarda a mensagem como veio.
        if memoria.eh_pedido(envio.texto):
            memoria.guardar_pedido_cru(envio.texto, conversa)
        if isinstance(e, ollama.ModeloInexistente):
            return JSONResponse({'erro': 'modelo_inexistente'}, status_code=404)
        return JSONResponse({'erro': 'ollama_indisponivel'}, status_code=503)

    async def repassar_e_guardar():
        resposta = []
        try:
            async for pedaco in fluxo:
                resposta.append(pedaco)
                yield pedaco
        finally:
            # finally e não depois do laço: se a janela fechar no meio, o que já
            # chegou é guardado do mesmo jeito que apareceu na tela.
            if resposta:
                banco.adicionar(conversa, 'solis', ''.join(resposta))

    # Texto puro, pedaço a pedaço: o front só concatena. NDJSON seria mais uma
    # camada de parse pra carregar um campo só.
    #
    # O aprendizado roda como tarefa de fundo: só começa depois que a resposta
    # terminou de chegar, então a conversa não espera a segunda pergunta ao modelo.
    # O contexto são as duas falas antes da mensagem nova (a pergunta do Solis
    # que a mensagem talvez responda), não o histórico inteiro.
    return StreamingResponse(
        repassar_e_guardar(),
        media_type='text/plain; charset=utf-8',
        background=BackgroundTask(memoria.aprender, envio.modelo, conversa, envio.texto, historico[-3:-1]),
    )


@app.get('/memorias')
async def listar_memorias():
    return {'memorias': banco.memorias()}


@app.delete('/memorias/{id_}')
async def esquecer(id_: int):
    if not banco.apagar_memoria(id_):
        return JSONResponse({'erro': 'memoria_inexistente'}, status_code=404)
    return {'ok': True}
