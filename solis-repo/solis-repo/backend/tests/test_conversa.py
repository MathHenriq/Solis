"""A conversa contra um Ollama falso que responde em NDJSON, como o /api/chat."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from solis import main, memoria, ollama

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
            transporte=httpx.MockTransport(chat_falso(recebido)),
        )
        return await juntar(fluxo)

    assert asyncio.run(rodar()) == 'Olá, Matheus.'
    pedido = recebido[0]
    assert pedido['model'] == 'llama3.2:3b' and pedido['stream'] is True
    assert [m['role'] for m in pedido['messages']] == ['system', 'user', 'assistant', 'user']
    assert pedido['messages'][0]['content'].startswith(ollama.SISTEMA)


def test_modelo_inexistente():
    def nao_achou(req):
        return httpx.Response(404, json={'error': "model 'x' not found"})

    with pytest.raises(ollama.ModeloInexistente):
        asyncio.run(ollama.conversar('x', [], transporte=httpx.MockTransport(nao_achou)))


def falso_que_responde(monkeypatch, pedacos=PEDACOS, quebra_no=None):
    """Troca o Ollama por um gerador; `quebra_no` simula a conexão caindo."""
    recebido = []

    async def falso(modelo, mensagens, memorias=None, trechos=None, resumo=None):
        recebido.append(mensagens)

        async def gen():
            for i, p in enumerate(pedacos):
                if i == quebra_no:
                    raise RuntimeError('caiu')
                yield p
        return gen()
    monkeypatch.setattr(ollama, 'conversar', falso)
    # O aprendizado de fundo tem teste próprio; aqui ele não pode sair pra rede.
    async def sem_aprender(*_):
        pass
    monkeypatch.setattr(memoria, 'aprender', sem_aprender)
    return recebido


def test_conversa_e_guardada_e_volta_inteira(monkeypatch):
    recebido = falso_que_responde(monkeypatch)
    cliente = TestClient(main.app)
    assert cliente.get('/conversas/atual').json() == {'id': None, 'mensagens': []}

    cid = cliente.post('/conversas').json()['id']
    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    assert r.status_code == 200 and r.text == 'Olá, Matheus.'
    cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'e aí?'})

    # O histórico que vai ao modelo sai do banco, com a resposta anterior junto.
    assert [m['texto'] for m in recebido[1]] == ['oi', 'Olá, Matheus.', 'e aí?']

    atual = cliente.get('/conversas/atual').json()
    assert atual['id'] == cid
    assert [(m['papel'], m['texto']) for m in atual['mensagens']] == [
        ('pessoa', 'oi'), ('solis', 'Olá, Matheus.'), ('pessoa', 'e aí?'), ('solis', 'Olá, Matheus.'),
    ]


def test_nova_conversa_vira_a_atual_e_comeca_vazia(monkeypatch):
    recebido = falso_que_responde(monkeypatch)
    cliente = TestClient(main.app)
    a = cliente.post('/conversas').json()['id']
    cliente.post(f'/conversas/{a}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    b = cliente.post('/conversas').json()['id']
    cliente.post(f'/conversas/{b}/mensagens', json={'modelo': 'm', 'texto': 'do zero'})
    assert [m['texto'] for m in recebido[-1]] == ['do zero']
    assert cliente.get('/conversas/atual').json()['id'] == b


def test_resposta_cortada_guarda_o_que_chegou(monkeypatch):
    falso_que_responde(monkeypatch, quebra_no=2)
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']
    try:
        cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    except RuntimeError:
        pass  # o TestClient repassa a exceção do gerador; no servidor real a conexão só fecha
    textos = [m['texto'] for m in cliente.get('/conversas/atual').json()['mensagens']]
    assert textos == ['oi', 'Olá, Matheus']


def test_rota_diz_quem_falhou_e_nao_guarda_o_aviso(monkeypatch):
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']
    for erro, status, chave in [
        (ollama.OllamaIndisponivel, 503, 'ollama_indisponivel'),
        (ollama.ModeloInexistente, 404, 'modelo_inexistente'),
    ]:
        async def falha(*_, erro=erro):
            raise erro()
        monkeypatch.setattr(ollama, 'conversar', falha)
        r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
        assert (r.status_code, r.json()) == (status, {'erro': chave})
    # A fala da pessoa fica; nenhuma resposta do Solis foi inventada.
    papeis = [m['papel'] for m in cliente.get('/conversas/atual').json()['mensagens']]
    assert papeis == ['pessoa', 'pessoa']


def test_conversa_inexistente():
    r = TestClient(main.app).post('/conversas/999/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    assert (r.status_code, r.json()) == (404, {'erro': 'conversa_inexistente'})
