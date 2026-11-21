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
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

import httpx
from fastapi import BackgroundTasks, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

import numpy as np

from . import apis, ativacao, avisos, banco, busca, cerebros, conhecimento, estilos, fala, memoria, microfone, ocr, ollama, palavra, pc, rapidas, resumo, roteador, transcricao, voz
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
    # O Ollama, se estiver instalado e parado: o local responde a voz primeiro.
    ligando = asyncio.create_task(ollama.ligar_se_parado())
    # E as tarefas agendadas: o pedido ao Claude na hora marcada.
    relogio = asyncio.create_task(_vigiar_agendadas())
    # E a tirar o Whisper da memória quando ninguém fala há um tempo.
    ouvido = asyncio.create_task(voz.vigiar())
    boca = asyncio.create_task(fala.vigiar())
    # As frases da narração, gravadas já: a primeira vez não espera a voz gerar.
    frases = asyncio.create_task(fala.gravar_frases())
    yield
    boca.cancel()
    frases.cancel()
    indexacao.cancel()
    leitura.cancel()
    vigia.cancel()
    relogio.cancel()
    ligando.cancel()
    ouvido.cancel()
    # O navegador do Claude (e a janela dele) fecha junto com o servidor.
    from . import navegador
    await asyncio.to_thread(navegador.parar)


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


class NovoTitulo(BaseModel):
    titulo: str


@app.patch('/conversas/{conversa}')
async def renomear_conversa(conversa: int, corpo: NovoTitulo):
    """O Matheus deu outro nome à conversa (o título automático não troca mais:
    ele só vem quando ainda não há título)."""
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    titulo = ' '.join(corpo.titulo.split())[:120]
    if not titulo:
        return JSONResponse({'erro': 'titulo_vazio'}, status_code=400)
    banco.guardar_titulo(conversa, titulo)
    return {'id': conversa, 'titulo': titulo}


