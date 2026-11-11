"""Servidor local do Solis.

Roda em 127.0.0.1 e só ali — é local-first, nada escuta na rede. O front fala
com ele por HTTP tanto no `npm run dev` quanto dentro do Tauri.

    npm run backend        # a partir da raiz do app
"""
import asyncio
import contextlib
import json
import logging
import os
import mimetypes
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

import httpx
from fastapi import BackgroundTasks, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from . import apis, ativacao, avisos, banco, busca, cerebros, conhecimento, fala, memoria, ocr, ollama, pc, rapidas, resumo, roteador, voz
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
    # Começa a indexar o que estiver pendente — inclusive refazer todos os
    # vetores, se o modelo de embeddings mudou (busca.conferir_modelo).
    indexacao = asyncio.create_task(busca.indexar_se_livre())
    # E a ler as páginas escaneadas que ficaram na fila quando o servidor caiu.
    leitura = asyncio.create_task(ocr.ler_se_livre())
    # E a vigiar a Agenda e as Tarefas: o aviso do Windows na hora.
    vigia = asyncio.create_task(avisos.vigiar())
    # E a tirar o Whisper da memória quando ninguém fala há um tempo.
    ouvido = asyncio.create_task(voz.vigiar())
    boca = asyncio.create_task(fala.vigiar())
    yield
    boca.cancel()
    indexacao.cancel()
    leitura.cancel()
    vigia.cancel()
    ouvido.cancel()


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
    def um(p: dict) -> dict:
        nome = p['nome']
        tipo = 'local' if nome == 'local' else 'cli' if nome in cerebros.CLIS else 'api'
        item = {
            **p,
            'rotulo': cerebros.NOMES[nome],
            'tipo': tipo,
            # O local depende do Ollama, que a tela de Modelos já mostra. Pra
            # API, "instalado" é ter uma chave guardada.
            'instalado': tipo == 'local' or cerebros.instalado(nome),
            'pausa': None if tipo == 'local' else cerebros.pausa(nome),
        }
        if tipo == 'api':
            # A chave nunca sai daqui: a tela só sabe que ela existe.
            item.update(modelo=apis.modelo(nome), site=apis.PROVEDORES[nome]['site'], nota=apis.PROVEDORES[nome]['nota'])
        return item

    return {'cerebros': [um(p) for p in roteador.preferencia()]}


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


class AjustesClaude(BaseModel):
    modelo: str | None = None
    esforco: str | None = None


@app.get('/cerebros/claude/ajustes')
async def ler_ajustes_claude():
    """O modelo do Claude e o quanto ele pensa (None = o padrão da conta)."""
    from . import agente
    return {**agente.ajustes(), 'modelos': list(agente.MODELOS), 'esforcos': list(agente.ESFORCOS)}


@app.put('/cerebros/claude/ajustes')
async def guardar_ajustes_claude(corpo: AjustesClaude):
    from . import agente
    try:
        agente.guardar_ajustes(corpo.modelo, corpo.esforco)
    except ValueError as e:
        return JSONResponse({'erro': f'{e}_invalido'}, status_code=400)
    return await ler_ajustes_claude()


@app.post('/cerebros/{nome}/retomar')
async def retomar_cerebro(nome: str):
    if nome not in cerebros.NOMES:
        return JSONResponse({'erro': 'cerebro_inexistente'}, status_code=404)
    cerebros.retomar(nome)
    return _cerebros()


class Chave(BaseModel):
    chave: str


@app.put('/cerebros/{nome}/chave')
async def guardar_chave(nome: str, corpo: Chave):
    """Confere a chave no serviço, escolhe o modelo, guarda selado e liga o
    cérebro — quem colou uma chave quer usar."""
    if nome not in apis.PROVEDORES:
        return JSONResponse({'erro': 'cerebro_inexistente'}, status_code=404)
    chave = corpo.chave.strip()
    if not chave:
        return JSONResponse({'erro': 'chave_vazia'}, status_code=400)
    try:
        await apis.guardar_chave(nome, chave)
    except apis.ChaveRecusada:
        return JSONResponse({'erro': 'chave_recusada'}, status_code=400)
    except apis.ProvedorFora as e:
        return JSONResponse({'erro': 'provedor_fora', 'detalhe': str(e)}, status_code=502)
    cerebros.retomar(nome)
    roteador.ligar(nome, True)
    return _cerebros()


@app.delete('/cerebros/{nome}/chave')
async def apagar_chave(nome: str):
    if nome not in apis.PROVEDORES:
        return JSONResponse({'erro': 'cerebro_inexistente'}, status_code=404)
    apis.apagar_chave(nome)
    roteador.ligar(nome, False)
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


# O modelo local da última mensagem: é o que a escuta aquece quando ouve "Solis".
_ultimo_modelo: str | None = None


class Envio(BaseModel):
    # O modelo local escolhido em Modelos locais. Vazio quando o Ollama está fora
    # — a conversa ainda pode ir pra um cérebro de nuvem.
    modelo: str = ''
    texto: str
    # Veio pela voz e a resposta vai ser falada: resposta curta (ollama.VOZ).
    voz: bool = False
    # Editar uma mensagem ou refazer a resposta: a conversa volta a antes da
    # mensagem `desde` (da pessoa), e esta vai no lugar dela.
    desde: int | None = None
    # Os caminhos devolvidos por POST /anexos.
    anexos: list[str] = []


