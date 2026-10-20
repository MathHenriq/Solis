"""Conversa com o Ollama — o que está instalado, o que está carregado, e o chat.

Só fala HTTP com o servidor do Ollama (padrão 127.0.0.1:11434). Não formata
nada pra tela: devolve bytes e números crus, e quem decide "4,7 GB" ou "128k"
é o front.
"""
import asyncio
import json
import os
from collections.abc import AsyncIterator

import httpx

OLLAMA = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')

# ERROR_STATES.md §2 pede timeout de 8–10s antes de desistir do modelo local.
# A conexão em si falha rápido: se nada escuta na porta, não adianta esperar 8s
# pra dizer que o Ollama está fora do ar.
TIMEOUT = httpx.Timeout(8.0, connect=2.0)

# Na conversa os 8s não servem: o primeiro pedaço só sai depois que o Ollama
# carrega o modelo na memória, e um 14B frio passa disso fácil. O limite vale
# ENTRE pedaços — um modelo que travou no meio ainda é cortado, só que em 2 min.
TIMEOUT_CONVERSA = httpx.Timeout(120.0, connect=2.0)

# Quem o Solis é e, sobretudo, o que ele NÃO consegue fazer. O modelo não sabe
# o que o app em volta dele faz: sem esta lista, perguntado se tem internet, ele
# inventa que tem (aconteceu, com o llama3.2:3b). Este texto descreve as
# capacidades de HOJE — quando memória ou ferramentas entrarem, ele muda junto.
SISTEMA = (
    'Você é o Solis, o assistente pessoal do Matheus. Você roda localmente no '
    'computador dele, num modelo de linguagem pequeno.\n\n'
    'O que você NÃO pode fazer, e deve dizer com clareza quando perguntarem: '
    'acessar a internet, ler arquivos ou programas do computador, e lembrar de '
    'algo depois que a conversa for fechada. Você só sabe o que foi dito nesta '
    'conversa e o que aprendeu no treinamento.\n\n'
    'Quando não souber algo, diga que não sabe. Responda em português do Brasil, '
    'com clareza e sem rodeios.'
)

PAPEIS = {'pessoa': 'user', 'solis': 'assistant'}


class OllamaIndisponivel(Exception):
    """O Ollama não respondeu — desligado, porta errada ou travado."""


class ModeloInexistente(Exception):
    """O modelo pedido não está instalado no Ollama."""


def _contexto(info: dict) -> int | None:
    # A chave é prefixada pela arquitetura ("llama.context_length",
    # "qwen2.context_length", "nomic-bert.context_length"), então procura pelo sufixo.
    for chave, valor in info.items():
        if chave.endswith('.context_length'):
            return int(valor)
    return None


def _embeddings(nome: str, detalhes: dict) -> bool:
    # Ollama recente declara `capabilities`; versões antigas não, e aí o nome é
    # o único sinal que sobra (nomic-embed-text, mxbai-embed-large...).
    capacidades = detalhes.get('capabilities')
    if capacidades is not None:
        return 'embedding' in capacidades
    return 'embed' in nome


async def listar_modelos(transporte: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    async with httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT, transport=transporte) as c:
        try:
            tags, ps = await asyncio.gather(c.get('/api/tags'), c.get('/api/ps'))
            tags.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaIndisponivel() from e

        modelos = tags.json().get('models', [])
        carregados = {m['name'] for m in ps.json().get('models', [])} if ps.is_success else set()

        # /api/show é por modelo; em paralelo, porque com 5 modelos em série a
        # tela esperaria 5 idas e voltas. Se um falhar, o modelo ainda aparece
        # — só sem contexto.
        async def mostrar(nome: str) -> dict:
            try:
                r = await c.post('/api/show', json={'model': nome})
                return r.json() if r.is_success else {}
            except httpx.HTTPError:
                return {}

        detalhes = await asyncio.gather(*(mostrar(m['name']) for m in modelos))

    return [
        {
            'nome': m['name'],
            'bytes': m.get('size', 0),
            'quantizacao': m.get('details', {}).get('quantization_level'),
            'contexto': _contexto(d.get('model_info', {})),
            # Na memória agora (/api/ps). Não é o "Em uso" da tela — esse é o
            # modelo escolhido pra Conversa, e quem guarda a escolha é o front.
            # O Ollama descarrega o modelo depois de ~5 min parado.
            'carregado': m['name'] in carregados,
            'embeddings': _embeddings(m['name'], d),
        }
        for m, d in zip(modelos, detalhes)
    ]


async def conversar(
    modelo: str,
    mensagens: list[dict],
    transporte: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[str]:
    """Abre a resposta do modelo e devolve os pedaços de texto conforme saem.

    O erro de conexão e o de modelo inexistente são levantados AQUI, antes do
    primeiro pedaço — depois que o streaming começa já não dá pra trocar o
    status da resposta HTTP. Um corte no meio só encerra o texto onde parou.
    """
    corpo = {
        'model': modelo,
        'stream': True,
        'messages': [{'role': 'system', 'content': SISTEMA}]
        + [{'role': PAPEIS[m['papel']], 'content': m['texto']} for m in mensagens],
    }
    cliente = httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT_CONVERSA, transport=transporte)
    try:
        r = await cliente.send(cliente.build_request('POST', '/api/chat', json=corpo), stream=True)
    except httpx.HTTPError as e:
        await cliente.aclose()
        raise OllamaIndisponivel() from e

    if r.status_code == 404:
        await r.aclose()
        await cliente.aclose()
        raise ModeloInexistente()
    if not r.is_success:
        await r.aclose()
        await cliente.aclose()
        raise OllamaIndisponivel()

    async def pedacos() -> AsyncIterator[str]:
        try:
            # Um JSON por linha. Modelos que "pensam" (qwen3) mandam o raciocínio
            # em `message.thinking`; só `content` é resposta, o resto fica de fora.
            async for linha in r.aiter_lines():
                if not linha:
                    continue
                parte = json.loads(linha)
                if 'error' in parte:
                    break
                texto = parte.get('message', {}).get('content', '')
                if texto:
                    yield texto
                if parte.get('done'):
                    break
        except httpx.HTTPError:
            pass
        finally:
            await r.aclose()
            await cliente.aclose()

    return pedacos()