@app.delete('/conversas/{conversa}')
async def apagar_conversa(conversa: int):
    """Apaga a conversa e os anexos dela (as memórias ficam). Respondendo,
    espera acabar; com comando em segundo plano, a sessão do Claude para ele."""
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    if conversa in _paradas:
        return JSONResponse({'erro': 'respondendo'}, status_code=409)
    try:
        from . import agente
        viva = agente._vivas.get(conversa)
        if viva is not None and viva.laco is not None:
            asyncio.run_coroutine_threadsafe(viva.fechar(), viva.laco)
    except ImportError:
        pass
    for caminho in banco.apagar_conversa(conversa):
        with contextlib.suppress(OSError):
            Path(caminho).unlink()
    banco.registrar_acao(None, 'apagar_conversa', {'conversa': conversa}, 'apagada pelo Matheus', True)
    return {'ok': True}


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
    # O botão Pesquisa: vai pro Claude, com a orientação de pesquisa longa
    # (várias fontes, citações, as fontes no fim) — roteador.NOTA_PESQUISA.
    pesquisa: bool = False
    # Interno (o relógio das agendadas, não a tela): o nome da tarefa agendada
    # que mandou esta mensagem — vai uma nota pro cérebro, não pra conversa.
    agendada: str = ''
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
    if envio.pesquisa and not forcado:
        # Pesquisa longa: o Claude primeiro (ele busca, lê, usa ajudantes e
        # cita); sem ele (a cota acabou), os de API pelo corpo do Solis — o
        # navegador pra buscar e o WebFetch pra ler (19/11/2026: as funções são
        # do Solis). Antes era só o Claude, e sem ele a pesquisa falhava.
        ordem = (['claude'] if cerebros.disponivel('claude') else []) + [
            c for c in ordem if c != 'claude' and roteador.com_corpo(c)]
        # Sem nenhum: o Claude mesmo assim, pra falhar com a mensagem certa.
        ordem, forcado = ordem or ['claude'], True
    if envio.agendada and not forcado:
        # A tarefa agendada vai primeiro pro Claude (é a do Claude Desktop,
        # agendadas.py); sem ele (a cota acabou), segue nos outros, que fazem
        # pelo corpo do Solis. Antes ia só pro Claude, e sem ele a tarefa
        # falhava (as funções são do Solis: decisão do Matheus, 18/11/2026).
        ordem = (['claude'] if cerebros.disponivel('claude') else []) + [c for c in ordem if c != 'claude']
    if anexos and not forcado:
        # Com anexo, o Claude primeiro: ele lê texto, PDF e imagem; o modelo
        # local não enxerga imagem nem tem a pasta de trabalho.
        ordem = sorted(ordem, key=lambda c: c != 'claude')
    global _ultimo_modelo
    if envio.modelo and envio.modelo != _ultimo_modelo:
        _ultimo_modelo = envio.modelo
        banco.guardar_ajuste('modelo_local', envio.modelo)
    # A tela manda vazio quando leu os modelos com o Ollama fora; ligado depois
    # (o Solis liga sozinho), o local usa o último escolhido, e não cai como
    # "Ollama fora do ar" (visto em 16/11/2026).
    if not envio.modelo:
        envio.modelo = _ultimo_modelo or banco.ajuste('modelo_local') or ''

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
    if envio.pesquisa:
        etapas.marcar('pesquisa')
    parar = _paradas[conversa] = asyncio.Event()
    tarefa = asyncio.create_task(
        _responder(etapas, envio.modelo, conversa, texto, ordem, forcado, mensagem_id, envio.voz, anexos,
                   envio.pesquisa, envio.agendada)
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


@app.get('/anexos/arquivo')
async def imagem_do_anexo(caminho: str):
    """A imagem de um anexo, pra miniatura na fala do Matheus. Só imagem, e só
    de dentro da pasta de anexos (o mesmo _anexo do POST): nada mais do disco
    sai por aqui."""
    a = _anexo(caminho)
    if a is None or not a['tipo'].startswith('image/'):
        return JSONResponse({'erro': 'nao_achado'}, status_code=404)
    dados = await asyncio.to_thread(Path(a['caminho']).read_bytes)
    return Response(dados, media_type=a['tipo'], headers={'Cache-Control': 'private, max-age=86400'})


class Projeto(BaseModel):
    pasta: str | None = None
    modo: str = 'pedir'
    # O projeto da conversa (id); null tira dela. Sem o campo, fica o que era.
    projeto: int | None = None


def _pasta_valida(texto: str | None) -> str | None | JSONResponse:
    if not texto or not texto.strip():
        return None
    p = Path(texto.strip().strip('"')).expanduser()
    if not p.is_dir():
        return JSONResponse({'erro': 'pasta_inexistente'}, status_code=400)
    return str(p.resolve())


@app.get('/conversas/{conversa}/projeto')
async def ler_projeto(conversa: int):
    """Onde o Claude trabalha nesta conversa: o projeto (`projeto`: id e nome,
    ou null), a pasta (a do projeto, se houver) e o modo."""
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    return {**banco.projeto_da_conversa(conversa), 'recentes': banco.projetos_recentes()}


@app.put('/conversas/{conversa}/projeto')
async def guardar_projeto(conversa: int, corpo: Projeto):
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    pasta = _pasta_valida(corpo.pasta)
    if isinstance(pasta, JSONResponse):
        return pasta
    if corpo.modo not in banco.MODOS:
        return JSONResponse({'erro': 'modo_invalido'}, status_code=400)
    antes = banco.projeto_da_conversa(conversa)
    if 'projeto' in corpo.model_fields_set:
        if corpo.projeto is not None and not banco.projeto(corpo.projeto):
            return JSONResponse({'erro': 'projeto_inexistente'}, status_code=404)
        depois = banco.guardar_projeto(conversa, pasta, corpo.modo, corpo.projeto)
    else:
        depois = banco.guardar_projeto(conversa, pasta, corpo.modo)
    if depois['pasta'] != antes['pasta'] or (depois['projeto'] or {}).get('id') != (antes['projeto'] or {}).get('id'):
        # A sessão do Claude mora com a pasta e as instruções com que começou:
        # outra pasta ou outro projeto, outra sessão (o histórico vai no pedido).
        banco.esquecer_sessao_claude(conversa)
    return await ler_projeto(conversa)


# — Projetos: instruções e arquivos fixos, e a pasta de código ————————————————————
class NovoProjeto(BaseModel):
    nome: str
    instrucoes: str = ''
    pasta: str | None = None


def _pasta_projetos() -> Path:
    from . import agente
    return agente._pasta_trabalho().resolve() / 'projetos'


@app.get('/projetos')
async def listar_projetos():
    """Os projetos, o mais mexido primeiro (com quantos arquivos e conversas)."""
    return {'projetos': banco.projetos()}


@app.post('/projetos')
async def criar_projeto(corpo: NovoProjeto):
    if not corpo.nome.strip():
        return JSONResponse({'erro': 'sem_nome'}, status_code=400)
    pasta = _pasta_valida(corpo.pasta)
    if isinstance(pasta, JSONResponse):
        return pasta
    return banco.criar_projeto(corpo.nome[:120], corpo.instrucoes[:20_000], pasta)


@app.get('/projetos/{projeto}')
async def ler_projeto_inteiro(projeto: int):
    p = banco.projeto(projeto)
    return p if p else JSONResponse({'erro': 'projeto_inexistente'}, status_code=404)


@app.put('/projetos/{projeto}')
async def editar_projeto(projeto: int, corpo: NovoProjeto):
    if not corpo.nome.strip():
        return JSONResponse({'erro': 'sem_nome'}, status_code=400)
    pasta = _pasta_valida(corpo.pasta)
    if isinstance(pasta, JSONResponse):
        return pasta
    antes = banco.projeto(projeto)
    if not antes:
        return JSONResponse({'erro': 'projeto_inexistente'}, status_code=404)
    p = banco.editar_projeto(projeto, corpo.nome[:120], corpo.instrucoes[:20_000], pasta)
    if (antes['instrucoes'], antes['pasta']) != (p['instrucoes'], p['pasta']):
        # As conversas dele começam sessão nova do Claude: instruções e pasta
        # entram quando a sessão nasce.
        for c in banco.conversas_do_projeto(projeto):
            banco.esquecer_sessao_claude(c)
    return p


@app.delete('/projetos/{projeto}')
async def apagar_projeto(projeto: int):
    """Apaga o projeto e os arquivos fixos dele (da pasta do Solis). As
    conversas ficam, sem projeto."""
    if not banco.projeto(projeto):
        return JSONResponse({'erro': 'projeto_inexistente'}, status_code=404)
    for c in banco.conversas_do_projeto(projeto):
        banco.esquecer_sessao_claude(c)
    for caminho in banco.apagar_projeto(projeto):
        with contextlib.suppress(OSError):
            Path(caminho).unlink()
    return {'ok': True}


@app.post('/projetos/{projeto}/arquivos')
async def adicionar_arquivo_projeto(projeto: int, request: Request, nome: str):
    """O arquivo cru no corpo, o nome na query (como em /anexos). Fica na pasta
    de trabalho, em projetos/<id>/, enquanto o projeto existir."""
    if not banco.projeto(projeto):
        return JSONResponse({'erro': 'projeto_inexistente'}, status_code=404)
    dados = await request.body()
    if not dados:
        return JSONResponse({'erro': 'vazio'}, status_code=400)
    if len(dados) > ANEXO_MAX:
        return JSONResponse({'erro': 'grande_demais', 'max': ANEXO_MAX}, status_code=413)
    seguro = re.sub(r'[^\w.\- ]', '_', Path(nome).name).strip()[:120] or 'arquivo'
    pasta = _pasta_projetos() / str(projeto)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f'{uuid.uuid4().hex[:8]}-{seguro}'
    await asyncio.to_thread(caminho.write_bytes, dados)
    for c in banco.conversas_do_projeto(projeto):
        banco.esquecer_sessao_claude(c)
    return banco.adicionar_arquivo_projeto(projeto, seguro, str(caminho),
                                           mimetypes.guess_type(seguro)[0] or 'application/octet-stream', len(dados))


@app.delete('/projetos/{projeto}/arquivos/{arquivo}')
async def remover_arquivo_projeto(projeto: int, arquivo: int):
    caminho = banco.remover_arquivo_projeto(projeto, arquivo)
    if caminho is None:
        return JSONResponse({'erro': 'arquivo_inexistente'}, status_code=404)
    with contextlib.suppress(OSError):
        Path(caminho).unlink()
    for c in banco.conversas_do_projeto(projeto):
        banco.esquecer_sessao_claude(c)
    return {'ok': True}


@app.post('/conversas/{conversa}/parar')
async def parar_resposta(conversa: int):
    """O Matheus parou a resposta no meio. O que já chegou fica guardado."""
    parar = _paradas.get(conversa)
    if parar is None:
        return JSONResponse({'erro': 'nada_respondendo'}, status_code=404)
    parar.set()
    return {'ok': True}


# — Tarefas agendadas ——————————————————————————————————————————————————————————
class Agendada(BaseModel):
    nome: str
    pedido: str
    frequencia: str
    hora: str
    dia_semana: int | None = None
    data: str | None = None
    ativa: bool = True


def _com_descricao(a: dict) -> dict:
    from . import agendadas
    return {**a, 'descricao': agendadas.descrever(a)}


def _validar_agendada(corpo: Agendada) -> JSONResponse | None:
    from . import agendadas
    if not corpo.nome.strip() or not corpo.pedido.strip():
        return JSONResponse({'erro': 'sem_nome_ou_pedido'}, status_code=400)
    try:
        agendadas.validar(corpo.frequencia, corpo.hora, corpo.dia_semana, corpo.data)
    except agendadas.AgendaInvalida as e:
        return JSONResponse({'erro': 'agenda_invalida', 'motivo': str(e)}, status_code=400)
    return None


@app.get('/agendadas')
async def listar_agendadas():
    """As tarefas agendadas, com a frase de quando ("Todo dia às 8:00") e a
    próxima vez."""
    return {'agendadas': [_com_descricao(a) for a in banco.agendadas()]}


@app.post('/agendadas')
async def criar_agendada(corpo: Agendada):
    from . import agendadas
    if erro := _validar_agendada(corpo):
        return erro
    prox = agendadas.proxima(corpo.frequencia, corpo.hora, datetime.now(), corpo.dia_semana, corpo.data)
    if prox is None:
        return JSONResponse({'erro': 'agenda_invalida', 'motivo': 'essa data já passou'}, status_code=400)
    a = banco.criar_agendada(corpo.nome.strip()[:120], corpo.pedido.strip()[:4000], corpo.frequencia, corpo.hora,
                             corpo.dia_semana, corpo.data, prox.isoformat(timespec='minutes'))
    banco.registrar_acao(None, 'agendar_tarefa', {'nome': a['nome']}, agendadas.descrever(a), True)
    return _com_descricao(a)


@app.put('/agendadas/{id_}')
async def editar_agendada(id_: int, corpo: Agendada):
    from . import agendadas
    if not banco.agendada(id_):
        return JSONResponse({'erro': 'agendada_inexistente'}, status_code=404)
    if erro := _validar_agendada(corpo):
        return erro
    prox = agendadas.proxima(corpo.frequencia, corpo.hora, datetime.now(), corpo.dia_semana, corpo.data)
    a = banco.editar_agendada(id_, corpo.nome.strip()[:120], corpo.pedido.strip()[:4000], corpo.frequencia,
                              corpo.hora, corpo.dia_semana, corpo.data, corpo.ativa and prox is not None,
                              prox.isoformat(timespec='minutes') if prox else None)
    return _com_descricao(a)


@app.delete('/agendadas/{id_}')
async def apagar_agendada(id_: int):
    if not banco.apagar_agendada(id_):
        return JSONResponse({'erro': 'agendada_inexistente'}, status_code=404)
    return {'ok': True}


@app.post('/agendadas/{id_}/rodar')
async def rodar_agendada_agora(id_: int):
    """Roda agora (sem mudar a próxima vez): a conversa nasce já, e o Claude
    responde nela em segundo plano."""
    a = banco.agendada(id_)
    if not a:
        return JSONResponse({'erro': 'agendada_inexistente'}, status_code=404)
    conversa = _conversa_da_agendada(a)
    tarefa = asyncio.create_task(_executar_agendada(a, conversa))
    _tarefas.add(tarefa)
    tarefa.add_done_callback(_tarefas.discard)
    return {'conversa': conversa}


def _conversa_da_agendada(a: dict) -> int:
    conversa = banco.nova_conversa()
    banco.guardar_titulo(conversa, a['nome'])
    return conversa


async def _executar_agendada(a: dict, conversa: int) -> None:
    """O pedido da tarefa, como uma mensagem pro Claude na conversa dela; no
    fim, o aviso do Windows com o começo da resposta."""
    try:
        resposta = await enviar(conversa, Envio(texto=a['pedido'], agendada=a['nome']))
        if isinstance(resposta, StreamingResponse):
            async for _ in resposta.body_iterator:
                pass
        ultima = next((m for m in reversed(banco.mensagens(conversa)) if m['papel'] == 'solis'), None)
        texto = (ultima or {}).get('texto') or 'Terminou sem resposta.'
        banco.marcar_agendada(a['id'], **_proxima_de(a), ultima=datetime.now().isoformat(timespec='minutes'),
                              ultima_conversa=conversa)
        await avisos.mostrar(f'Tarefa agendada: {a["nome"]}', ' '.join(texto.split())[:160], f'agendada-{a["id"]}-{conversa}')
        log.info('agendada %s rodou na conversa %s', a['id'], conversa)
    except Exception:
        log.exception('a tarefa agendada %s falhou', a['id'])


def _proxima_de(a: dict) -> dict:
    """O que a tarefa tem agora no banco (rodar agora não mexe na próxima)."""
    atual = banco.agendada(a['id']) or a
    return {'proxima': atual['proxima'], 'ativa': atual['ativa']}


async def _vigiar_agendadas() -> None:
    """O relógio das agendadas: confere a cada 30 s, como o dos avisos."""
    from . import agendadas
    while True:
        try:
            for a in agendadas.vencidas(datetime.now()):
                # Marca a próxima vez antes de rodar: a conferida seguinte não
                # pode rodar a mesma de novo enquanto o Claude responde.
                agendadas.avancar(a, datetime.now())
                conversa = _conversa_da_agendada(a)
                tarefa = asyncio.create_task(_executar_agendada(a, conversa))
                _tarefas.add(tarefa)
                tarefa.add_done_callback(_tarefas.discard)
        except Exception:
            log.exception('a conferida das agendadas falhou')
        await asyncio.sleep(30)


# — Documentos (.docx, .xlsx, .pptx, .pdf) ————————————————————————————————————
@app.get('/documentos')
async def ler_documentos():
    """As bibliotecas que as skills de documento usam estão prontas? (documentos.py)"""
    from . import documentos
    return documentos.estado()


@app.post('/documentos/preparar')
async def preparar_documentos():
    """Baixa e instala as bibliotecas numa pasta do Solis (npm e PyPI). O
    Matheus clicou em Configurações; demora um ou dois minutos."""
    from . import documentos
    try:
        r = await asyncio.to_thread(documentos.preparar)
    except documentos.PrepararFalhou as e:
        banco.registrar_acao(None, 'preparar_documentos', {}, f'não deu: {e}', False)
        return JSONResponse({'erro': 'nao_deu', 'motivo': str(e)}, status_code=502)
    banco.registrar_acao(None, 'preparar_documentos', {}, 'bibliotecas instaladas em ' + r['pasta'], True)
    return r


class Abrir(BaseModel):
    caminho: str
    # Mostrar na pasta (o Explorer com o arquivo selecionado), em vez de abrir.
    pasta: bool = False


def _onde_o_solis_trabalha(p: Path) -> bool:
    """A pasta de trabalho, as pastas autorizadas e as de projeto já abertas."""
    from . import agente
    return agente._dentro(str(p)) or any(
        p.resolve().is_relative_to(Path(r).resolve()) for r in banco.projetos_recentes(50) if Path(r).is_dir())


ARTEFATO_MAX = 5_000_000


@app.get('/arquivos/conteudo')
async def conteudo_artefato(caminho: str):
    """O conteúdo de um artefato (página .html, imagem .svg) que o Claude
    criou, pro painel ao lado da conversa — que roda num iframe isolado, sem
    acesso ao Solis. Só .html e .svg, e só de onde o Solis trabalha."""
    p = Path(caminho)
    if p.suffix.lower() not in ('.html', '.htm', '.svg') or not p.is_file():
        return JSONResponse({'erro': 'nao_e_artefato'}, status_code=400)
    if not _onde_o_solis_trabalha(p):
        return JSONResponse({'erro': 'fora_das_pastas'}, status_code=403)
    if p.stat().st_size > ARTEFATO_MAX:
        return JSONResponse({'erro': 'grande_demais'}, status_code=413)
    return {'tipo': 'svg' if p.suffix.lower() == '.svg' else 'html',
            'texto': p.read_text(encoding='utf-8', errors='replace')}


@app.post('/arquivos/abrir')
async def abrir_arquivo(corpo: Abrir):
    """Abre um documento que o Claude criou no programa do Windows (ou mostra
    na pasta). Só documento, e só de onde o Solis trabalha: a pasta de
    trabalho, as pastas autorizadas e as de projeto já abertas."""
    from . import documentos
    p = Path(corpo.caminho)
    if not _onde_o_solis_trabalha(p):
        return JSONResponse({'erro': 'fora_das_pastas'}, status_code=403)
    try:
        documentos.abrir(str(p), corpo.pasta)
    except documentos.PrepararFalhou as e:
        return JSONResponse({'erro': 'nao_abre', 'motivo': str(e)}, status_code=400)
    return {'ok': True}


class Link(BaseModel):
    url: str


def link_valido(url: str) -> bool:
    """Só página da web (http ou https, com endereço), sem espaço nem
    caractere de controle: nunca arquivo, programa ou outro protocolo."""
    from urllib.parse import urlparse
    if len(url) > 4000 or any(c.isspace() or ord(c) < 32 for c in url):
        return False
    u = urlparse(url)
    return u.scheme in ('http', 'https') and bool(u.hostname)


@app.post('/link/abrir')
async def abrir_link(corpo: Link):
    """Abre um link no navegador padrão do Windows. A janela do app (Tauri)
    não abre link em nova janela: a tela manda os links por aqui."""
    import webbrowser
    if not link_valido(corpo.url):
        return JSONResponse({'erro': 'link_invalido'}, status_code=400)
    ok = await asyncio.to_thread(webbrowser.open, corpo.url, 2)
    return {'ok': bool(ok)}


# — Conectores da conta do claude.ai ——————————————————————————————————————————
@app.get('/conectores')
async def ler_conectores(atualizar: bool = False):
    """Os conectores da conta do claude.ai que o Claude do Solis usa (Agenda,
    Drive, Canva...): `nome`, `estado` (conectado, precisa_entrar, conectando,
    falhou), quantas `ferramentas` e quantas só leem. Ler sobe um CLI (alguns
    segundos); fica guardado 5 minutos, `atualizar` lê de novo."""
    try:
        from . import agente
    except ImportError:
        return JSONResponse({'erro': 'sem_sdk'}, status_code=503)
    try:
        return {'conectores': await agente.conectores(atualizar)}
    except agente.AgenteFalhou as e:
        return JSONResponse({'erro': 'nao_deu', 'motivo': str(e)}, status_code=502)


# — Skills ————————————————————————————————————————————————————————————————————
class SkillCorpo(BaseModel):
    nome: str
    descricao: str
    instrucoes: str
    para: list[str]


class SkillLigada(BaseModel):
    ligada: bool


@app.get('/skills')
async def listar_skills():
    """As skills: as suas (escritas no Solis ou à mão, pro Claude, pro Codex ou
    pros dois) e as da conta do claude.ai (`origem` conta ou anthropic), com
    `ligada` (desligar é só do Claude)."""
    from . import skills
    return {'skills': await asyncio.to_thread(skills.listar)}


@app.get('/skills/{nome}')
async def ler_skill(nome: str):
    from . import skills
    s = await asyncio.to_thread(skills.ler, nome)
    return s if s else JSONResponse({'erro': 'skill_inexistente'}, status_code=404)


async def _salvar_skill(corpo: SkillCorpo, antigo: str | None):
    from . import skills
    try:
        s = await asyncio.to_thread(skills.salvar, corpo.nome.strip(), corpo.descricao.strip(), corpo.instrucoes,
                                    corpo.para, antigo)
    except skills.SkillInvalida as e:
        return JSONResponse({'erro': 'skill_invalida', 'motivo': str(e)}, status_code=400)
    banco.registrar_acao(None, 'salvar_skill', {'nome': s['nome'], 'para': s['para'], 'antigo': antigo},
                         s['descricao'][:200], True)
    return s


@app.post('/skills')
async def criar_skill(corpo: SkillCorpo):
    return await _salvar_skill(corpo, None)


@app.put('/skills/{nome}')
async def editar_skill(nome: str, corpo: SkillCorpo):
    return await _salvar_skill(corpo, nome)


@app.delete('/skills/{nome}')
async def apagar_skill(nome: str):
    """Tira uma das suas do Claude e do Codex: a pasta vai pra lixeira do Solis."""
    from . import skills
    if not await asyncio.to_thread(skills.apagar, nome):
        return JSONResponse({'erro': 'skill_inexistente'}, status_code=404)
    banco.registrar_acao(None, 'apagar_skill', {'nome': nome}, 'pra lixeira do Solis', True)
    return {'ok': True}


@app.put('/skills/{nome}/ligada')
async def ligar_skill(nome: str, corpo: SkillLigada):
    from . import skills
    if nome not in {s['nome'] for s in await asyncio.to_thread(skills.listar)}:
        return JSONResponse({'erro': 'skill_inexistente'}, status_code=404)
    skills.ligar(nome, corpo.ligada)
    return {'ok': True}


# — Controle da tela ——————————————————————————————————————————————————————————
class TelaLigada(BaseModel):
    ligada: bool


@app.get('/tela')
async def ler_tela():
    """Se o Claude pode ver e controlar a tela (desligado até o Matheus ligar)."""
    from . import tela
    return {'ligada': tela.ligada(), 'disponivel': os.name == 'nt'}


@app.put('/tela')
async def ligar_tela(corpo: TelaLigada):
    from . import tela
    ligada = tela.ligar(corpo.ligada)
    banco.registrar_acao(None, 'controle_da_tela', {'ligada': corpo.ligada}, 'ligado' if ligada else 'desligado', True)
    return {'ligada': ligada, 'disponivel': os.name == 'nt'}


# — Uso da cota do Claude ————————————————————————————————————————————————————
@app.get('/uso')
async def ler_uso(atualizar: bool = False):
    """Quanto da cota do Claude já foi (a sessão de 5 horas, a semana) e quando
    volta, pelo /usage do CLI (não gasta cota). Guardado um minuto."""
    from . import uso
    try:
        return await uso.ler(atualizar)
    except uso.UsoIndisponivel as e:
        return JSONResponse({'erro': 'nao_deu', 'motivo': str(e)}, status_code=502)


# — Estilos de resposta ———————————————————————————————————————————————————————
class EstiloEscolha(BaseModel):
    id: str


class EstiloCorpo(BaseModel):
    nome: str
    instrucoes: str


@app.get('/estilos')
async def listar_estilos():
    """O estilo de resposta escolhido (`atual`) e os estilos: os prontos (Normal,
    Conciso, Explicativo, Formal) e os do Matheus (`seu`)."""
    return estilos.listar()


@app.put('/estilos/atual')
async def escolher_estilo(corpo: EstiloEscolha):
    try:
        return estilos.escolher(corpo.id)
    except estilos.EstiloInvalido:
        return JSONResponse({'erro': 'estilo_inexistente'}, status_code=404)


@app.post('/estilos')
async def criar_estilo(corpo: EstiloCorpo):
    try:
        return estilos.salvar(corpo.nome, corpo.instrucoes)
    except estilos.EstiloInvalido as e:
        return JSONResponse({'erro': 'estilo_invalido', 'motivo': str(e)}, status_code=400)


@app.put('/estilos/{id_}')
async def editar_estilo(id_: str, corpo: EstiloCorpo):
    try:
        return estilos.salvar(corpo.nome, corpo.instrucoes, id_)
    except estilos.EstiloInvalido as e:
        return JSONResponse({'erro': 'estilo_invalido', 'motivo': str(e)}, status_code=400)


@app.delete('/estilos/{id_}')
async def apagar_estilo(id_: str):
    if not estilos.apagar(id_):
        return JSONResponse({'erro': 'estilo_inexistente'}, status_code=404)
    return {'ok': True}


# — Servidores MCP ———————————————————————————————————————————————————————————
class ServidorCorpo(BaseModel):
    nome: str
    tipo: str
    comando: str = ''
    url: str = ''
    variaveis: str = ''
    para: list[str]


@app.get('/mcp')
async def listar_servidores_mcp():
    """Os servidores MCP do Claude (configuração de usuário do Claude Code) e do
    GPT (Codex): os seus, o da memória do Solis e os internos do Codex, com
    `para` e as `ferramentas` da última conferida."""
    from . import servidores_mcp
    return {'servidores': await asyncio.to_thread(servidores_mcp.listar)}


@app.get('/mcp/{nome}')
async def ler_servidor_mcp(nome: str):
    from . import servidores_mcp
    s = await asyncio.to_thread(servidores_mcp.ler, nome)
    return s if s else JSONResponse({'erro': 'servidor_inexistente'}, status_code=404)


async def _salvar_servidor(corpo: ServidorCorpo, antigo: str | None):
    from . import servidores_mcp
    try:
        s = await asyncio.to_thread(servidores_mcp.salvar, corpo.nome.strip(), corpo.tipo, corpo.comando,
                                    corpo.url.strip(), corpo.variaveis, corpo.para, antigo)
    except servidores_mcp.ServidorInvalido as e:
        return JSONResponse({'erro': 'servidor_invalido', 'motivo': str(e)}, status_code=400)
    # O registro de ações guarda sem os valores das variáveis (chave de API).
    banco.registrar_acao(None, 'salvar_servidor_mcp', {'nome': s['nome'], 'para': s['para'], 'antigo': antigo},
                         s['comando'] or s['url'], True)
    return s


@app.post('/mcp')
async def criar_servidor_mcp(corpo: ServidorCorpo):
    return await _salvar_servidor(corpo, None)


@app.put('/mcp/{nome}')
async def editar_servidor_mcp(nome: str, corpo: ServidorCorpo):
    return await _salvar_servidor(corpo, nome)


@app.delete('/mcp/{nome}')
async def remover_servidor_mcp(nome: str):
    from . import servidores_mcp
    try:
        ok = await asyncio.to_thread(servidores_mcp.remover, nome)
    except servidores_mcp.ServidorInvalido as e:
        return JSONResponse({'erro': 'servidor_invalido', 'motivo': str(e)}, status_code=400)
    if not ok:
        return JSONResponse({'erro': 'servidor_inexistente'}, status_code=404)
    banco.registrar_acao(None, 'remover_servidor_mcp', {'nome': nome}, 'removido', True)
    return {'ok': True}


@app.post('/mcp/{nome}/conferir')
async def conferir_servidor_mcp(nome: str):
    """Conecta no servidor e lista as ferramentas (quantas, quantas só leem, ou o erro)."""
    from . import servidores_mcp
    try:
        return await servidores_mcp.conferir(nome)
    except servidores_mcp.ServidorInvalido:
        return JSONResponse({'erro': 'servidor_inexistente'}, status_code=404)


@app.post('/mcp/{nome}/entrar')
async def entrar_servidor_mcp(nome: str, request: Request):
    """Começa o login (OAuth) num servidor por endereço: devolve `url`, a
    página de login, pra tela abrir no navegador. O serviço volta pra
    /mcp/oauth/volta; a tela acompanha por GET /mcp/{nome}/entrar."""
    from . import mcp_oauth, servidores_mcp
    s = await asyncio.to_thread(servidores_mcp.ler, nome)
    if not s or s['tipo'] != 'endereco':
        return JSONResponse({'erro': 'servidor_inexistente'}, status_code=404)
    volta = str(request.base_url).rstrip('/') + mcp_oauth.VOLTA
    try:
        url = await mcp_oauth.comecar(nome, s['url'], volta, ao_terminar=servidores_mcp.depois_de_entrar)
    except mcp_oauth.PrecisaEntrar as e:
        return JSONResponse({'erro': 'login', 'motivo': str(e)}, status_code=400)
    banco.registrar_acao(None, 'entrar_servidor_mcp', {'nome': nome}, s['url'], True)
    # O navegador padrão do Windows, aberto pelo servidor do Solis (a janela do
    # app não abre página de fora). A tela também recebe o endereço.
    await asyncio.to_thread(_abrir_no_navegador, url)
    return {'url': url}


def _abrir_no_navegador(url: str) -> None:
    import webbrowser
    webbrowser.open(url)


@app.get('/mcp/{nome}/entrar')
async def situacao_do_login_mcp(nome: str):
    from . import mcp_oauth
    return mcp_oauth.situacao(nome)


@app.get('/mcp/oauth/volta')
async def volta_do_login_mcp(code: str | None = None, state: str | None = None, error: str | None = None):
    """Pra onde o serviço manda o navegador depois do login: entrega o código
    pro Solis terminar e diz ao Matheus que pode voltar."""
    from html import escape

    from fastapi.responses import HTMLResponse

    from . import mcp_oauth
    nome = mcp_oauth.voltou(state, code, error)
    if nome is None:
        texto = 'Esse login não estava sendo esperado pelo Solis (ou já terminou). Tente "Entrar" de novo.'
    elif error:
        texto = f'O serviço recusou o login em "{nome}". Pode fechar esta aba e tentar de novo no Solis.'
    else:
        texto = f'Pronto: o Solis entrou em "{nome}". Pode fechar esta aba e voltar pro Solis.'
    return HTMLResponse('<!doctype html><meta charset="utf-8"><title>Solis</title>'
                        '<body style="font-family:system-ui,sans-serif;margin:15vh auto;max-width:32rem;'
                        f'padding:0 1rem;line-height:1.5">{escape(texto)}</body>')


# — Hooks do Claude (hooks.py) —————————————————————————————————————————————————
class HookCorpo(BaseModel):
    evento: str
    ferramenta: str = ''
    comando: str
    tempo: float | None = None


@app.get('/hooks')
async def listar_hooks():
    """Os hooks do Claude (~/.claude/settings.json) e os eventos que a tela oferece."""
    from . import hooks
    try:
        lista = await asyncio.to_thread(hooks.listar)
    except hooks.HookInvalido as e:
        return JSONResponse({'erro': 'hook_invalido', 'motivo': str(e)}, status_code=409)
    return {'hooks': lista, 'eventos': [{'id': k, 'rotulo': v, 'ferramenta': k in hooks.COM_FERRAMENTA}
                                        for k, v in hooks.EVENTOS.items()]}


async def _salvar_hook(corpo: HookCorpo, antigo: str | None):
    from . import hooks
    try:
        h = await asyncio.to_thread(hooks.salvar, corpo.evento, corpo.ferramenta, corpo.comando, corpo.tempo, antigo)
    except hooks.HookInvalido as e:
        return JSONResponse({'erro': 'hook_invalido', 'motivo': str(e)}, status_code=400)
    banco.registrar_acao(None, 'salvar_hook', {'evento': h['evento'], 'ferramenta': h['ferramenta'], 'antigo': antigo},
                         h['comando'], True)
    return h


@app.post('/hooks')
async def criar_hook(corpo: HookCorpo):
    return await _salvar_hook(corpo, None)


@app.post('/hooks/testar')
async def testar_hook(corpo: HookCorpo):
    """Roda o comando do hook uma vez, como o Claude Code rodaria (o Git Bash,
    o exemplo do evento na entrada), sem salvar: o código de saída e o que ele
    escreveu, com o efeito em português. O Matheus clicou em Testar: roda de
    verdade, então fica no registro de ações."""
    from . import hooks
    try:
        r = await asyncio.to_thread(hooks.testar, corpo.evento, corpo.ferramenta, corpo.comando, corpo.tempo)
    except hooks.HookInvalido as e:
        return JSONResponse({'erro': 'hook_invalido', 'motivo': str(e)}, status_code=400)
    banco.registrar_acao(None, 'testar_hook', {'evento': corpo.evento, 'ferramenta': corpo.ferramenta},
                         corpo.comando, r['codigo'] == 0)
    return r


@app.put('/hooks/{id_}')
async def editar_hook(id_: str, corpo: HookCorpo):
    return await _salvar_hook(corpo, id_)


@app.delete('/hooks/{id_}')
async def remover_hook(id_: str):
    from . import hooks
    try:
        h = await asyncio.to_thread(hooks.remover, id_)
    except hooks.HookInvalido as e:
        return JSONResponse({'erro': 'hook_invalido', 'motivo': str(e)}, status_code=404)
    banco.registrar_acao(None, 'remover_hook', {'evento': h['evento'], 'ferramenta': h['ferramenta']}, h['comando'], True)
    return {'ok': True}


# — Navegador do Claude ————————————————————————————————————————————————————————
class EscolhaNavegador(BaseModel):
    navegador: str


@app.get('/navegador')
async def ler_navegador():
    """Qual navegador o Claude usa (`escolhido`: chrome, msedge ou None), os
    que estão no PC, se está `desligado` e se a janela está `aberto`."""
    from . import navegador
    return navegador.estado()


@app.put('/navegador')
async def escolher_navegador(corpo: EscolhaNavegador):
    """chrome, msedge ou desligado. Trocar fecha a janela do outro."""
    from . import navegador
    try:
        r = await asyncio.to_thread(navegador.escolher, corpo.navegador)
    except ValueError:
        return JSONResponse({'erro': 'navegador_invalido'}, status_code=400)
    banco.registrar_acao(None, 'escolher_navegador', {'navegador': corpo.navegador}, corpo.navegador, True)
    return r


class ChaveNavegador(BaseModel):
    chave: str = ''


@app.put('/navegador/chave')
async def guardar_chave_navegador(corpo: ChaveNavegador):
    """A chave da extensão do Playwright (o Matheus cola): com ela, o navegador
    de sempre liga sem pedir. Vazia apaga. Vai pro cofre; nunca volta pela API."""
    from . import navegador
    r = await asyncio.to_thread(navegador.guardar_chave, corpo.chave)
    banco.registrar_acao(None, 'chave_navegador', {}, 'guardada' if corpo.chave.strip() else 'apagada', True)
    return r


@app.post('/navegador/abrir')
async def abrir_navegador():
    """Abre a janela do navegador do Solis — pra entrar nas contas que o Claude
    vai usar (os logins ficam no perfil do Solis)."""
    from . import navegador
    try:
        await asyncio.to_thread(navegador.abrir)
    except navegador.NavegadorFalhou as e:
        return JSONResponse({'erro': 'nao_abriu', 'motivo': str(e)}, status_code=503)
    return navegador.estado()


# — Git da pasta de projeto ————————————————————————————————————————————————————
def _pasta_git(conversa: int) -> str | None:
    return banco.projeto_da_conversa(conversa)['pasta']


async def _git_acao(conversa: int, nome: str, funcao, *args):
    """Commit, push e PR: o Matheus clicou; vai pro registro de ações."""
    from . import git
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    pasta = _pasta_git(conversa)
    if not pasta:
        return JSONResponse({'erro': 'sem_projeto'}, status_code=400)
    try:
        r = await asyncio.to_thread(funcao, pasta, *args)
    except git.GitFalhou as e:
        banco.registrar_acao(conversa, f'git_{nome}', {'pasta': pasta}, f'não deu: {e}', False)
        return JSONResponse({'erro': 'git', 'motivo': str(e)}, status_code=400)
    banco.registrar_acao(conversa, f'git_{nome}', {'pasta': pasta, **({'mensagem': args[0]} if args else {})},
                         json.dumps(r, ensure_ascii=False), True)
    return r


@app.get('/conversas/{conversa}/git')
async def ler_git(conversa: int):
    """O git da pasta de projeto: ramo, upstream, à frente/atrás e os arquivos
    mudados com as linhas. `repo: false` sem projeto ou fora de um repositório."""
    from . import git
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    pasta = _pasta_git(conversa)
    if not pasta:
        return {'repo': False}
    try:
        return await asyncio.to_thread(git.estado, pasta)
    except git.GitFalhou as e:
        return JSONResponse({'erro': 'git', 'motivo': str(e)}, status_code=400)


@app.get('/conversas/{conversa}/git/diff')
async def ler_git_diff(conversa: int, arquivo: str):
    from . import git
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    pasta = _pasta_git(conversa)
    if not pasta:
        return JSONResponse({'erro': 'sem_projeto'}, status_code=400)
    try:
        return {'diff': await asyncio.to_thread(git.diff, pasta, arquivo)}
    except git.GitFalhou as e:
        return JSONResponse({'erro': 'git', 'motivo': str(e)}, status_code=400)


class Commit(BaseModel):
    mensagem: str


@app.post('/conversas/{conversa}/git/commit')
async def git_commit(conversa: int, corpo: Commit):
    """Tudo que mudou num commit, com a mensagem. Os hooks do projeto rodam."""
    from . import git
    return await _git_acao(conversa, 'commit', git.commit, corpo.mensagem)


@app.post('/conversas/{conversa}/git/push')
async def git_push(conversa: int):
    from . import git
    return await _git_acao(conversa, 'push', git.push)


@app.post('/conversas/{conversa}/git/pr')
async def git_pr(conversa: int):
    """O PR do ramo atual, pelo gh (precisa estar instalado e logado)."""
    from . import git
    return await _git_acao(conversa, 'pr', git.pr)


# — Segundo plano ——————————————————————————————————————————————————————————————
@app.get('/conversas/{conversa}/fundo')
async def ler_fundo(conversa: int):
    """Os comandos que o Claude deixou rodando em segundo plano nesta conversa,
    com o fim da saída, e a resposta que ele começou sozinho quando um acabou
    (`resposta`: texto e etapas até agora; null se não há). A tela lê isto a
    cada 1,5 s enquanto houver algo — não há stream aberto pra isso."""
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    try:
        from . import agente
    except ImportError:
        return {'comandos': [], 'resposta': None, 'aprovacoes': []}
    return await asyncio.to_thread(agente.fundo, conversa)


@app.post('/conversas/{conversa}/fundo/{tarefa}/parar')
async def parar_fundo(conversa: int, tarefa: str):
    from . import agente
    if not await agente.parar_fundo(conversa, tarefa):
        return JSONResponse({'erro': 'nada_rodando'}, status_code=404)
    return {'ok': True}


# — Voltar atrás ———————————————————————————————————————————————————————————————
class Volta(BaseModel):
    # A fala da pessoa: os arquivos voltam a como estavam antes dela.
    desde: int
    # Só dizer o que voltaria (a tela mostra antes de confirmar).
    simular: bool = False
    # A conversa volta junto: a fala `desde` e o que veio depois saem.
    conversa: bool = False


@app.get('/conversas/{conversa}/voltar')
async def ler_volta(conversa: int):
    """A última fala depois da qual o Claude mudou arquivo: dela pra trás, toda
    fala da pessoa tem o "voltar atrás" (null: nada pra voltar)."""
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    # A do Claude (o checkpoint do CLI) ou a dos outros cérebros (as cópias do corpo).
    ultimas = [u for u in (banco.ultimo_ponto_mudado(conversa), banco.ultima_copia(conversa)) if u is not None]
    return {'ultima': max(ultimas) if ultimas else None}


@app.post('/conversas/{conversa}/voltar')
async def voltar_atras(conversa: int, corpo: Volta):
    """O que o Claude mudou nos arquivos da fala `desde` em diante volta — pelo
    próprio CLI (agente.voltar). Comandos que ele rodou não voltam."""
    if not banco.existe(conversa):
        return JSONResponse({'erro': 'conversa_inexistente'}, status_code=404)
    if conversa in _paradas:
        return JSONResponse({'erro': 'respondendo'}, status_code=409)
    if corpo.conversa and not banco.mensagem_da_pessoa(conversa, corpo.desde):
        return JSONResponse({'erro': 'mensagem_inexistente'}, status_code=404)
    pontos = banco.pontos_desde(conversa, corpo.desde)
    copias = banco.copias_desde(conversa, corpo.desde)
    r = {'arquivos': [], 'mais': 0, 'menos': 0, 'erros': []}

    async def do_claude():
        from . import agente
        return await agente.voltar(pontos, simular=corpo.simular)

    async def dos_outros():
        # As edições da Groq, do Gemini... pelo corpo (editar.py): as cópias do Solis.
        from . import editar
        return await asyncio.to_thread(editar.voltar, copias, corpo.simular)

    # Um arquivo que o Claude e outro cérebro mudaram tem que terminar como
    # estava antes da PRIMEIRA mudança: volta antes quem começou depois.
    partes = [(min(p['mensagem'] for p in pontos), do_claude)] if pontos else []
    if copias:
        partes.append((banco.primeira_copia(conversa, corpo.desde), dos_outros))
    for _, parte in sorted(partes, key=lambda x: x[0], reverse=True):
        try:
            uma = await parte()
        except Exception as e:  # noqa: BLE001 — o CLI do Claude falhou: vira 502, como antes
            return JSONResponse({'erro': 'nao_deu', 'motivo': str(e)[:300]}, status_code=502)
        r['arquivos'] += [a for a in uma['arquivos'] if a not in r['arquivos']]
        r['mais'] += uma['mais']
        r['menos'] += uma['menos']
        r['erros'] += uma['erros']
    if corpo.simular:
        return r
    if (pontos or copias) and not r['erros']:
        banco.limpar_pontos(conversa, corpo.desde)
    if r['arquivos']:
        banco.registrar_acao(conversa, 'voltar_atras', {'desde': corpo.desde, 'arquivos': r['arquivos']},
                             f'voltaram {len(r["arquivos"])} arquivo(s)', not r['erros'])
    if corpo.conversa and not r['erros']:
        # Com erro, a conversa fica: é nela que se vê o que não voltou.
        banco.apagar_desde(conversa, corpo.desde)
        banco.esquecer_sessao_claude(conversa)
    return r


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
    pesquisa: bool = False,
    agendada: str = '',
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
            fim(cerebro='solis', mensagem=resposta_id)
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
                                   texto + roteador.nota_anexos(anexos) + (roteador.NOTA_PESQUISA if pesquisa else '')
                                   + roteador.nota_agendada(agendada) + estilos.nota(),
                                   etapas, voz=voz),
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
        fim(cerebro=cerebro, **({'mensagem': resposta_id} if resposta_id else {}),
            **({'cortada': True} if cortada else {}), **({'parada': True} if parada else {}))

        try:
            await _depois(etapas, modelo, conversa, texto, historico, mensagem_id, ''.join(resposta))
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
        # O registro de uso conta até a tentativa sem resposta (as quedas).
        try:
            banco.registrar_usos(resposta_id, etapas.lista)
        except Exception:
            log.exception('conversa %s: o registro de uso falhou', conversa)
        etapas.encerrar()


