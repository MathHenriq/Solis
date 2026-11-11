"""A voz da Fish Audio (fala.py), sem rede: o pedido, a chave conferida e
guardada selada, a lista de vozes em português e o lugar na cadeia."""
import asyncio
import json

import httpx
import pytest

from solis import banco, cofre, fala


def _transporte(responder):
    pedidos = []

    def tratar(req: httpx.Request):
        pedidos.append(req)
        return responder(req)
    return httpx.MockTransport(tratar), pedidos


def _com_chave(chave='fk-teste'):
    banco.guardar_ajuste('chave:fish', cofre.selar(chave))


def test_sem_chave_nao_tenta():
    with pytest.raises(fala.SemVoz, match='sem chave'):
        asyncio.run(fala.fish('oi', 'pt'))


def test_pedido_vai_com_o_modelo_gratis_a_voz_e_o_idioma():
    _com_chave()
    fala.escolher_voz_fish('voz-123')
    transporte, pedidos = _transporte(lambda req: httpx.Response(200, content=b'ID3audio'))
    audio = asyncio.run(fala.fish('Bom dia, Matheus.', 'pt', transporte))
    assert audio == b'ID3audio'
    req = pedidos[0]
    assert str(req.url) == fala.FISH_URL
    assert req.headers['authorization'] == 'Bearer fk-teste' and req.headers['model'] == 's2.1-pro-free'
    corpo = json.loads(req.content)
    assert corpo == {'text': 'Bom dia, Matheus.', 'format': 'mp3', 'latency': 'balanced', 'language': 'pt-BR',
                     'reference_id': 'voz-123'}


def test_erro_da_fish_vira_sem_voz_com_o_codigo():
    _com_chave()
    transporte, _ = _transporte(lambda req: httpx.Response(402, json={'message': 'No API credit', 'status': 402}))
    with pytest.raises(fala.SemVoz, match='402'):
        asyncio.run(fala.fish('oi', 'pt', transporte))


def test_vozes_em_portugues():
    _com_chave()
    itens = {'total': 2, 'items': [
        {'_id': 'a1', 'title': 'Narrador BR', 'task_count': 900, 'state': 'trained',
         'samples': [{'audio': 'https://x/a1.mp3'}]},
        {'_id': 'b2', 'title': 'Em treino', 'task_count': 5, 'state': 'training', 'samples': []},
    ]}
    transporte, pedidos = _transporte(lambda req: httpx.Response(200, json=itens))
    vozes = asyncio.run(fala.vozes_fish(transporte))
    assert vozes == [{'id': 'a1', 'nome': 'Narrador BR', 'usos': 900, 'amostra': 'https://x/a1.mp3'}]
    assert pedidos[0].url.params['language'] == 'pt'


def test_chave_so_e_guardada_se_a_fish_aceita():
    recusa, _ = _transporte(lambda req: httpx.Response(401, json={'message': 'Invalid Token', 'status': 401}))
    with pytest.raises(fala.SemVoz):
        asyncio.run(fala.guardar_chave_fish('errada', recusa))
    assert fala.chave_fish() is None
    aceita, pedidos = _transporte(lambda req: httpx.Response(200, json={'total': 0, 'items': []}))
    asyncio.run(fala.guardar_chave_fish('  boa  ', aceita))
    # Confere nas vozes da própria conta: a lista pública aceita qualquer chave.
    assert pedidos[0].url.params['self'] == 'true' and pedidos[0].headers['authorization'] == 'Bearer boa'
    assert fala.chave_fish() == 'boa'
    # Selada no banco, nunca em texto puro.
    assert banco.ajuste('chave:fish') != 'boa'
    fala.esquecer_chave_fish()
    assert fala.chave_fish() is None


def test_fish_vem_primeiro_na_cadeia_e_o_privado_continua_local():
    assert [n for n, _, _ in fala.NUVEM] == ['fish', 'gemini', 'ava']


def test_ouvir_uma_voz_do_gemini_nao_passa_pela_fish(monkeypatch):
    _com_chave()
    chamadas = []

    async def fish_falso(texto, lingua_, **_):
        chamadas.append('fish')
        return b'fish'

    async def gemini_falso(texto, lingua_, voz=None, **_):
        chamadas.append('gemini')
        return b'gemini'
    monkeypatch.setattr(fala, 'NUVEM', [('fish', 'audio/mpeg', fish_falso), ('gemini', 'audio/wav', gemini_falso)])
    monkeypatch.setattr(fala, 'privado', lambda *_: False)
    assert asyncio.run(fala.falar('Oi, Matheus.', voz='Aoede'))[2] == 'gemini'
    assert asyncio.run(fala.falar('Oi de novo.'))[2] == 'fish'
    assert chamadas == ['gemini', 'fish']


