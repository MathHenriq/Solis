"""Servidor local do Solis.

Roda em 127.0.0.1 e só ali — é local-first, nada escuta na rede. O front fala
com ele por HTTP tanto no `npm run dev` quanto dentro do Tauri.

    npm run backend        # a partir da raiz do app
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.background import BackgroundTasks

from . import banco, busca, cerebros, memoria, ollama, resumo, roteador

app = FastAPI(title='Solis')

# As origens de onde o front é servido: o Vite em dev, e o WebView do Tauri
# (tauri://localhost no macOS/Linux, http://tauri.localhost no Windows).
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:1420', 'tauri://localhost', 'http://tauri.localhost'],
    allow_methods=['GET', 'POST', 'DELETE'],
    allow_headers=['*'],
    # Sem isto o navegador esconde do front quem respondeu.
    expose_headers=['X-Solis-Cerebro'],
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
    # O modelo local escolhido em Modelos locais. Vazio quando o Ollama está fora
    # — a conversa ainda pode ir pra um cérebro de nuvem.
    modelo: str = ''
    texto: str


@app.post('/conversas/{conversa}/mensagens')
async def enviar(conversa: int, envio: Envio):
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)

    # "/claude ..." escolhe quem responde; o comando não faz parte do que foi dito.
    texto, ordem, forcado = roteador.escolher(envio.texto)

    # A mensagem da pessoa é guardada antes de perguntar ao modelo: o que ela
    # disse aconteceu, mesmo que nenhum modelo responda. O aviso de erro não é
    # guardado — é estado do sistema naquele momento, não fala de ninguém.
    mensagem_id = banco.adicionar(conversa, 'pessoa', texto, privada=memoria.eh_privado(texto))
    # Só o fim da conversa vai inteiro; o começo vai como resumo. O que ficou de
    # fora não se perde: está no banco, e a busca traz de volta o trecho exato.
    resumido, historico, desde = resumo.para_o_modelo(conversa)
    memorias, trechos = await busca.contexto(texto, conversa, desde)

    try:
        fluxo, cerebro = await roteador.responder(
            ordem, envio.modelo, conversa, historico, memorias, trechos, resumido, texto
        )
    except roteador.NinguemRespondeu as e:
        # Sem modelo nenhum não há extração — mas um pedido de guardar não pode
        # se perder por isso. Guarda a mensagem como veio.
        if memoria.eh_pedido(texto):
            memoria.guardar_pedido_cru(texto, conversa)
        return _ninguem_respondeu(e, forcado)

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
                banco.adicionar(conversa, 'solis', ''.join(resposta), cerebro=cerebro)

    # Texto puro, pedaço a pedaço: o front só concatena. NDJSON seria mais uma
    # camada de parse pra carregar um campo só.
    #
    # Depois que a resposta terminou de chegar, em segundo plano e nesta ordem:
    # aprender (extrair memórias da mensagem), indexar (vetorizar o que entrou,
    # inclusive a memória que acabou de nascer) e resumir (se a conversa passou
    # do lote). A conversa não espera nenhum dos três. O contexto do aprendizado
    # são as duas falas antes da mensagem nova (a pergunta do Solis que ela
    # talvez responda), não o histórico inteiro.
    #
    # Os três rodam SEMPRE no modelo local, qualquer que seja o cérebro que
    # respondeu: leem tudo, inclusive o que é privado, e não podem gastar cota.
    depois = BackgroundTasks()
    depois.add_task(memoria.aprender, envio.modelo, conversa, texto, historico[-3:-1], mensagem_id)
    depois.add_task(busca.indexar_pendentes)
    depois.add_task(resumo.resumir, envio.modelo, conversa)
    return StreamingResponse(
        repassar_e_guardar(),
        media_type='text/plain; charset=utf-8',
        headers={'X-Solis-Cerebro': cerebro},
        background=depois,
    )


def _ninguem_respondeu(e: roteador.NinguemRespondeu, forcado: bool) -> JSONResponse:
    """O erro diz QUEM falhou, porque o conserto muda: ligar o Ollama, instalar
    um modelo, ou olhar o login e a cota de um CLI."""
    if forcado and e.ordem != ['local']:
        [nome] = e.ordem
        return JSONResponse({'erro': 'cerebro_indisponivel', 'cerebro': cerebros.NOMES[nome]}, status_code=502)
    if isinstance(e.erros.get('local'), ollama.ModeloInexistente):
        return JSONResponse({'erro': 'modelo_inexistente'}, status_code=404)
    return JSONResponse({'erro': 'ollama_indisponivel'}, status_code=503)


@app.get('/memorias')
async def listar_memorias():
    return {'memorias': banco.memorias()}


@app.delete('/memorias/{id_}')
async def esquecer(id_: int):
    if not banco.apagar_memoria(id_):
        return JSONResponse({'erro': 'memoria_inexistente'}, status_code=404)
    return {'ok': True}