async def _depois(etapas: Etapas, modelo: str, conversa: int, texto: str, historico: list[dict], mensagem_id: int,
                  resposta: str = ''):
    """Depois que a resposta terminou de chegar, nesta ordem: dar título (se a
    conversa ainda não tem — é rápido, e a lista do painel troca a primeira
    fala por ele), aprender (extrair memórias da mensagem), indexar (vetorizar
    o que entrou, inclusive a memória que acabou de nascer) e resumir (se a
    conversa passou do lote). A tela já
    liberou a conversa no `fim`; estas etapas chegam pelo mesmo stream, que só
    fecha depois delas. O contexto do aprendizado são as duas falas antes da
    mensagem nova (a pergunta do Solis que ela talvez responda), não o histórico
    inteiro.

    Rodam no modelo local, qualquer que seja o cérebro que respondeu: leem
    tudo, inclusive o que é privado, e não gastam cota. E no modelo de fundo
    (MODELO_FUNDO), não no da conversa. A exceção (16/11/2026, decisão do
    Matheus): com o Ollama fora, o aprendizado do que não é privado vai pra
    Groq (memoria.aprender) — senão nada era guardado.

    Quando o Solis respondeu que não entendeu, não aprende (a não ser que
    seja um pedido de guardar): a mensagem não era pra ele ou chegou errada."""
    modelo = await _modelo_de_fundo(modelo)
    if titulo := await resumo.titular(modelo, conversa):
        etapas.marcar('titulo', titulo=titulo)
    criadas: list[dict] = list(etapas.anotadas)
    marcados: list[dict] = []
    if memoria.nao_entendeu(resposta) and not memoria.eh_pedido(texto):
        novas = []
    else:
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
    return {'disponivel': voz.disponivel(), 'modelo': voz.modelo_em_uso() or voz.MODELO}


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


