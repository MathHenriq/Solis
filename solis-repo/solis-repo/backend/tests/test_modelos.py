"""O Ollama de verdade não roda aqui — as respostas abaixo têm o formato da API
dele (/api/tags, /api/ps, /api/show) e passam por um transporte falso do httpx."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from solis import main, ollama

TAGS = {'models': [
    {'name': 'llama3.1:8b', 'size': 4_920_753_328, 'details': {'quantization_level': 'Q4_K_M'}},
    {'name': 'nomic-embed-text:latest', 'size': 274_302_450, 'details': {'quantization_level': 'F16'}},
]}
PS = {'models': [{'name': 'llama3.1:8b'}]}
SHOW = {
    'llama3.1:8b': {'model_info': {'llama.context_length': 131072}, 'capabilities': ['completion', 'tools']},
    'nomic-embed-text:latest': {'model_info': {'nomic-bert.context_length': 2048}, 'capabilities': ['embedding']},
}


def ollama_falso(req: httpx.Request) -> httpx.Response:
    if req.url.path == '/api/tags':
        return httpx.Response(200, json=TAGS)
    if req.url.path == '/api/ps':
        return httpx.Response(200, json=PS)
    if req.url.path == '/api/show':
        return httpx.Response(200, json=SHOW[json.loads(req.content)['model']])
    return httpx.Response(404)


def test_lista_com_contexto_uso_e_embeddings():
    modelos = asyncio.run(ollama.listar_modelos(httpx.MockTransport(ollama_falso)))
    assert modelos == [
        {'nome': 'llama3.1:8b', 'bytes': 4_920_753_328, 'quantizacao': 'Q4_K_M',
         'contexto': 131072, 'carregado': True, 'embeddings': False},
        {'nome': 'nomic-embed-text:latest', 'bytes': 274_302_450, 'quantizacao': 'F16',
         'contexto': 2048, 'carregado': False, 'embeddings': True},
    ]


def test_show_falhando_nao_derruba_a_lista():
    def sem_show(req):
        return httpx.Response(500) if req.url.path == '/api/show' else ollama_falso(req)
    modelos = asyncio.run(ollama.listar_modelos(httpx.MockTransport(sem_show)))
    assert [m['contexto'] for m in modelos] == [None, None]
    # Sem /api/show não há `capabilities`; o nome ainda denuncia o de embeddings.
    assert [m['embeddings'] for m in modelos] == [False, True]


def test_ollama_fora_do_ar_vira_503(monkeypatch):
    async def recusa(*_):
        raise ollama.OllamaIndisponivel()
    monkeypatch.setattr(ollama, 'listar_modelos', recusa)
    r = TestClient(main.app).get('/modelos')
    assert r.status_code == 503
    assert r.json() == {'erro': 'ollama_indisponivel'}


def test_conexao_recusada_vira_indisponivel():
    def recusa(req):
        raise httpx.ConnectError('recusada', request=req)
    with pytest.raises(ollama.OllamaIndisponivel):
        asyncio.run(ollama.listar_modelos(httpx.MockTransport(recusa)))