# Referência forte às respostas em andamento: sem ela o coletor de lixo pode
# levar uma tarefa no meio.
_tarefas: set[asyncio.Task] = set()

# A resposta em andamento de cada conversa, pra o Matheus poder parar no meio.
_paradas: dict[int, asyncio.Event] = {}


@app.post('/conversas/{conversa}/mensagens')
async def enviar(conversa: int, envio: Envio):
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)

    if envio.desde is not None:
        if conversa in _paradas:
            return JSONResponse({'erro': 'respondendo'}, status_code=409)
        if not banco.mensagem_da_pessoa(conversa, envio.desde):
            return JSONResponse({'erro': 'mensagem_inexistente'}, status_code=404)
        banco.apagar_desde(conversa, envio.desde)
        # A sessão do Claude viu o que foi apagado: a próxima começa outra,
        # com o histórico de agora.
        banco.esquecer_sessao_claude(conversa)

    anexos = []
    for caminho in envio.anexos:
        anexo = _anexo(caminho)
        if anexo is None:
            return JSONResponse({'erro': 'anexo_inexistente'}, status_code=400)
        anexos.append(anexo)

    # "/claude ..." escolhe quem responde; o comando não faz parte do que foi dito.
    texto, ordem, forcado = roteador.escolher(envio.texto, voz=envio.voz)
    if anexos and not forcado:
        # Com anexo, o Claude primeiro: ele lê texto, PDF e imagem; o modelo
        # local não enxerga imagem nem tem a pasta de trabalho.
        ordem = sorted(ordem, key=lambda c: c != 'claude')
    global _ultimo_modelo
    if envio.modelo and envio.modelo != _ultimo_modelo:
        _ultimo_modelo = envio.modelo
        banco.guardar_ajuste('modelo_local', envio.modelo)

    # A mensagem da pessoa é guardada antes de perguntar ao modelo: o que ela
    # disse aconteceu, mesmo que nenhum modelo responda. O aviso de erro não é
    # guardado — é estado do sistema naquele momento, não fala de ninguém.
    mensagem_id = banco.adicionar(conversa, 'pessoa', texto, privada=memoria.eh_privado(texto))
    if anexos:
        banco.guardar_anexos(mensagem_id, anexos)

    # O trabalho roda numa tarefa própria e o stream só repassa as etapas que
    # ela marca. Duas razões: a tela vê cada etapa ENQUANTO acontece (a busca,
    # o CLI subindo), e não só quando chega a primeira palavra; e fechar a
    # janela não corta nada — a resposta termina e é guardada inteira, e o
    # aprendizado roda do mesmo jeito.
    etapas = Etapas(conversa)
    # O id da mensagem guardada: é por ele que a tela edita ou refaz depois.
    etapas.marcar('guardada', pessoa=mensagem_id)
    parar = _paradas[conversa] = asyncio.Event()
    tarefa = asyncio.create_task(
        _responder(etapas, envio.modelo, conversa, texto, ordem, forcado, mensagem_id, envio.voz, anexos)
    )
    _tarefas.add(tarefa)
    tarefa.add_done_callback(_tarefas.discard)
    tarefa.add_done_callback(lambda _: _paradas.pop(conversa, None) if _paradas.get(conversa) is parar else None)

    async def ndjson():
        async for evento in etapas.eventos():
            yield json.dumps(evento, ensure_ascii=False) + '\n'

    # NDJSON e não texto puro: junto do texto vão as etapas e o erro — que agora
    # chega com o stream já aberto, quando não dá mais pra mudar o status HTTP.
    return StreamingResponse(ndjson(), media_type='application/x-ndjson')


# — Anexos ————————————————————————————————————————————————————————————————————————

ANEXO_MAX = 50 * 1024 * 1024


def _pasta_anexos() -> Path:
    from . import agente
    return agente._pasta_trabalho().resolve() / 'anexos'


def _anexo(caminho: str) -> dict | None:
    """O anexo que POST /anexos guardou — só dentro da pasta de anexos."""
    try:
        p = Path(caminho).resolve()
    except OSError:
        return None
    if not p.is_file() or not p.is_relative_to(_pasta_anexos()):
        return None
    nome = p.name.split('-', 1)[1] if '-' in p.name else p.name
    return {'nome': nome, 'caminho': str(p), 'tipo': mimetypes.guess_type(nome)[0] or 'application/octet-stream',
            'tamanho': p.stat().st_size}


@app.post('/anexos')
async def anexar(request: Request, nome: str):
    """O arquivo cru no corpo (como em /conhecimento), o nome na query. Vai pra
    pasta de trabalho, em anexos/AAAA-MM-DD/, e o caminho volta pra tela, que o
    manda com a mensagem."""
    dados = await request.body()
    if not dados:
        return JSONResponse({'erro': 'vazio'}, status_code=400)
    if len(dados) > ANEXO_MAX:
        return JSONResponse({'erro': 'grande_demais', 'max': ANEXO_MAX}, status_code=413)
    seguro = re.sub(r'[^\w.\- ]', '_', Path(nome).name).strip()[:120] or 'arquivo'
    pasta = _pasta_anexos() / date.today().isoformat()
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f'{uuid.uuid4().hex[:8]}-{seguro}'
    await asyncio.to_thread(caminho.write_bytes, dados)
    return _anexo(str(caminho))