@app.get('/fala/frase/{nome}')
async def falar_frase(nome: str):
    """Uma frase fixa do Solis (fala.FRASES): gravada uma vez com a voz
    escolhida, depois sai do disco. É o que a tela fala enquanto o Claude
    trabalha num pedido de voz."""
    if nome not in fala.FRASES:
        return JSONResponse({'erro': 'frase_inexistente'}, status_code=404)
    try:
        audio, tipo, quem = await fala.frase(nome)
    except fala.SemVoz as e:
        return JSONResponse({'erro': 'sem_voz', 'motivo': str(e)}, status_code=503)
    return Response(audio, media_type=tipo, headers={'X-Solis-Voz': quem, 'Cache-Control': 'no-store'})


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
    # A conexão com a Groq e com a Fish abre agora, enquanto a pessoa fala:
    # a resposta não paga o TLS (conexoes.py).
    from . import apis, conexoes
    conexoes.aquecer(*[n for n, tem in (('groq', apis._chave_de('groq')), ('fish', fala.chave_fish())) if tem])
    # Depois de o servidor reiniciar, o da última vez (guardado).
    modelo = _ultimo_modelo or banco.ajuste('modelo_local')
    if modelo:
        tarefa = asyncio.create_task(ollama.aquecer(modelo))
        _tarefas.add(tarefa)
        tarefa.add_done_callback(_tarefas.discard)


