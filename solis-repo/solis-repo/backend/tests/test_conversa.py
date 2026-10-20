"""A conversa contra um Ollama falso que responde em NDJSON, como o /api/chat."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from solis import main, ollama

PEDACOS = ['Olá', ', Matheus', '.']


def chat_falso(recebido: list):
    def responder(req: httpx.Request) -> httpx.Response:
        recebido.append(json.loads(req.content))
        linhas = [{'message': {'role': 'assistant', 'content': p}, 'done': False} for p in PEDACOS]
        # Modelo que "pensa": o raciocínio vem em outro campo e não pode vazar.
        linhas.insert(0, {'message': {'role': 'assistant', 'content': '', 'thinking': 'hmm'}, 'done': False})
        linhas.append({'message': {'role': 'assistant', 'content': ''}, 'done': True})
        return httpx.Response(200, text='\n'.join(json.dumps(l) for l in linhas) + '\n')
    return responder


async def juntar(fluxo):
    return ''.join([p async for p in fluxo])


def test_junta_os_pedacos_e_monta_o_pedido():
    recebido = []

    async def rodar():
        fluxo = await ollama.conversar(
            'llama3.2:3b',
            [{'papel': 'pessoa', 'texto': 'oi'}, {'papel': 'solis', 'texto': 'Olá.'}, {'papel': 'pessoa', 'texto': 'tudo bem?'}],
            httpx.MockTransport(chat_falso(recebido)),
        )
        return await juntar(fluxo)

    assert asyncio.run(rodar()) == 'Olá, Matheus.'
    pedido = recebido[0]
    assert pedido['model'] == 'llama3.2:3b' and pedido['stream'] is True
    assert [m['role'] for m in pedido['messages']] == ['system', 'user', 'assistant', 'user']
    assert pedido['messages'][0]['content'] == ollama.SISTEMA


def test_modelo_inexistente():
    def nao_achou(req):
        return httpx.Response(404, json={'error': "model 'x' not found"})

    with pytest.raises(ollama.ModeloInexistente):
        asyncio.run(ollama.conversar('x', [], httpx.MockTransport(nao_achou)))


def test_rota_devolve_o_texto_em_stream(monkeypatch):
    async def falso(modelo, mensagens):
        async def gen():
            for p in PEDACOS:
                yield p
        return gen()
    monkeypatch.setattr(ollama, 'conversar', falso)
    r = TestClient(main.app).post('/conversa', json={'modelo': 'm', 'mensagens': [{'papel': 'pessoa', 'texto': 'oi'}]})
    assert r.status_code == 200 and r.text == 'Olá, Matheus.'


def test_rota_diz_quem_falhou(monkeypatch):
    cliente = TestClient(main.app)
    corpo = {'modelo': 'm', 'mensagens': []}
    for erro, status, chave in [
        (ollama.OllamaIndisponivel, 503, 'ollama_indisponivel'),
        (ollama.ModeloInexistente, 404, 'modelo_inexistente'),
    ]:
        async def falha(*_, erro=erro):
            raise erro()
        monkeypatch.setattr(ollama, 'conversar', falha)
        r = cliente.post('/conversa', json=corpo)
        assert (r.status_code, r.json()) == (status, {'erro': chave})
