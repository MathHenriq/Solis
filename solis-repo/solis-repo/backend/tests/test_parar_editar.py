"""Parar a resposta no meio, editar uma mensagem e refazer a resposta
(docs/PARIDADE.md → a conversa básica do Desktop)."""
import asyncio
import json

import httpx

from solis import banco, main, roteador


def _eventos(corpo: str) -> list[dict]:
    return [json.loads(l) for l in corpo.splitlines() if l.strip()]


def _cerebro_lento(monkeypatch, antes_de_comecar: float = 0.0):
    """Um cérebro que diz "Começo" e depois fica pensando até ser parado."""
    async def responder(ordem, modelo, conversa, historico, *_, **__):
        await asyncio.sleep(antes_de_comecar)

        async def fluxo():
            yield 'Começo'
            await asyncio.sleep(30)
            yield ' e fim'
        return fluxo(), 'claude'
    monkeypatch.setattr(roteador, 'responder', responder)

    async def nada(*_, **__):
        return None
    monkeypatch.setattr(main, '_depois', nada)


async def _mandar_e_parar(conversa: int, espera: float) -> tuple[list[dict], dict]:
    transporte = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transporte, base_url='http://solis') as c:
        envio = asyncio.create_task(c.post(f'/conversas/{conversa}/mensagens', json={'texto': 'explica tudo'}))
        await asyncio.sleep(espera)
        parou = await c.post(f'/conversas/{conversa}/parar')
        r = await asyncio.wait_for(envio, 5)
        return _eventos(r.text), parou.json()


def test_parar_no_meio_guarda_o_que_chegou(monkeypatch):
    _cerebro_lento(monkeypatch)
    c = banco.nova_conversa()
    eventos, parou = asyncio.run(_mandar_e_parar(c, 0.5))
    assert parou == {'ok': True}
    assert ''.join(e['texto'] for e in eventos if 'texto' in e) == 'Começo'
    fim = next(e for e in eventos if e.get('etapa') == 'fim')
    assert fim['parada'] is True
    assert [m['texto'] for m in banco.mensagens(c)] == ['explica tudo', 'Começo']


def test_parar_antes_da_primeira_palavra(monkeypatch):
    _cerebro_lento(monkeypatch, antes_de_comecar=30)
    c = banco.nova_conversa()
    eventos, _ = asyncio.run(_mandar_e_parar(c, 0.5))
    assert next(e for e in eventos if e.get('etapa') == 'fim') == {'etapa': 'fim', 't': eventos[-1]['t'], 'parada': True}
    assert [m['texto'] for m in banco.mensagens(c)] == ['explica tudo']


def test_parar_sem_resposta_em_andamento():
    from fastapi.testclient import TestClient
    c = banco.nova_conversa()
    r = TestClient(main.app).post(f'/conversas/{c}/parar')
    assert r.status_code == 404 and r.json()['erro'] == 'nada_respondendo'


def test_ate_parar_devolve_o_resultado_quando_ninguem_para():
    async def rodar():
        async def pronto():
            return 42
        return await main._ate_parar(pronto(), asyncio.Event())
    assert asyncio.run(rodar()) == (42, False)


# — Editar e refazer ————————————————————————————————————————————————————————————

def _conversa_com(*falas: tuple[str, str]) -> tuple[int, list[int]]:
    c = banco.nova_conversa()
    return c, [banco.adicionar(c, papel, texto, cerebro=None if papel == 'pessoa' else 'local') for papel, texto in falas]


def test_apagar_desde_volta_a_conversa_e_os_vetores():
    c, ids = _conversa_com(('pessoa', 'um'), ('solis', 'resposta um'), ('pessoa', 'dois'), ('solis', 'resposta dois'))
    with banco._con() as con:
        con.execute("INSERT INTO vetores (tipo, ref, vetor) VALUES ('mensagem', ?, x'00')", (ids[3],))
    assert banco.apagar_desde(c, ids[2]) == 2
    assert [m['texto'] for m in banco.mensagens(c)] == ['um', 'resposta um']
    assert banco._con().execute("SELECT COUNT(*) FROM vetores WHERE tipo = 'mensagem'").fetchone()[0] == 0


def test_editar_troca_a_mensagem_e_o_que_veio_depois(monkeypatch):
    from fastapi.testclient import TestClient

    async def responder(*_, **__):
        async def fluxo():
            yield 'nova resposta'
        return fluxo(), 'local'
    monkeypatch.setattr(roteador, 'responder', responder)

    async def nada(*_, **__):
        return None
    monkeypatch.setattr(main, '_depois', nada)
    c, ids = _conversa_com(('pessoa', 'um'), ('solis', 'resposta um'), ('pessoa', 'dois'), ('solis', 'resposta dois'))
    banco.guardar_sessao_claude(c, 'velha')
    r = TestClient(main.app).post(f'/conversas/{c}/mensagens', json={'texto': 'dois, editado', 'desde': ids[2]})
    guardada = next(e for e in _eventos(r.text) if e.get('etapa') == 'guardada')
    assert [m['texto'] for m in banco.mensagens(c)] == ['um', 'resposta um', 'dois, editado', 'nova resposta']
    assert guardada['pessoa'] == banco.mensagens(c)[2]['id']
    # A sessão do Claude tinha visto o que foi apagado.
    assert banco.sessao_claude(c) is None


def test_editar_so_mensagem_da_pessoa_desta_conversa():
    from fastapi.testclient import TestClient
    c, ids = _conversa_com(('pessoa', 'um'), ('solis', 'resposta um'))
    outra, _ = _conversa_com(('pessoa', 'x'))
    cliente = TestClient(main.app)
    assert cliente.post(f'/conversas/{c}/mensagens', json={'texto': 'y', 'desde': ids[1]}).status_code == 404
    assert cliente.post(f'/conversas/{outra}/mensagens', json={'texto': 'y', 'desde': ids[0]}).status_code == 404
    assert [m['texto'] for m in banco.mensagens(c)] == ['um', 'resposta um']


def test_nao_edita_enquanto_responde():
    from fastapi.testclient import TestClient
    c, ids = _conversa_com(('pessoa', 'um'))
    main._paradas[c] = asyncio.Event()
    try:
        r = TestClient(main.app).post(f'/conversas/{c}/mensagens', json={'texto': 'y', 'desde': ids[0]})
        assert r.status_code == 409
    finally:
        main._paradas.pop(c, None)


def test_interromper_recusa_os_cartoes_que_esperavam():
    from concurrent.futures import Future
    from solis import agente
    fut = Future()
    agente._pendentes['x1'] = fut
    agente._interromper({'aprovacoes': {'x1'}})
    assert fut.result() is False
    agente._pendentes.pop('x1', None)


def test_a_conversa_libera_no_fim_e_nao_depois_do_aprendizado(monkeypatch):
    """Editar e refazer logo depois do fim não podem levar 409 por causa do
    título e do aprendizado, que ainda rodam."""
    from fastapi.testclient import TestClient

    async def responder(*_, **__):
        async def fluxo():
            yield 'pronto'
        return fluxo(), 'local'
    monkeypatch.setattr(roteador, 'responder', responder)
    durante = []

    async def depois(etapas, modelo, conversa, *_):
        durante.append(conversa in main._paradas)
    monkeypatch.setattr(main, '_depois', depois)
    c = banco.nova_conversa()
    TestClient(main.app).post(f'/conversas/{c}/mensagens', json={'texto': 'oi'})
    assert durante == [False]