def _palavra_sombra():
    """O ouvido da palavra treinada pra escuta em modo sombra, ou None (sem o
    modelo, ou SOLIS_PALAVRA_SOMBRA=0)."""
    if os.environ.get('SOLIS_PALAVRA_SOMBRA', '1') == '0':
        return None
    try:
        return palavra.Ouvido(palavra.MODELO_SOLIS)
    except palavra.SemModelo as e:
        log.info('escuta: sem a palavra treinada (%s)', e)
    except Exception:  # noqa: BLE001 — a sombra nunca impede a escuta
        log.exception('escuta: a palavra treinada não abriu')
    return None


def _aquecer_whisper(pequeno: bool = False) -> None:
    """Sobe (em segundo plano) quem vai conferir a palavra: o Whisper pequeno
    com a Groq transcrevendo o pedido (transcricao.py), ou o turbo daqui (offline)."""
    async def aquecer():
        try:
            await asyncio.to_thread(transcricao.aquecer_pequeno if pequeno else voz.aquecer)
        except voz.SemModelo:
            pass
        except Exception:
            log.exception('o whisper não aqueceu')
    tarefa = asyncio.create_task(aquecer())
    _tarefas.add(tarefa)
    tarefa.add_done_callback(_tarefas.discard)


async def _transcrever_escuta(tipo: str, audio: bytes) -> str:
    """Online primeiro (transcricao.py): o "Solis" conferido aqui pelo Whisper
    pequeno, o pedido no Whisper da Groq; sem a Groq, o turbo daqui."""
    try:
        texto = await transcricao.escuta(tipo, audio)
    except (voz.SemModelo, voz.AudioRuim):
        texto = ''
    if ESCUTA_LOG:
        log.info('escuta: %.1f s -> %r', (len(audio) - 44) / 2 / ativacao.TAXA, texto)
    return texto