# — Aos pedaços ————————————————————————————————————————————————————————————————————

def _juntar(fluxo):
    async def tudo():
        return [p async for p in fluxo]
    return asyncio.run(tudo())


class _Pedacos(httpx.AsyncByteStream):
    def __init__(self, pedacos):
        self.pedacos = pedacos

    async def __aiter__(self):
        for p in self.pedacos:
            yield p


def test_aos_pedacos_toca_o_que_chega_e_guarda_inteiro(monkeypatch):
    _com_chave()
    monkeypatch.setattr(fala, 'privado', lambda *_: False)
    transporte, pedidos = _transporte(lambda req: httpx.Response(200, stream=_Pedacos([b'ID3', b'aa', b'bb'])))
    monkeypatch.setattr(fala, '_transporte_fish', transporte)

    async def rodar():
        fluxo, tipo, quem = await fala.falar_aos_pedacos('Bom dia, Matheus.')
        return [p async for p in fluxo], tipo, quem
    pedacos, tipo, quem = asyncio.run(rodar())
    assert pedacos == [b'ID3', b'aa', b'bb'] and (tipo, quem) == ('audio/mpeg', 'fish')
    assert json.loads(pedidos[0].content)['latency'] == 'balanced'
    # A segunda vez sai do cache, inteira, sem ir na Fish.
    asyncio.run(rodar())
    assert len(pedidos) == 1


def test_fish_que_falha_antes_do_primeiro_pedaco_cai_pra_cadeia(monkeypatch):
    _com_chave()
    monkeypatch.setattr(fala, 'privado', lambda *_: False)
    transporte, _ = _transporte(lambda req: httpx.Response(429, json={'message': 'busy', 'status': 429}))
    monkeypatch.setattr(fala, '_transporte_fish', transporte)

    async def falar_falso(texto, conversa=None, voz=None):
        return b'RIFFwav', 'audio/wav', 'gemini'
    monkeypatch.setattr(fala, 'falar', falar_falso)

    async def rodar():
        fluxo, tipo, quem = await fala.falar_aos_pedacos('Oi.')
        return [p async for p in fluxo], tipo, quem
    assert asyncio.run(rodar()) == ([b'RIFFwav'], 'audio/wav', 'gemini')
    # 429: a Fish descansa em vez de ser tentada a cada pedaço.
    assert fala._fora_ate['fish'] > 0
    fala._fora_ate.pop('fish', None)


def test_privado_nao_vai_pra_fish(monkeypatch):
    _com_chave()
    monkeypatch.setattr(fala, 'privado', lambda *_: True)
    transporte, pedidos = _transporte(lambda req: httpx.Response(200, content=b'x'))
    monkeypatch.setattr(fala, '_transporte_fish', transporte)

    async def falar_falso(texto, conversa=None, voz=None):
        return b'local', 'audio/wav', 'kokoro'
    monkeypatch.setattr(fala, 'falar', falar_falso)

    async def rodar():
        fluxo, _, quem = await fala.falar_aos_pedacos('meu exame de sangue')
        return [p async for p in fluxo], quem
    assert asyncio.run(rodar()) == ([b'local'], 'kokoro') and pedidos == []


def test_rota_do_fluxo(monkeypatch):
    from fastapi.testclient import TestClient
    from solis import main

    async def aos_pedacos(texto, conversa=None):
        async def g():
            yield b'ID3'
            yield b'zz'
        return g(), 'audio/mpeg', 'fish'
    monkeypatch.setattr(fala, 'falar_aos_pedacos', aos_pedacos)
    c = TestClient(main.app)
    id_ = c.post('/fala/fluxo', json={'texto': 'oi'}).json()['id']
    r = c.get(f'/fala/fluxo/{id_}')
    assert r.content == b'ID3zz' and r.headers['x-solis-voz'] == 'fish'
    # O id vale uma vez só.
    assert c.get(f'/fala/fluxo/{id_}').status_code == 404
