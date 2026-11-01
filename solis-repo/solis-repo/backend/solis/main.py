"""Servidor local do Solis.

Roda em 127.0.0.1 e só ali — é local-first, nada escuta na rede. O front fala
com ele por HTTP tanto no `npm run dev` quanto dentro do Tauri.

    npm run backend        # a partir da raiz do app
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import banco, busca, cerebros, memoria, ollama, resumo, roteador
from .etapas import Etapas

log = logging.getLogger('solis.main')


def _ligar_log() -> None:
    """O log do Solis no terminal do servidor e num arquivo ao lado do banco
    (solis.log): as etapas de cada resposta, com os tempos, ficam guardadas pra
    flagrar a próxima demora mesmo com o terminal fechado. Sem isto o uvicorn
    só mostra os avisos — os INFO do Solis sumiam."""
    raiz = logging.getLogger('solis')
    if raiz.handlers:
        return
    formato = logging.Formatter('%(asctime)s %(name)s %(message)s', '%H:%M:%S')
    arquivo = banco.caminho_padrao().parent / 'solis.log'
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    for saida in (
        logging.StreamHandler(),
        RotatingFileHandler(arquivo, maxBytes=1_000_000, backupCount=3, encoding='utf-8'),
    ):
        saida.setFormatter(formato)
        raiz.addHandler(saida)
    raiz.setLevel(logging.INFO)
    raiz.propagate = False


@asynccontextmanager
async def _vida(_app):
    # Na subida do servidor, e não na importação: os testes importam o app sem
    # subir, e não podem escrever log no %APPDATA% de verdade.
    _ligar_log()
    yield


app = FastAPI(title='Solis', lifespan=_vida)

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
    # O modelo local escolhido em Modelos locais. Vazio quando o Ollama está fora
    # — a conversa ainda pode ir pra um cérebro de nuvem.
    modelo: str = ''
    texto: str


# Referência forte às respostas em andamento: sem ela o coletor de lixo pode
# levar uma tarefa no meio.
_tarefas: set[asyncio.Task] = set()


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

    # O trabalho roda numa tarefa própria e o stream só repassa as etapas que
    # ela marca. Duas razões: a tela vê cada etapa ENQUANTO acontece (a busca,
    # o CLI subindo), e não só quando chega a primeira palavra; e fechar a
    # janela não corta nada — a resposta termina e é guardada inteira, e o
    # aprendizado roda do mesmo jeito.
    etapas = Etapas(conversa)
    tarefa = asyncio.create_task(_responder(etapas, envio.modelo, conversa, texto, ordem, forcado, mensagem_id))
    _tarefas.add(tarefa)
    tarefa.add_done_callback(_tarefas.discard)

    async def ndjson():
        async for evento in etapas.eventos():
            yield json.dumps(evento, ensure_ascii=False) + '\n'

    # NDJSON e não texto puro: junto do texto vão as etapas e o erro — que agora
    # chega com o stream já aberto, quando não dá mais pra mudar o status HTTP.
    return StreamingResponse(ndjson(), media_type='application/x-ndjson')


async def _responder(
    etapas: Etapas,
    modelo: str,
    conversa: int,
    texto: str,
    ordem: list[str],
    forcado: bool,
    mensagem_id: int,
) -> None:
    resposta_id = None
    try:
        # Só o fim da conversa vai inteiro; o começo vai como resumo. O que ficou
        # de fora não se perde: está no banco, e a busca traz de volta o trecho.
        resumido, historico, desde = resumo.para_o_modelo(conversa)
        memorias, trechos = await busca.contexto(texto, conversa, desde)
        etapas.marcar('memoria', memorias=len(memorias), trechos=len(trechos))

        try:
            fluxo, cerebro = await roteador.responder(
                ordem, modelo, conversa, historico, memorias, trechos, resumido, texto, etapas
            )
        except roteador.NinguemRespondeu as e:
            # Sem modelo nenhum não há extração — mas um pedido de guardar não
            # pode se perder por isso. Guarda a mensagem como veio.
            if memoria.eh_pedido(texto):
                memoria.guardar_pedido_cru(texto, conversa)
            etapas.erro(**_ninguem_respondeu(e, forcado))
            return

        resposta = []
        cortada = False
        try:
            async for pedaco in fluxo:
                resposta.append(pedaco)
                etapas.texto(pedaco)
        except Exception:
            log.exception('a resposta da conversa %s caiu no meio', conversa)
            cortada = True
        finally:
            # finally: nem o servidor desligando no meio perde o que já chegou.
            if resposta:
                resposta_id = banco.adicionar(conversa, 'solis', ''.join(resposta), cerebro=cerebro)
        etapas.marcar('fim', cerebro=cerebro, **({'cortada': True} if cortada else {}))

        try:
            await _depois(etapas, modelo, conversa, texto, historico, mensagem_id)
        except Exception:
            # Sem evento de erro: a resposta já está na tela, inteira, e um
            # aviso agora a trocaria pelo erro de uma etapa de fundo.
            log.exception('conversa %s: etapa depois da resposta falhou', conversa)
    except Exception:
        log.exception('conversa %s: erro no servidor', conversa)
        etapas.erro('servidor')
    finally:
        # As etapas vão pro banco com as de depois da resposta: a tela recolhida
        # conta todas, inclusive "memória guardada".
        if resposta_id is not None:
            banco.guardar_etapas(resposta_id, etapas.lista)
        etapas.encerrar()


async def _depois(etapas: Etapas, modelo: str, conversa: int, texto: str, historico: list[dict], mensagem_id: int):
    """Depois que a resposta terminou de chegar, nesta ordem: aprender (extrair
    memórias da mensagem), indexar (vetorizar o que entrou, inclusive a memória
    que acabou de nascer) e resumir (se a conversa passou do lote). A tela já
    liberou a conversa no `fim`; estas etapas chegam pelo mesmo stream, que só
    fecha depois delas. O contexto do aprendizado são as duas falas antes da
    mensagem nova (a pergunta do Solis que ela talvez responda), não o histórico
    inteiro.

    Os três rodam SEMPRE no modelo local, qualquer que seja o cérebro que
    respondeu: leem tudo, inclusive o que é privado, e não podem gastar cota."""
    novas = await memoria.aprender(modelo, conversa, texto, historico[-3:-1], mensagem_id)
    etapas.marcar('aprendizado', novas=novas or 0)
    etapas.marcar('indexacao', vetores=await busca.indexar_pendentes())
    etapas.marcar('resumo', resumiu=bool(await resumo.resumir(modelo, conversa)))


def _ninguem_respondeu(e: roteador.NinguemRespondeu, forcado: bool) -> dict:
    """O erro diz QUEM falhou, porque o conserto muda: ligar o Ollama, instalar
    um modelo, ou olhar o login e a cota de um CLI."""
    if forcado and e.ordem != ['local']:
        [nome] = e.ordem
        return {'erro': 'cerebro_indisponivel', 'cerebro': cerebros.NOMES[nome]}
    if isinstance(e.erros.get('local'), ollama.ModeloInexistente):
        return {'erro': 'modelo_inexistente'}
    return {'erro': 'ollama_indisponivel'}


@app.get('/memorias')
async def listar_memorias():
    return {'memorias': banco.memorias()}


@app.delete('/memorias/{id_}')
async def esquecer(id_: int):
    if not banco.apagar_memoria(id_):
        return JSONResponse({'erro': 'memoria_inexistente'}, status_code=404)
    return {'ok': True}