# — Teste da escuta (voz_teste.py) ——————————————————————————————————————————————
_medindo: dict[str, asyncio.Task] = {}


@app.post('/aprendizado/teste')
async def testar_aprendizado(onde: str = 'groq', modelo: str = '', pausa: float = 0.0):
    """O teste do aprendizado (aprendizado_teste.py): casos inventados pela
    extração, sem guardar nada. `onde`: 'local' ou 'groq'. `pausa`: segundos
    entre um caso e outro (o limite grátis da Groq é por minuto)."""
    from . import aprendizado_teste
    if onde not in ('local', 'groq'):
        return JSONResponse({'erro': 'onde_invalido'}, status_code=400)
    modelo = modelo or (MODELO_FUNDO if onde == 'local' else memoria.MODELO_NUVEM)
    r = await aprendizado_teste.medir(onde, modelo, pausa)
    from . import qualidade
    qualidade.guardar_teste_aprendizado(r['resumo'])
    return r


# — Qualidade (qualidade.py): a taxa de acerto por função ———————————————————————
class Voto(BaseModel):
    voto: Literal[1, -1] | None = None


@app.get('/qualidade')
async def ver_qualidade(dias: int = 30):
    """Por função: quantas vezes rodou e deu certo, os votos, as últimas falhas;
    e os testes de qualidade com meta."""
    from . import qualidade
    return await asyncio.to_thread(qualidade.relatorio, max(1, min(dias, 3650)))


