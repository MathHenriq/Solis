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


def eventos(r) -> list[dict]:
    return [json.loads(linha) for linha in r.text.splitlines()]


def texto(r) -> str:
    return ''.join(e.get('texto', '') for e in eventos(r))


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

    async def falso(modelo, mensagens, memorias=None, trechos=None, resumo=None, **_):
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
    assert r.status_code == 200 and texto(r) == 'Olá, Matheus.'
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
    for erro, chave in [
        (ollama.OllamaIndisponivel, 'ollama_indisponivel'),
        (ollama.ModeloInexistente, 'modelo_inexistente'),
    ]:
        async def falha(*_, erro=erro, **__):
            raise erro()
        monkeypatch.setattr(ollama, 'conversar', falha)
        r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
        # O erro chega como o último evento: o stream já estava aberto.
        ultimo = eventos(r)[-1]
        assert (ultimo['erro'], 'texto' in ultimo) == (chave, False)
    # A fala da pessoa fica; nenhuma resposta do Solis foi inventada.
    papeis = [m['papel'] for m in cliente.get('/conversas/atual').json()['mensagens']]
    assert papeis == ['pessoa', 'pessoa']


def test_conversa_inexistente():
    r = TestClient(main.app).post('/conversas/999/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    assert (r.status_code, r.json()) == (404, {'erro': 'conversa_inexistente'})


def test_etapas_da_resposta_inteira_em_ordem(monkeypatch):
    falso_que_responde(monkeypatch)
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']
    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    assert r.headers['content-type'] == 'application/x-ndjson'
    lista = eventos(r)
    etapas = [e['etapa'] for e in lista if 'etapa' in e]
    # Antes da resposta, a resposta, e depois dela — as de depois chegam pelo
    # mesmo stream, que só fecha quando o aprendizado e o resumo terminam.
    assert etapas == ['memoria', 'cerebro', 'primeira_palavra', 'fim', 'aprendizado', 'indexacao', 'resumo']
    assert lista[0] == {'etapa': 'memoria', 't': lista[0]['t'], 'memorias': 0, 'trechos': 0}
    tempos = [e['t'] for e in lista if 't' in e]
    assert tempos == sorted(tempos)
    # O texto chega entre a primeira palavra e o fim.
    i, f = [n for n, e in enumerate(lista) if e.get('etapa') in ('primeira_palavra', 'fim')]
    assert ''.join(e['texto'] for e in lista[i + 1:f]) == 'Olá, Matheus.'
    # E ficam guardadas com a resposta, sem o texto, pra a tela reabrir com elas.
    [pessoa, solis] = cliente.get('/conversas/atual').json()['mensagens']
    assert pessoa['etapas'] is None
    assert solis['etapas'] == [e for e in lista if 'etapa' in e]


def test_titulo_e_uma_etapa_depois_da_resposta(monkeypatch):
    falso_que_responde(monkeypatch)

    async def titulo(modelo, instrucao, texto, **_):
        return 'Cumprimento'
    monkeypatch.setattr(ollama, 'responder_texto', titulo)
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']
    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    etapas = [e for e in eventos(r) if 'etapa' in e]
    assert [e['etapa'] for e in etapas][-4:] == ['titulo', 'aprendizado', 'indexacao', 'resumo']
    assert next(e for e in etapas if e['etapa'] == 'titulo')['titulo'] == 'Cumprimento'
    assert cliente.get('/conversas').json()['conversas'][0]['titulo'] == 'Cumprimento'


def test_tarefas_de_fundo_usam_o_modelo_de_fundo(monkeypatch):
    """O título, o aprendizado e o resumo vão pro MODELO_FUNDO, não pro modelo
    da conversa; sem ele instalado (ou sem Ollama), voltam pro da conversa."""
    falso_que_responde(monkeypatch)
    usados = []

    async def aprender(modelo, *_):
        usados.append(modelo)
        return []
    monkeypatch.setattr(memoria, 'aprender', aprender)
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']

    async def com_qwen():
        return {'llama3.2:3b', main.MODELO_FUNDO}
    monkeypatch.setattr(ollama, 'instalados', com_qwen)
    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'llama3.2:3b', 'texto': 'oi'})
    assert next(e for e in eventos(r) if e.get('etapa') == 'aprendizado')['modelo'] == main.MODELO_FUNDO

    async def sem_qwen():
        return {'llama3.2:3b'}
    monkeypatch.setattr(ollama, 'instalados', sem_qwen)
    cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'llama3.2:3b', 'texto': 'e aí'})
    assert usados == [main.MODELO_FUNDO, 'llama3.2:3b']
