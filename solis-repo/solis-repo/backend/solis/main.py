"""Servidor local do Solis.

Roda em 127.0.0.1 e só ali — é local-first, nada escuta na rede. O front fala
com ele por HTTP tanto no `npm run dev` quanto dentro do Tauri.

    npm run backend        # a partir da raiz do app
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import BackgroundTasks, FastAPI
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
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
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


def _cerebros() -> dict:
    """A lista de Configurações → Cérebros: a ordem, quem está ligado, e o que
    impede cada um de responder agora (CLI ausente, pausa depois de falhar)."""
    return {
        'cerebros': [
            {
                **p,
                'rotulo': cerebros.NOMES[p['nome']],
                # O local depende do Ollama, que a tela de Modelos já mostra.
                'instalado': p['nome'] == 'local' or cerebros.instalado(p['nome']),
                'pausa': None if p['nome'] == 'local' else cerebros.pausa(p['nome']),
            }
            for p in roteador.preferencia()
        ]
    }


@app.get('/cerebros')
async def listar_cerebros():
    return _cerebros()


class Preferencia(BaseModel):
    nome: str
    ligado: bool


class Ordem(BaseModel):
    ordem: list[Preferencia]


@app.put('/cerebros')
async def ordenar_cerebros(ordem: Ordem):
    try:
        roteador.guardar_preferencia([p.model_dump() for p in ordem.ordem])
    except ValueError:
        return JSONResponse({'erro': 'ordem_invalida'}, status_code=400)
    return _cerebros()


@app.post('/cerebros/{nome}/retomar')
async def retomar_cerebro(nome: str):
    if nome not in cerebros.NOMES:
        return JSONResponse({'erro': 'cerebro_inexistente'}, status_code=404)
    cerebros.retomar(nome)
    return _cerebros()


@app.get('/conversas/atual')
async def conversa_atual():
    """A conversa mais recente, pra o app reabrir onde parou. Sem nenhuma ainda,
    id null — a primeira só é criada quando houver o que guardar."""
    conversa = banco.ultima_conversa()
    return {'id': conversa, 'mensagens': banco.mensagens(conversa) if conversa else []}


@app.get('/conversas')
async def listar_conversas(q: str = ''):
    """A lista do painel de conversas; `q` filtra pelo título e pelo texto."""
    return {'conversas': banco.conversas(q)}


@app.get('/conversas/{conversa}')
async def abrir_conversa(conversa: int):
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    return {'id': conversa, 'mensagens': banco.mensagens(conversa)}


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
    """Depois que a resposta terminou de chegar, nesta ordem: dar título (se a
    conversa ainda não tem — é rápido, e a lista do painel troca a primeira
    fala por ele), aprender (extrair memórias da mensagem), indexar (vetorizar
    o que entrou, inclusive a memória que acabou de nascer) e resumir (se a
    conversa passou do lote). A tela já
    liberou a conversa no `fim`; estas etapas chegam pelo mesmo stream, que só
    fecha depois delas. O contexto do aprendizado são as duas falas antes da
    mensagem nova (a pergunta do Solis que ela talvez responda), não o histórico
    inteiro.

    Todos rodam SEMPRE no modelo local, qualquer que seja o cérebro que
    respondeu: leem tudo, inclusive o que é privado, e não podem gastar cota.
    E no modelo de fundo (MODELO_FUNDO), não no da conversa."""
    modelo = await _modelo_de_fundo(modelo)
    if titulo := await resumo.titular(modelo, conversa):
        etapas.marcar('titulo', titulo=titulo)
    novas = await memoria.aprender(modelo, conversa, texto, historico[-3:-1], mensagem_id)
    etapas.marcar('aprendizado', novas=len(novas or []), textos=novas or [], modelo=modelo)
    etapas.marcar('indexacao', vetores=await busca.indexar_pendentes())
    etapas.marcar('resumo', resumiu=bool(await resumo.resumir(modelo, conversa)))


# O modelo das tarefas de fundo: título, aprendizado e resumo. Fixo, e não o da
# conversa, porque elas pedem um modelo que siga instrução — medido em
# 08/11/2026: no aprendizado o qwen3:8b acertou 12 de 12 casos e o
# llama3.2:3b, 6; no resumo o llama copiou a conversa em vez de resumir (ver
# backend/README.md → Raciocínio). Trocar não precisa de código:
# SOLIS_MODELO_FUNDO=outro:modelo.
#
# PROVISÓRIO: o qwen3:8b ocupa 5,2 GB dos 8 da placa, e sobe pra GPU a cada
# mensagem — com um jogo aberto, estoura a VRAM. Questão em aberto em
# docs/ESCOPO.md → "Questões pra depois do Solis completo".
MODELO_FUNDO = os.environ.get('SOLIS_MODELO_FUNDO', 'qwen3:8b')


async def _modelo_de_fundo(modelo_da_conversa: str) -> str:
    """O MODELO_FUNDO se estiver instalado; senão o da conversa, que é o que
    havia antes — melhor uma tarefa de fundo fraca que nenhuma."""
    try:
        instalados = await ollama.instalados()
    except ollama.OllamaIndisponivel:
        return modelo_da_conversa
    return MODELO_FUNDO if MODELO_FUNDO in instalados else modelo_da_conversa


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
async def listar_memorias(q: str = ''):
    """Todas as que valem, ou as que batem com a busca `q` (texto e tema)."""
    return {'memorias': banco.buscar_memorias(q) if q.strip() else banco.memorias()}


class Correcao(BaseModel):
    texto: str


@app.patch('/memorias/{id_}')
async def corrigir(id_: int, correcao: Correcao, fundo: BackgroundTasks):
    texto = ' '.join(correcao.texto.split())
    if not texto:
        return JSONResponse({'erro': 'texto_vazio'}, status_code=400)
    memoria = banco.corrigir_memoria(id_, texto)
    if memoria is None:
        return JSONResponse({'erro': 'memoria_inexistente'}, status_code=404)
    # O vetor novo, pra busca por significado achar o texto corrigido.
    fundo.add_task(busca.indexar_pendentes)
    return {'memoria': memoria}


@app.delete('/memorias/{id_}')
async def esquecer(id_: int):
    if not banco.apagar_memoria(id_):
        return JSONResponse({'erro': 'memoria_inexistente'}, status_code=404)
    return {'ok': True}