@app.put('/mensagens/{mensagem}/voto')
async def votar(mensagem: int, corpo: Voto):
    """O 👍/👎 numa resposta (null tira). 404 se não é resposta de um cérebro."""
    if not banco.votar(mensagem, corpo.voto):
        return JSONResponse({'erro': 'resposta_inexistente'}, status_code=404)
    return {'ok': True, 'voto': corpo.voto}


@app.get('/voz/teste/roteiro')
async def roteiro_do_teste():
    """O roteiro do teste da escuta: cada frase, o tipo (chamada ou sem "Solis")
    e a janela em segundos da gravação."""
    from . import voz_teste
    return voz_teste.roteiro()


@app.get('/voz/teste')
async def listar_testes():
    from . import voz_teste
    return {'testes': await asyncio.to_thread(voz_teste.listar),
            'medindo': [i for i, t in _medindo.items() if not t.done()]}


@app.post('/voz/teste')
async def guardar_teste(request: Request):
    """A gravação (WAV 16 kHz mono no corpo) e, no cabeçalho X-Solis-Roteiro, os
    tempos de verdade de cada frase. Já começa a medir com a escuta de hoje."""
    from urllib.parse import unquote

    from . import voz_teste
    try:
        passos = json.loads(unquote(request.headers.get('x-solis-roteiro', ''))) or None
    except ValueError:
        passos = None
    try:
        r = await asyncio.to_thread(voz_teste.guardar, await request.body(), passos)
    except voz_teste.TesteInvalido as e:
        return JSONResponse({'erro': 'teste_invalido', 'motivo': str(e)}, status_code=400)
    # A escuta como está, e a com o Silero VAD: a decisão sai da voz dele.
    _comecar_medida(r['id'], 'atual', 'silero')
    return r


def _comecar_medida(id_: str, *motores: str) -> None:
    from . import voz_teste

    async def medir():
        for motor in motores:  # uma de cada vez: o Whisper é um só
            try:
                await voz_teste.medir(id_, motor)
            except Exception:
                log.exception('a medida %s do teste da escuta %s falhou', motor, id_)
    _medindo[id_] = asyncio.create_task(medir())


@app.post('/voz/teste/{id_}/medir')
async def medir_teste(id_: str, motor: str = 'atual'):
    from . import voz_teste
    if not (voz_teste.pasta() / id_ / 'gravacao.wav').is_file():
        return JSONResponse({'erro': 'teste_inexistente'}, status_code=404)
    if id_ in _medindo and not _medindo[id_].done():
        return {'medindo': True}
    _comecar_medida(id_, motor)
    return {'medindo': True}


@app.get('/voz/teste/{id_}/medida/{motor}')
async def ler_medida(id_: str, motor: str):
    from . import voz_teste
    arquivo = voz_teste.pasta() / id_ / f'medida-{motor}.json'
    if not re.match(r'^[0-9-]+$', id_) or not re.match(r'^[a-z0-9-]+$', motor) or not arquivo.is_file():
        return JSONResponse({'erro': 'medida_inexistente'}, status_code=404)
    return json.loads(arquivo.read_text(encoding='utf-8'))