@app.post('/conversas/{conversa}/parar')
async def parar_resposta(conversa: int):
    """O Matheus parou a resposta no meio. O que já chegou fica guardado."""
    parar = _paradas.get(conversa)
    if parar is None:
        return JSONResponse({'erro': 'nada_respondendo'}, status_code=404)
    parar.set()
    return {'ok': True}


async def _ate_parar(aguardavel, parar: asyncio.Event | None):
    """(resultado, False) — ou (None, True) se o Matheus parou antes. Parar
    cancela o que estava esperando: o modelo, o CLI ou a sessão do Claude, que
    é interrompida (agente._interromper)."""
    tarefa = asyncio.ensure_future(aguardavel)
    if parar is None:
        return await tarefa, False
    espera = asyncio.ensure_future(parar.wait())
    try:
        await asyncio.wait({tarefa, espera}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        espera.cancel()
    if tarefa.done():
        return tarefa.result(), False
    tarefa.cancel()
    with contextlib.suppress(BaseException):
        await tarefa
    return None, True


async def _responder(
    etapas: Etapas,
    modelo: str,
    conversa: int,
    texto: str,
    ordem: list[str],
    forcado: bool,
    mensagem_id: int,
    voz: bool = False,
    anexos: list[dict] | None = None,
) -> None:
    resposta_id = None
    parar = _paradas.get(conversa)

    def fim(**dados):
        # A resposta acabou: a tela libera o campo aqui, e o servidor também —
        # editar e refazer não esperam o título e o aprendizado, que seguem.
        etapas.marcar('fim', **dados)
        if _paradas.get(conversa) is parar:
            _paradas.pop(conversa, None)

    try:
        # O básico (hora, data, lembrete, agenda, tarefas) sai em código, antes
        # de tudo: sem busca na memória e sem modelo (rapidas.py). Comando na
        # frente ("/claude que horas são") manda no lugar disso.
        rapida = None if forcado or anexos else rapidas.responder(texto, datetime.now())
        if rapida:
            t = rapida['tarefa']
            if t:
                banco.adicionar_tarefa(t['texto'], t['prazo'], t['hora'], conversa, privada=rapida['privada'])
            etapas.marcar('rapida', tipo=rapida['tipo'])
            etapas.texto(rapida['texto'])
            resposta_id = banco.adicionar(conversa, 'solis', rapida['texto'], privada=rapida['privada'], cerebro='solis')
            fim(cerebro='solis')
            if t:
                # A mesma etapa do aprendizado: a tela mostra "Tarefa anotada".
                etapas.marcar('aprendizado', novas=0, textos=[], tarefas=[t], compromissos=[])
            return

        # Só o fim da conversa vai inteiro; o começo vai como resumo. O que ficou
        # de fora não se perde: está no banco, e a busca traz de volta o trecho.
        resumido, historico, desde = resumo.para_o_modelo(conversa)
        memorias, trechos = await busca.contexto(texto, conversa, desde)
        arquivos = sum(1 for t in trechos if t.get('arquivo'))
        etapas.marcar('memoria', memorias=len(memorias), trechos=len(trechos) - arquivos, arquivos=arquivos)
        # As tarefas abertas vão no pedido, na mesma lista dos trechos (o filtro
        # do que é privado antes da nuvem é o mesmo): "o que eu tenho pra hoje?"
        trechos = trechos + _tarefas_no_pedido() + _agenda_no_pedido()
        pedida = memoria.hora_pedida(texto, datetime.now())
        if pedida:
            trechos.append({'lembrete': True, 'dia': pedida[0], 'hora': pedida[1], 'relativa': pedida[2], 'privada': False})

        try:
            aberto, parada = await _ate_parar(
                roteador.responder(ordem, modelo, conversa, historico, memorias, trechos, resumido,
                                   texto + roteador.nota_anexos(anexos), etapas, voz=voz),
                parar,
            )
            if parada:
                fim(parada=True)
                return
            fluxo, cerebro = aberto
        except roteador.NinguemRespondeu as e:
            # Sem modelo nenhum não há extração — mas um pedido de guardar não
            # pode se perder por isso. Guarda a mensagem como veio.
            if memoria.eh_pedido(texto):
                memoria.guardar_pedido_cru(texto, conversa)
            etapas.erro(**_ninguem_respondeu(e, forcado))
            return

        resposta = []
        cortada = parada = False
        try:
            while True:
                pedaco, parada = await _ate_parar(anext(fluxo, None), parar)
                if parada or pedaco is None:
                    break
                resposta.append(pedaco)
                etapas.texto(pedaco)
        except Exception:
            log.exception('a resposta da conversa %s caiu no meio', conversa)
            cortada = True
        finally:
            if parada:
                with contextlib.suppress(Exception):
                    await fluxo.aclose()
            # finally: nem o servidor desligando no meio perde o que já chegou.
            if resposta:
                resposta_id = banco.adicionar(conversa, 'solis', ''.join(resposta), cerebro=cerebro)
        fim(cerebro=cerebro, **({'cortada': True} if cortada else {}),
                      **({'parada': True} if parada else {}))

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
    criadas: list[dict] = list(etapas.anotadas)
    marcados: list[dict] = []
    novas = await memoria.aprender(
        modelo, conversa, texto, historico[-3:-1], mensagem_id, tarefas=criadas, compromissos=marcados
    )
    etapas.marcar(
        'aprendizado', novas=len(novas or []), textos=novas or [], tarefas=criadas, compromissos=marcados, modelo=modelo
    )
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
    fundo.add_task(busca.indexar_se_livre)
    return {'memoria': memoria}


@app.delete('/memorias/{id_}')
async def esquecer(id_: int):
    if not banco.apagar_memoria(id_):
        return JSONResponse({'erro': 'memoria_inexistente'}, status_code=404)
    return {'ok': True}


# — Tarefas ———————————————————————————————————————————————————————————————————————

# As abertas mais próximas do prazo que vão em cada pedido. Mais que isso é
# pedido longo pra pouca chance de a mensagem ser sobre a 21ª.
TAREFAS_NO_PEDIDO = 20


def _tarefas_no_pedido() -> list[dict]:
    return [
        {'tarefa': True, 'texto': t['texto'], 'prazo': t['prazo'], 'hora': t['hora'], 'privada': t['privada']}
        for t in banco.tarefas_abertas(TAREFAS_NO_PEDIDO)
    ]


# Os compromissos de hoje aos próximos dias que vão em cada pedido.
AGENDA_DIAS = 7
AGENDA_NO_PEDIDO = 20


def _agenda_no_pedido() -> list[dict]:
    hoje = date.today()
    return [
        {
            'compromisso': True,
            'texto': c['titulo'] + (f' ({c["onde"]})' if c['onde'] else ''),
            'dia': c['dia'], 'hora': c['hora'], 'privada': c['privado'],
        }
        for c in banco.compromissos(hoje.isoformat(), (hoje + timedelta(days=AGENDA_DIAS)).isoformat(), AGENDA_NO_PEDIDO)
    ]


def _meia_noite_utc() -> str:
    """O começo do dia de hoje, na hora local, em UTC (como o banco guarda)."""
    hoje = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return hoje.astimezone(timezone.utc).isoformat(timespec='seconds')


class NovaTarefa(BaseModel):
    texto: str
    prazo: str | None = None
    hora: str | None = None
    privada: bool = False


class MudancaTarefa(BaseModel):
    texto: str | None = None
    prazo: str | None = None
    hora: str | None = None
    feita: bool | None = None


def _prazo_valido(prazo: str | None, hora: str | None) -> str | None:
    """O erro, ou None se prazo e hora estão no formato (AAAA-MM-DD, HH:MM)."""
    if prazo:
        try:
            date.fromisoformat(prazo)
        except ValueError:
            return 'prazo_invalido'
    if hora and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', hora):
        return 'hora_invalida'
    return None


@app.get('/tarefas')
async def listar_tarefas():
    """As abertas e as feitas hoje, da mais perto do prazo pra mais longe (sem
    prazo por último). Cada uma com `origem`: o título da conversa de onde veio."""
    return {'tarefas': banco.tarefas(_meia_noite_utc())}


@app.post('/tarefas')
async def criar_tarefa(corpo: NovaTarefa):
    texto = corpo.texto.strip()
    if not texto:
        return JSONResponse({'erro': 'texto_vazio'}, status_code=400)
    if erro := _prazo_valido(corpo.prazo, corpo.hora):
        return JSONResponse({'erro': erro}, status_code=400)
    id_ = banco.adicionar_tarefa(texto, corpo.prazo or None, corpo.hora or None, privada=corpo.privada)
    return {'tarefa': banco.tarefa(id_)}


@app.patch('/tarefas/{id_}')
async def mudar_tarefa(id_: int, corpo: MudancaTarefa):
    """Só o que veio no corpo muda: `{"feita": true}` marca, `{"prazo": ""}` tira
    o prazo (e a hora junto)."""
    campos = {k: getattr(corpo, k) for k in corpo.model_fields_set}
    if 'texto' in campos:
        campos['texto'] = (campos['texto'] or '').strip()
        if not campos['texto']:
            return JSONResponse({'erro': 'texto_vazio'}, status_code=400)
    if erro := _prazo_valido(campos.get('prazo'), campos.get('hora')):
        return JSONResponse({'erro': erro}, status_code=400)
    tarefa = banco.mudar_tarefa(id_, **campos)
    if tarefa is None:
        return JSONResponse({'erro': 'tarefa_inexistente'}, status_code=404)
    return {'tarefa': tarefa}


@app.delete('/tarefas/{id_}')
async def apagar_tarefa(id_: int):
    if not banco.apagar_tarefa(id_):
        return JSONResponse({'erro': 'tarefa_inexistente'}, status_code=404)
    return {'ok': True}


# — Voz ————————————————————————————————————————————————————————————————————————————

@app.get('/voz')
async def estado_voz():
    """Se dá pra falar: o faster-whisper instalado e o modelo na pasta."""
    return {'disponivel': voz.disponivel(), 'modelo': voz.MODELO}


@app.post('/voz')
async def transcrever_voz(request: Request):
    """O áudio cru no corpo (o que o MediaRecorder do navegador grava: webm com
    opus), e o texto de volta. Nada é guardado: o áudio só vive neste pedido."""
    try:
        return await voz.transcrever(await request.body())
    except voz.SemModelo as e:
        return JSONResponse({'erro': 'sem_modelo', 'motivo': str(e)}, status_code=503)
    except voz.AudioRuim as e:
        return JSONResponse({'erro': 'audio_ruim', 'motivo': str(e)}, status_code=400)


# — Fala ———————————————————————————————————————————————————————————————————————————

class TextoFala(BaseModel):
    texto: str
    conversa: int | None = None
    # Uma voz do Gemini pra ouvir antes de escolher; sem ela, a escolhida.
    voz: str | None = None


class AjustesFala(BaseModel):
    voz: str | None = None
    modelo: str | None = None


@app.get('/fala/ajustes')
async def ajustes_da_fala():
    """A voz e o modelo do Gemini escolhidos, e as opções."""
    return {'voz': fala.voz_gemini(), 'modelo': fala.modelo_gemini(),
            'vozes': fala.VOZES_GEMINI, 'modelos': fala.MODELOS_GEMINI}


@app.put('/fala/ajustes')
async def ajustar_fala(corpo: AjustesFala):
    try:
        fala.ajustar(corpo.voz, corpo.modelo)
    except ValueError as e:
        return JSONResponse({'erro': 'ajuste_invalido', 'motivo': str(e)}, status_code=400)
    return await ajustes_da_fala()


@app.post('/fala/partes')
async def partes_da_fala(corpo: TextoFala):
    """A resposta em pedaços pra falar um de cada vez: o primeiro áudio chega
    rápido e o resto é gerado enquanto ele toca."""
    return {'partes': fala.partes(corpo.texto), 'lingua': fala.lingua(corpo.texto)}


@app.post('/fala')
async def falar(corpo: TextoFala):
    """Um pedaço de texto em áudio, pela cadeia de vozes (fala.py). Quem falou
    vem no cabeçalho X-Solis-Voz. A conversa decide se pode ir pra nuvem: com
    algo privado nela, só a voz local."""
    try:
        audio, tipo, quem = await fala.falar(corpo.texto, corpo.conversa, corpo.voz)
    except fala.SemVoz as e:
        return JSONResponse({'erro': 'sem_voz', 'motivo': str(e)}, status_code=503)
    cabecalhos = {'X-Solis-Voz': quem, 'Access-Control-Expose-Headers': 'X-Solis-Voz, X-Solis-Antes'}
    if fala.ultimos_motivos:
        # Cabeçalho HTTP é ASCII: os motivos vão sem acento.
        import unicodedata
        # Uma linha só: erro do Google vem com quebra de linha, e cabeçalho com
        # quebra derruba a resposta inteira (visto com uma chave inválida).
        motivos = ' '.join('; '.join(fala.ultimos_motivos).split())
        cabecalhos['X-Solis-Antes'] = unicodedata.normalize('NFKD', motivos).encode('ascii', 'ignore').decode()[:500]
    return Response(audio, media_type=tipo, headers=cabecalhos)


# — Fala aos pedaços ——————————————————————————————————————————————————————————————
# O <audio> do navegador toca enquanto o áudio chega, mas só por GET: a tela
# guarda o pedido aqui (POST, o texto no corpo — nunca na URL, que vai pro log)
# e o <audio> busca pelo id.

_fluxos: dict[str, tuple[str, int | None, float]] = {}


@app.post('/fala/fluxo')
async def preparar_fluxo(corpo: TextoFala):
    import time
    agora = time.time()
    for id_, (_, _, quando) in list(_fluxos.items()):
        if agora - quando > 120:
            _fluxos.pop(id_, None)
    id_ = uuid.uuid4().hex
    _fluxos[id_] = (corpo.texto, corpo.conversa, agora)
    return {'id': id_}


@app.get('/fala/fluxo/{id_}')
async def tocar_fluxo(id_: str):
    pedido = _fluxos.pop(id_, None)
    if pedido is None:
        return JSONResponse({'erro': 'fluxo_inexistente'}, status_code=404)
    texto, conversa, _ = pedido
    try:
        pedacos, tipo, quem = await fala.falar_aos_pedacos(texto, conversa)
    except fala.SemVoz as e:
        return JSONResponse({'erro': 'sem_voz', 'motivo': str(e)}, status_code=503)
    return StreamingResponse(pedacos, media_type=tipo, headers={'X-Solis-Voz': quem, 'Cache-Control': 'no-store'})


# — Voz da Fish Audio (em teste, fala.py) —————————————————————————————————————————

class ChaveFish(BaseModel):
    chave: str


class VozFish(BaseModel):
    voz: str | None = None
    nome: str | None = None


class AmostraFish(BaseModel):
    texto: str = 'Oi, Matheus! Eu sou o Solis. Anotei o seu lembrete pra amanhã às nove da manhã.'
    voz: str | None = None


@app.get('/fala/fish')
async def estado_fish():
    return {'chave': fala.chave_fish() is not None, 'voz': fala.voz_fish(), 'nome': fala.nome_voz_fish(),
            'modelo': fala.FISH_MODELO}


@app.put('/fala/fish/chave')
async def guardar_chave_fish(corpo: ChaveFish):
    """Confere a chave na Fish antes de guardar (selada, como as dos cérebros)."""
    try:
        await fala.guardar_chave_fish(corpo.chave)
    except fala.SemVoz as e:
        return JSONResponse({'erro': 'chave_recusada', 'motivo': str(e)}, status_code=400)
    except httpx.HTTPError:
        return JSONResponse({'erro': 'fish_fora'}, status_code=503)
    return await estado_fish()


@app.delete('/fala/fish/chave')
async def esquecer_chave_fish():
    fala.esquecer_chave_fish()
    return await estado_fish()


@app.get('/fala/fish/vozes')
async def vozes_fish(q: str = '', pagina: int = 1, ordem: str = 'score', lingua: str = 'pt', etiqueta: str = ''):
    """A biblioteca de vozes da Fish, por página. lingua vazia = todas."""
    try:
        return await fala.vozes_fish(busca=q, pagina=pagina, ordem=ordem, lingua_=lingua or None,
                                     etiqueta=etiqueta or None)
    except (fala.SemVoz, httpx.HTTPError) as e:
        return JSONResponse({'erro': 'sem_vozes', 'motivo': str(e)}, status_code=503)


@app.put('/fala/fish/voz')
async def escolher_voz_fish(corpo: VozFish):
    fala.escolher_voz_fish(corpo.voz, corpo.nome)
    return await estado_fish()


@app.post('/fala/fish/amostra')
async def amostra_fish(corpo: AmostraFish):
    """A Fish falando direto, sem a cadeia — pra ouvir uma voz antes de
    escolher. O tempo até o áudio vem no cabeçalho X-Solis-Tempo (segundos)."""
    import time
    t = time.perf_counter()
    try:
        audio = await fala.fish(fala.limpar(corpo.texto), fala.lingua(corpo.texto), voz=corpo.voz)
    except (fala.SemVoz, httpx.HTTPError) as e:
        return JSONResponse({'erro': 'sem_voz', 'motivo': str(e)}, status_code=503)
    return Response(audio, media_type='audio/mpeg', headers={
        'X-Solis-Tempo': f'{time.perf_counter() - t:.2f}', 'Access-Control-Expose-Headers': 'X-Solis-Tempo'})


# — Palavra de ativação ———————————————————————————————————————————————————————————

@app.get('/ativacao')
async def estado_ativacao():
    """O que falta pra escuta da palavra funcionar: chave, palavra, idioma."""
    return ativacao.estado()


class ChavePicovoice(BaseModel):
    chave: str


@app.put('/ativacao/chave')
async def guardar_chave_ativacao(corpo: ChavePicovoice):
    """A AccessKey do Picovoice, colada pelo Matheus na tela. Conferida com o
    modelo da palavra (se já houver) e guardada selada. Nunca volta."""
    try:
        await asyncio.to_thread(ativacao.guardar_chave, corpo.chave)
    except ativacao.ChaveRecusada as e:
        return JSONResponse({'erro': 'chave_recusada', 'motivo': str(e)[:300]}, status_code=400)
    except (ativacao.ModeloRecusado, ativacao.SemConfiguracao) as e:
        return JSONResponse({'erro': 'modelo_recusado', 'motivo': str(e)[:300]}, status_code=400)
    return ativacao.estado()


@app.put('/ativacao/palavra')
async def guardar_palavra_ativacao(request: Request):
    """O arquivo .ppn da palavra, cru no corpo."""
    try:
        await asyncio.to_thread(ativacao.guardar_palavra, await request.body())
    except ativacao.ChaveRecusada as e:
        return JSONResponse({'erro': 'chave_recusada', 'motivo': str(e)[:300]}, status_code=400)
    except (ativacao.ModeloRecusado, ativacao.SemConfiguracao) as e:
        return JSONResponse({'erro': 'modelo_recusado', 'motivo': str(e)[:300]}, status_code=400)
    return ativacao.estado()


@app.delete('/ativacao')
async def apagar_ativacao():
    ativacao.apagar()
    return ativacao.estado()


# SOLIS_ESCUTA_LOG=1 mostra no log o que o Whisper ouviu em cada trecho da
# escuta — só pra diagnosticar. Desligado por padrão: o microfone aberto pega
# conversa do cômodo, e isso não deve ir parar num log.
ESCUTA_LOG = os.environ.get('SOLIS_ESCUTA_LOG') == '1'


def _aquecer() -> None:
    """Ouviu "Solis": carrega o modelo local enquanto a pessoa ainda fala o
    pedido — a resposta não espera o modelo subir na GPU."""
    # Depois de o servidor reiniciar, o da última vez (guardado).
    modelo = _ultimo_modelo or banco.ajuste('modelo_local')
    if modelo:
        tarefa = asyncio.create_task(ollama.aquecer(modelo))
        _tarefas.add(tarefa)
        tarefa.add_done_callback(_tarefas.discard)


async def _transcrever_escuta(audio: bytes) -> str:
    try:
        texto = (await voz.transcrever(audio, vad=False))['texto']
    except (voz.SemModelo, voz.AudioRuim):
        texto = ''
    if ESCUTA_LOG:
        log.info('escuta: %.1f s -> %r', (len(audio) - 44) / 2 / ativacao.TAXA, texto)
    return texto


@app.websocket('/escuta')
async def escuta(ws: WebSocket):
    """O microfone aberto do navegador: áudio PCM 16 bits, 16 kHz, mono, em
    pedaços binários. Volta {"tipo": "ativou"} ao ouvir a palavra e, quando a
    pessoa para de falar, {"tipo": "texto", "texto"} (ou {"tipo": "nada"}).
    Texto {"pausa": true} do navegador suspende a escuta — enquanto o Solis
    fala, a voz dele não pode acordar ele mesmo."""
    await ws.accept()
    try:
        escutando = await asyncio.to_thread(ativacao.Escuta)
    except Exception as e:
        await ws.send_json({'tipo': 'erro', 'motivo': str(e)[:300]})
        await ws.close()
        return
    pausada = False
    try:
        while True:
            msg = await ws.receive()
            if msg.get('type') == 'websocket.disconnect':
                break
            if msg.get('text'):
                try:
                    pausada = bool(json.loads(msg['text']).get('pausa'))
                except ValueError:
                    pass
                continue
            if pausada or not msg.get('bytes'):
                continue
            # Gerador: cada decisão (confirmar/descartar) vale já pro quadro seguinte.
            for tipo, audio in escutando.alimentar(msg['bytes']):
                if tipo == 'ativou':
                    await ws.send_json({'tipo': 'ativou'})
                    _aquecer()
                elif tipo in ('previa', 'frase'):
                    # Whisper: o começo de um trecho de fala tem "Solis"?
                    achou, resto = ativacao.palavra_no_inicio(await _transcrever_escuta(audio))
                    if not achou:
                        escutando.descartar()
                        continue
                    await ws.send_json({'tipo': 'ativou'})
                    _aquecer()
                    if tipo == 'frase' and resto:
                        # "Solis, que horas são?" de uma vez, e acabou: já é o comando.
                        await ws.send_json({'tipo': 'texto', 'texto': resto})
                    else:
                        escutando.confirmar()
                elif audio is None:
                    await ws.send_json({'tipo': 'nada'})
                else:
                    # O comando pode trazer a própria palavra no começo (veio do trecho).
                    _, texto = ativacao.palavra_no_inicio(await _transcrever_escuta(audio))
                    await ws.send_json({'tipo': 'texto', 'texto': texto} if texto else {'tipo': 'nada'})
    except WebSocketDisconnect:
        pass
    finally:
        escutando.fechar()


# — Aprovações do agente (agente.py) ——————————————————————————————————————————————

class Aprovacao(BaseModel):
    aprovar: bool


@app.post('/aprovacoes/{id_}')
async def responder_aprovacao(id_: str, corpo: Aprovacao):
    """O Matheus respondeu o cartão de aprovação na conversa."""
    from . import agente
    if not agente.responder_aprovacao(id_, corpo.aprovar):
        return JSONResponse({'erro': 'aprovacao_inexistente'}, status_code=404)
    return {'ok': True}


# — Controle do PC (pc.py) ————————————————————————————————————————————————————————

def _estado_pc() -> dict:
    return {'ligada': pc.ligada(), 'pastas': pc.pastas(), 'disponivel': pc.disponivel()}


@app.get('/pc')
async def estado_pc():
    """A ferramenta Arquivos: ligada, as pastas autorizadas, e se está valendo."""
    return _estado_pc()


class PastasPc(BaseModel):
    pastas: list[str]


@app.put('/pc/pastas')
async def guardar_pastas_pc(corpo: PastasPc):
    try:
        pc.guardar_pastas(corpo.pastas)
    except ValueError as e:
        return JSONResponse({'erro': 'pasta_invalida', 'motivo': str(e)}, status_code=400)
    return _estado_pc()


class LigadaPc(BaseModel):
    ligada: bool


@app.put('/pc/ligada')
async def ligar_pc(corpo: LigadaPc):
    pc.ligar(corpo.ligada)
    return _estado_pc()


@app.get('/pc/registro')
async def registro_pc(limite: int = 50):
    """O que o Solis fez no computador, do mais novo pro mais antigo."""
    return banco.acoes(max(1, min(limite, 500)))


# — Agenda ————————————————————————————————————————————————————————————————————————

class NovoCompromisso(BaseModel):
    titulo: str
    dia: str
    hora: str | None = None
    duracao: int | None = None
    onde: str | None = None
    privado: bool = False


class MudancaCompromisso(BaseModel):
    titulo: str | None = None
    dia: str | None = None
    hora: str | None = None
    duracao: int | None = None
    onde: str | None = None


def _erro_compromisso(campos: dict) -> str | None:
    if 'titulo' in campos and not (campos['titulo'] or '').strip():
        return 'titulo_vazio'
    if 'dia' in campos and not campos['dia']:
        return 'dia_vazio'
    if erro := _prazo_valido(campos.get('dia'), campos.get('hora')):
        return 'dia_invalido' if erro == 'prazo_invalido' else erro
    duracao = campos.get('duracao')
    if duracao is not None and not 0 <= duracao <= 24 * 60:
        return 'duracao_invalida'
    return None


@app.get('/agenda')
async def listar_agenda(de: str, ate: str | None = None):
    """Os compromissos de `de` a `ate` (AAAA-MM-DD; sem `ate`, só o dia `de`),
    do dia inteiro pro mais tarde. Cada um com `origem`: a conversa de onde veio."""
    if _prazo_valido(de, None) or (ate and _prazo_valido(ate, None)):
        return JSONResponse({'erro': 'dia_invalido'}, status_code=400)
    return {'compromissos': banco.compromissos(de, ate or de)}


@app.post('/agenda')
async def criar_compromisso(corpo: NovoCompromisso):
    campos = corpo.model_dump()
    if erro := _erro_compromisso(campos):
        return JSONResponse({'erro': erro}, status_code=400)
    id_ = banco.adicionar_compromisso(
        corpo.titulo.strip(), corpo.dia, corpo.hora or None, corpo.duracao, (corpo.onde or '').strip() or None,
        privado=corpo.privado,
    )
    return {'compromisso': banco.compromisso(id_)}


@app.patch('/agenda/{id_}')
async def mudar_compromisso(id_: int, corpo: MudancaCompromisso):
    campos = {k: getattr(corpo, k) for k in corpo.model_fields_set}
    if erro := _erro_compromisso(campos):
        return JSONResponse({'erro': erro}, status_code=400)
    if 'titulo' in campos:
        campos['titulo'] = campos['titulo'].strip()
    if 'onde' in campos:
        campos['onde'] = (campos['onde'] or '').strip()
    compromisso = banco.mudar_compromisso(id_, **campos)
    if compromisso is None:
        return JSONResponse({'erro': 'compromisso_inexistente'}, status_code=404)
    return {'compromisso': compromisso}


@app.delete('/agenda/{id_}')
async def apagar_compromisso(id_: int):
    if not banco.apagar_compromisso(id_):
        return JSONResponse({'erro': 'compromisso_inexistente'}, status_code=404)
    return {'ok': True}


# — Conhecimento ——————————————————————————————————————————————————————————————————

@app.get('/conhecimento')
async def listar_conhecimento(fundo: BackgroundTasks, q: str = ''):
    """Os arquivos, do mais novo pro mais antigo. `q` filtra pelo nome e pelo
    texto (o texto das fontes privadas não é buscado, só o nome).

    Se ainda falta trecho sem vetor, tenta indexar de novo: a tela pergunta a
    cada 1,5 s enquanto falta, e sem isto um Ollama que volta depois de fora
    deixava a indexação parada até o próximo upload ou mensagem."""
    documentos = banco.documentos()
    if any(d['indexados'] < d['trechos'] for d in documentos):
        fundo.add_task(busca.indexar_se_livre)
    # O mesmo pras páginas escaneadas: a fila volta a andar quando o Ollama volta.
    if any(d['lidas'] < d['escaneadas'] for d in documentos):
        fundo.add_task(ocr.ler_se_livre)
    lista = banco.buscar_documentos(q) if q.strip() else documentos
    for d in lista:
        # Por que a leitura não anda: 'ollama' (fora) ou 'ocr' (nada lê aqui).
        d['leitura_parada'] = ocr.parado if d['lidas'] < d['escaneadas'] else None
    return {'documentos': lista}


@app.post('/conhecimento')
async def adicionar_conhecimento(request: Request, nome: str, fundo: BackgroundTasks, privado: bool = False):
    """O arquivo vem cru no corpo (não multipart): o front manda o File como
    está, e o nome vai na query. Lê, corta em trechos e guarda; os vetores
    saem em segundo plano — a tela acompanha pelo `indexados`."""
    dados = await request.body()
    try:
        # Ler um PDF grande leva segundos: fora do laço de eventos. Guardar,
        # não — o banco só é escrito desta thread (ver conhecimento.preparar).
        lido = await asyncio.to_thread(conhecimento.preparar, nome, dados)
        documento = conhecimento.guardar(nome, lido, privado)
    except conhecimento.NaoLeu as e:
        return JSONResponse({'erro': 'nao_leu', 'motivo': str(e)}, status_code=400)
    except banco.Duplicado as e:
        return JSONResponse({'erro': 'ja_existe', 'documento': e.documento}, status_code=409)
    fundo.add_task(busca.indexar_se_livre)
    if lido['escaneadas']:
        fundo.add_task(ocr.ler_se_livre)
    return {'documento': next(d for d in banco.documentos() if d['id'] == documento)}


class Pagina(BaseModel):
    url: str
    privado: bool = False


@app.post('/conhecimento/pagina')
async def adicionar_pagina(corpo: Pagina, fundo: BackgroundTasks):
    """Baixa a página (ou o PDF do endereço), tira o conteúdo principal e guarda
    como os arquivos. Os mesmos erros do POST /conhecimento."""
    try:
        url, tipo, dados = await conhecimento.baixar(corpo.url)
        nome, lido = await asyncio.to_thread(conhecimento.preparar_pagina, url, tipo, dados)
        documento = conhecimento.guardar(nome, lido, corpo.privado)
    except conhecimento.NaoLeu as e:
        return JSONResponse({'erro': 'nao_leu', 'motivo': str(e)}, status_code=400)
    except banco.Duplicado as e:
        return JSONResponse({'erro': 'ja_existe', 'documento': e.documento}, status_code=409)
    fundo.add_task(busca.indexar_se_livre)
    if lido.get('escaneadas'):
        fundo.add_task(ocr.ler_se_livre)
    return {'documento': next(d for d in banco.documentos() if d['id'] == documento)}


class Privacidade(BaseModel):
    privado: bool


@app.patch('/conhecimento/{id_}')
async def mudar_conhecimento(id_: int, corpo: Privacidade):
    if not banco.marcar_documento_privado(id_, corpo.privado):
        return JSONResponse({'erro': 'documento_inexistente'}, status_code=404)
    return {'documento': next(d for d in banco.documentos() if d['id'] == id_)}


@app.delete('/conhecimento/{id_}')
async def apagar_conhecimento(id_: int):
    if not banco.apagar_documento(id_):
        return JSONResponse({'erro': 'documento_inexistente'}, status_code=404)
    return {'ok': True}