@app.websocket('/escuta')
async def escuta(ws: WebSocket):
    """O microfone aberto do navegador: áudio PCM 16 bits, 16 kHz, mono, em
    pedaços binários. Primeiro {"tipo": "pronta"} (ou {"tipo": "erro"} e fecha);
    a tela só abre o microfone depois. Volta {"tipo": "ativou"} ao ouvir a palavra e, quando a
    pessoa para de falar, {"tipo": "texto", "texto"} (ou {"tipo": "nada"}).
    Texto {"pausa": true} do navegador suspende a escuta — enquanto o Solis
    fala, a voz dele não pode acordar ele mesmo. {"pausa": false, "seguir": true}
    quando a fala dele acabou numa pergunta: o pedido abre sem o "Solis" (volta
    {"tipo": "ativou"}, e o resto como depois da palavra)."""
    await ws.accept()
    try:
        escutando = await asyncio.to_thread(ativacao.Escuta)
    except Exception as e:
        await ws.send_json({'tipo': 'erro', 'motivo': str(e)[:300]})
        await ws.close()
        return
    # Quem confere a palavra já sobe agora: frio, o primeiro "Solis" esperava
    # ~7 s pela decisão (16/11/2026). Online (a Groq transcreve o pedido), é o
    # Whisper pequeno (453 MB da placa); offline, o turbo (1,2 GB). Com a escuta
    # rápida ligada (?segurar=1, o padrão; Configurações → Voz), ele fica
    # carregado enquanto a escuta estiver aberta (17/11/2026: a opção é do Matheus).
    pequeno = transcricao.online() and transcricao.pequeno_disponivel()
    segurado = (transcricao if pequeno else voz) if ws.query_params.get('segurar', '1') != '0' else None
    if segurado:
        segurado.segurar()
    _aquecer_whisper(pequeno)
    pausada = cedida = False
    pausou_em = 0.0
    log.info('escuta: conectada')
    # A palavra treinada em modo sombra (21/11/2026): ouve junto com o Whisper e
    # só anota no log quando acordaria — e, a cada ativação do Whisper, se ela
    # também ouviu. Um dia de uso em casa mede as duas lado a lado antes de ela
    # decidir sozinha. SOLIS_PALAVRA_SOMBRA=0 tira.
    sombra = await asyncio.to_thread(_palavra_sombra)
    sombra_ultimo = sombra_disparo = -99.0
    sombra_seguidas, sombra_pico = 0, 0.0
    # Outro programa no microfone (o Discord numa chamada): a tela solta o
    # microfone e o som da escuta, e volta quando ele soltar (microfone.py).
    fila = microfone.vigia.entrar()
    vigiando = None

    async def vigiar():
        nonlocal cedida
        while True:
            outros = await fila.get()
            if not microfone.CEDER:
                continue  # a escuta continua junto (microfone.CEDER)
            if outros and not cedida:
                cedida = True
                await ws.send_json({'tipo': 'ceder', 'por': outros})
            elif not outros and cedida:
                cedida = False
                await ws.send_json({'tipo': 'retomar'})
    try:
        # Quem está no microfone agora, antes da tela abrir o dela.
        await microfone.vigia.primeira_leitura()
        if microfone.vigia.outros and microfone.CEDER:
            cedida = True
            await ws.send_json({'tipo': 'ceder', 'por': microfone.vigia.outros})
        vigiando = asyncio.create_task(vigiar())
        # A tela só abre o microfone depois disto: escuta que não funciona (falta o
        # modelo, por exemplo) não pode deixar o microfone do PC aberto à toa.
        await ws.send_json({'tipo': 'pronta'})
        while True:
            msg = await ws.receive()
            if msg.get('type') == 'websocket.disconnect':
                break
            if msg.get('text'):
                try:
                    pedido = json.loads(msg['text'])
                except ValueError:
                    continue
                agora_pausada = bool(pedido.get('pausa'))
                # Relato do Matheus (20/11/2026): chamou, o Solis respondeu, e na
                # vez seguinte o "Solis" não acordou mais — e o log não dizia se
                # a escuta estava pausada (o Solis falando) ou se ouviu e não
                # reconheceu. Agora diz quando pausa e quanto tempo ficou.
                if agora_pausada and not pausada:
                    pausou_em = time.monotonic()
                    log.info('escuta: pausada (o Solis falando)')
                elif pausada and not agora_pausada:
                    log.info('escuta: voltou a ouvir depois de %.1f s pausada', time.monotonic() - pausou_em)
                pausada = agora_pausada
                # A fala dele acabou numa pergunta: ouve a resposta sem o "Solis".
                if pedido.get('seguir') and not pausada and escutando.seguir():
                    await ws.send_json({'tipo': 'ativou'})
                    _aquecer()
                continue
            if pausada or cedida or not msg.get('bytes'):
                continue
            if sombra is not None:
                try:
                    notas = await asyncio.to_thread(sombra.alimentar, np.frombuffer(msg['bytes'][:len(msg['bytes']) // 2 * 2],
                                                                                 dtype=np.int16))
                except Exception:  # noqa: BLE001 — a sombra nunca derruba a escuta
                    log.exception('escuta: a palavra treinada falhou; segue sem ela')
                    notas, sombra = [], None
                for nota in notas:
                    sombra_ultimo += 0.08
                    sombra_seguidas = sombra_seguidas + 1 if nota >= palavra.LIMIAR_SOLIS else 0
                    sombra_pico = max(sombra_pico, nota) if sombra_seguidas else 0.0
                    if sombra_seguidas >= palavra.PACIENCIA and sombra_ultimo - sombra_disparo > 1.5:
                        sombra_disparo = sombra_ultimo
                        log.info('escuta: a palavra treinada acordaria (nota %.2f)', sombra_pico)
            # Gerador: cada decisão (confirmar/descartar) vale já pro quadro seguinte.
            for tipo, audio in escutando.alimentar(msg['bytes']):
                if tipo == 'ativou':
                    await ws.send_json({'tipo': 'ativou'})
                    _aquecer()
                elif tipo in ('previa', 'frase'):
                    # Whisper: o começo de um trecho de fala tem "Solis"?
                    t0 = time.monotonic()
                    ouvido = await _transcrever_escuta(tipo, audio)
                    achou, resto = ativacao.palavra_no_inicio(ouvido)
                    demora = time.monotonic() - t0
                    if demora > 1.5:
                        # Sem o que foi dito: só quanto demorou (pra achar chamada perdida).
                        log.info('escuta: a decisão do trecho demorou %.1f s', demora)
                    if not achou:
                        # Só a palavra mais parecida com "Solis" (quando parece), nunca
                        # o resto do que foi dito: pra ver o "Solis" que não acordou.
                        perto = ativacao.mais_perto(ouvido)
                        log.info('escuta: %.1f s de fala sem "Solis"%s', (len(audio) - 44) / 2 / ativacao.TAXA,
                                 f' (o mais parecido: {perto!r})' if perto else '')
                        escutando.descartar()
                        continue
                    # Só o pedaço que valeu como "Solis", nunca o resto do que foi
                    # dito: pra achar a próxima ativação sem chamada (19/11/2026).
                    log.info('escuta: ativou com %r', ativacao.como_chamou(ouvido))
                    if sombra is not None:
                        log.info('escuta: a palavra treinada %s', 'também ouviu' if sombra_ultimo - sombra_disparo < 4
                                 else 'NÃO ouviu')
                    # "Solis, ." (o ruído virou ponto): vale como só "Solis".
                    resto = resto if ativacao.tem_fala(resto) else ''
                    await ws.send_json({'tipo': 'ativou'})
                    _aquecer()
                    pronto = escutando.confirmar(atraso=demora, resto=resto if tipo == 'frase' else '')
                    if pronto:
                        # "Solis, que horas são?" de uma vez, e acabou: já é o comando.
                        await ws.send_json({'tipo': 'texto', 'texto': pronto})
                elif tipo == 'rascunho':
                    # A cascata: calado há pouco, o texto adianta; vale se ele não voltar a falar.
                    _, texto = ativacao.palavra_no_inicio(await _transcrever_escuta(tipo, audio))
                    escutando.guardar_rascunho(texto)
                elif audio is None:
                    await ws.send_json({'tipo': 'nada'})
                else:
                    # Com o rascunho valendo, o texto já está pronto; senão, o Whisper agora.
                    # O comando pode trazer a própria palavra no começo (veio do trecho).
                    texto = escutando.pronto
                    if texto is None:
                        _, texto = ativacao.palavra_no_inicio(await _transcrever_escuta(tipo, audio))
                    # Sem palavra nenhuma (o "." do ruído), não vira mensagem.
                    await ws.send_json({'tipo': 'texto', 'texto': texto} if ativacao.tem_fala(texto) else {'tipo': 'nada'})
    except WebSocketDisconnect:
        pass
    finally:
        if vigiando is not None:
            vigiando.cancel()
        microfone.vigia.sair(fila)
        log.info('escuta: desconectada' + (' (estava pausada)' if pausada else ''))
        escutando.fechar()
        if segurado:
            segurado.soltar()


# — O modo Conversa (conversa_voz.py) ——————————————————————————————————————————————

@app.websocket('/conversa-voz')
async def conversa_por_voz(ws: WebSocket):
    """O bate-papo por voz em tempo real (Gemini Live). A tela manda o microfone
    (PCM 16 bits, 16 kHz) em pedaços binários e {"fim": true} pra sair; recebe
    {"tipo": "pronta", "conversa"}, a voz dele (PCM 16 bits, 24 kHz, binário),
    {"tipo": "ouviu"|"disse", "texto"}, {"tipo": "interrompido"}, {"tipo":
    "turno"} (uma troca salva na conversa) e {"tipo": "fim", "motivo"}.

    Sem o Gemini (sem chave, a faixa grátis acabou, caiu no meio), segue pela
    reserva da Groq (conversa_voz.conduzir_reserva), com {"tipo": "reserva"}
    avisando a tela; o resto da conversa é igual."""
    from . import conversa_voz
    await ws.accept()
    q = ws.query_params.get('conversa', '')
    conversa = int(q) if q.isdigit() else banco.nova_conversa()
    reserva = conversa_voz.reserva_disponivel()
    sessao_cm = None
    if not conversa_voz.gemini_descansando():
        try:
            sessao_cm = conversa_voz.abrir(conversa, fala.voz_gemini())
        except conversa_voz.SemChave as e:
            if not reserva:
                await ws.send_json({'tipo': 'erro', 'motivo': str(e)})
                await ws.close()
                return
    elif not reserva:
        await ws.send_json({'tipo': 'erro', 'motivo': 'o Gemini falhou há pouco e a Groq não está disponível'})
        await ws.close()
        return
    pronta = False

    async def avisar_pronta() -> None:
        nonlocal pronta
        if not pronta:
            pronta = True
            await ws.send_json({'tipo': 'pronta', 'conversa': conversa})

    async def receber() -> dict:
        msg = await ws.receive()
        if msg.get('type') == 'websocket.disconnect':
            return {'saiu': True}
        if msg.get('bytes'):
            return {'audio': msg['bytes']}
        if msg.get('text'):
            try:
                return {'fim': True} if json.loads(msg['text']).get('fim') else {}
            except ValueError:
                return {}
        return {}

    async def ao_turno(fala_dele: str, resposta: str, cerebro: str = 'gemini-live') -> None:
        id_pessoa, _ = conversa_voz.salvar_turno(conversa, fala_dele, resposta, cerebro)
        if fala_dele and id_pessoa:
            # O aprendizado, como no modo Pedido: o que ele disse pode virar memória.
            async def aprender():
                modelo = await _modelo_de_fundo(MODELO_FUNDO)
                await memoria.aprender(modelo, conversa, fala_dele, [], id_pessoa)
            tarefa = asyncio.create_task(aprender())
            _tarefas.add(tarefa)
            tarefa.add_done_callback(_tarefas.discard)

    async def local(instrucao: str, texto: str) -> str:
        # O privado, pela reserva: o modelo daqui, nunca a nuvem.
        return await ollama.responder_texto(await _modelo_de_fundo(MODELO_FUNDO), instrucao, texto, pensar=False)

    motivo = 'erro' if sessao_cm is None else ''
    if sessao_cm is not None:
        try:
            async with sessao_cm as sessao:
                await avisar_pronta()
                motivo = await conversa_voz.conduzir(sessao, receber, ws.send_bytes, ws.send_json, ao_turno)
        except WebSocketDisconnect:
            motivo = 'saiu'
        except Exception as e:  # noqa: BLE001 — a conexão com o Gemini caiu ou recusou
            log.warning('o modo conversa não abriu ou caiu: %s', e)
            motivo = 'erro'
            if not reserva:
                with contextlib.suppress(Exception):
                    await ws.send_json({'tipo': 'erro', 'motivo': f'{type(e).__name__}: {e}'[:200]})
        if motivo == 'erro':
            conversa_voz.deixar_gemini('não abriu ou caiu')
    if motivo == 'erro' and reserva:
        # Quem transcreve na reserva (o pequeno confere o privado antes da Groq)
        # fica carregado enquanto ela durar: frio, o primeiro pedido esperava ele subir.
        pequeno = transcricao.online() and transcricao.pequeno_disponivel()
        segurado = transcricao if pequeno else voz
        segurado.segurar()
        _aquecer_whisper(pequeno)
        try:
            await avisar_pronta()
            await ws.send_json({'tipo': 'reserva'})
            motivo = await conversa_voz.conduzir_reserva(conversa, receber, ws.send_bytes, ws.send_json, ao_turno,
                                                         local=local)
        except WebSocketDisconnect:
            motivo = 'saiu'
        except Exception as e:  # noqa: BLE001 — a reserva também caiu: avisa e fecha
            log.warning('o modo conversa caiu na reserva: %r', e)
            motivo = 'erro'
            with contextlib.suppress(Exception):
                await ws.send_json({'tipo': 'erro', 'motivo': f'{type(e).__name__}: {e}'[:200]})
        finally:
            segurado.soltar()
    with contextlib.suppress(Exception):
        await ws.send_json({'tipo': 'fim', 'motivo': motivo})
        await ws.close()


# — Aprovações do agente (agente.py) ——————————————————————————————————————————————

class Aprovacao(BaseModel):
    aprovar: bool
    # Aprovar e não perguntar de novo nesta conversa (o comando exato, ou as edições).
    sempre: bool = False


@app.post('/aprovacoes/{id_}')
async def responder_aprovacao(id_: str, corpo: Aprovacao):
    """O Matheus respondeu o cartão de aprovação na conversa."""
    from . import agente
    if not agente.responder_aprovacao(id_, corpo.aprovar, corpo.sempre):
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
