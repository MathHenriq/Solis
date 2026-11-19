"""Cérebros por API (solis/apis.py), com o serviço simulado — nenhum teste sai
pra rede nem gasta cota de ninguém."""
import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from solis import apis, banco, cerebros, cofre, main, roteador


class Gravador:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


def servico(rota):
    """Transporte falso: `rota(request) -> httpx.Response`."""
    return httpx.MockTransport(rota)


def sse(*eventos):
    linhas = [f'data: {json.dumps(e)}' for e in eventos] + ['data: [DONE]']
    return '\n\n'.join(linhas) + '\n\n'


def coletar(gerador):
    async def junta():
        return [p async for p in gerador]
    return asyncio.run(junta())


# --- escolha do modelo -------------------------------------------------------

def test_groq_e_mistral_pela_preferencia():
    assert apis._escolher('groq', ['llama-3.3-70b-versatile', 'openai/gpt-oss-120b']) == 'openai/gpt-oss-120b'
    assert apis._escolher('mistral', ['codestral-latest', 'mistral-small-latest']) == 'mistral-small-latest'
    # Nenhum preferido: o primeiro que o serviço tem, em vez de nada.
    assert apis._escolher('groq', ['outro-modelo']) == 'outro-modelo'


def test_gemini_pega_o_flash_mais_novo_que_conversa():
    ids = ['gemini-2.5-flash', 'gemini-3.0-flash-lite', 'gemini-3.0-flash-preview-tts',
           'gemini-3.0-flash', 'gemini-2.5-pro', 'gemini-3.1-flash-preview']
    # O estável vence o preview, mesmo mais velho; lite e tts ficam de fora.
    assert apis._escolher('gemini', ids) == 'gemini-3.0-flash'
    assert apis._escolher('gemini', ['gemini-3.1-flash-preview']) == 'gemini-3.1-flash-preview'


def test_openrouter_so_os_gratis():
    ids = ['openai/gpt-oss-120b', 'mistralai/x:free', 'qwen/qwen3-235b:free']
    assert apis._escolher('openrouter', ids) == 'qwen/qwen3-235b:free'
    assert apis._escolher('openrouter', ['openai/gpt-oss-120b']) is None


# --- chave -------------------------------------------------------------------

def test_chave_recusada_nao_e_guardada():
    t = servico(lambda req: httpx.Response(401))
    with pytest.raises(apis.ChaveRecusada):
        asyncio.run(apis.guardar_chave('groq', 'gsk_errada', t))
    assert not apis.tem_chave('groq')


def test_gemini_cai_pra_lista_nativa_quando_o_formato_openai_recusa():
    def rota(req):
        if req.url.path.endswith('/openai/models'):
            return httpx.Response(401)
        assert req.headers['x-goog-api-key'] == 'AIza_boa'
        return httpx.Response(200, json={'models': [
            {'name': 'models/gemini-2.5-flash', 'supportedGenerationMethods': ['generateContent']},
            {'name': 'models/text-embedding-004', 'supportedGenerationMethods': ['embedContent']},
        ]})
    assert asyncio.run(apis.guardar_chave('gemini', 'AIza_boa', servico(rota))) == 'gemini-2.5-flash'

    def recusa(req):
        return httpx.Response(401) if 'openai' in req.url.path else httpx.Response(400)
    with pytest.raises(apis.ChaveRecusada):
        asyncio.run(apis.guardar_chave('gemini', 'errada', servico(recusa)))


def test_chave_boa_fica_selada_com_o_modelo(tmp_path):
    vistos = []

    def rota(req):
        vistos.append((req.url, req.headers['authorization']))
        return httpx.Response(200, json={'data': [{'id': 'openai/gpt-oss-120b'}]})

    assert asyncio.run(apis.guardar_chave('groq', 'gsk_boa', servico(rota))) == 'openai/gpt-oss-120b'
    assert vistos == [(httpx.URL('https://api.groq.com/openai/v1/models'), 'Bearer gsk_boa')]
    assert apis.tem_chave('groq') and apis.modelo('groq') == 'openai/gpt-oss-120b'
    if cofre.DISPONIVEL:
        assert cofre.selado(banco.ajuste('chave:groq'))
        banco._con().execute('PRAGMA wal_checkpoint(TRUNCATE)')
        assert b'gsk_boa' not in (tmp_path / 'solis.db').read_bytes()


def test_rota_guarda_liga_e_nunca_devolve_a_chave(monkeypatch):
    async def lista(nome, chave, transporte=None):
        return ['openai/gpt-oss-120b']
    monkeypatch.setattr(apis, 'listar', lista)
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: nome in cerebros.CLIS or apis.tem_chave(nome))
    cliente = TestClient(main.app)

    r = cliente.put('/cerebros/groq/chave', json={'chave': '  gsk_segredo  '})
    assert r.status_code == 200 and 'gsk_segredo' not in r.text
    groq = next(c for c in r.json()['cerebros'] if c['nome'] == 'groq')
    assert (groq['ligado'], groq['instalado'], groq['modelo']) == (True, True, 'openai/gpt-oss-120b')
    assert groq['site'].startswith('https://console.groq.com')
    assert 'groq' in roteador.escolher('oi')[1]
    assert roteador.escolher('/groq oi') == ('oi', ['groq'], True)

    r = cliente.delete('/cerebros/groq/chave')
    groq = next(c for c in r.json()['cerebros'] if c['nome'] == 'groq')
    assert (groq['ligado'], groq['instalado'], groq['modelo']) == (False, False, None)


def test_rota_diz_o_que_deu_errado(monkeypatch):
    cliente = TestClient(main.app)
    assert cliente.put('/cerebros/claude/chave', json={'chave': 'x'}).status_code == 404
    assert cliente.put('/cerebros/groq/chave', json={'chave': '  '}).json() == {'erro': 'chave_vazia'}

    async def recusa(*_, **__):
        raise apis.ChaveRecusada()
    monkeypatch.setattr(apis, 'listar', recusa)
    assert cliente.put('/cerebros/groq/chave', json={'chave': 'x'}).json() == {'erro': 'chave_recusada'}

    async def fora(*_, **__):
        raise apis.ProvedorFora('ConnectError')
    monkeypatch.setattr(apis, 'listar', fora)
    r = cliente.put('/cerebros/groq/chave', json={'chave': 'x'})
    assert (r.status_code, r.json()['erro']) == (502, 'provedor_fora')


# --- resposta ----------------------------------------------------------------

def com_chave(nome='groq', modelo='openai/gpt-oss-120b'):
    banco.guardar_ajuste(f'chave:{nome}', cofre.selar('gsk_x'))
    banco.guardar_ajuste(f'modelo:{nome}', modelo)


def test_resposta_em_pedacos_e_raciocinio_vira_etapa():
    com_chave()
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        corpo = sse(
            {'choices': [{'delta': {'reasoning': 'hmm'}}]},
            {'choices': [{'delta': {'content': 'Bom '}}]},
            {'choices': [{'delta': {}}]},
            {'choices': [{'delta': {'content': 'dia.'}}]},
        )
        return httpx.Response(200, text=corpo, headers={'content-type': 'text/event-stream'})

    g = Gravador()
    assert ''.join(coletar(apis.responder('groq', 'sis', 'oi', g, servico(rota)))) == 'Bom dia.'
    [p] = pedidos
    assert p['model'] == 'openai/gpt-oss-120b' and p['stream'] is True
    assert p['messages'] == [{'role': 'system', 'content': 'sis'}, {'role': 'user', 'content': 'oi'}]
    assert [e for e, _ in g.lista] == ['pedido', 'pensando']


def test_limite_gratis_pausa_ate_quando_o_servico_disse():
    com_chave()
    t = servico(lambda req: httpx.Response(429, headers={'retry-after': '30'}))
    with pytest.raises(cerebros.CerebroFalhou):
        coletar(apis.responder('groq', 's', 'p', transporte=t))
    pausa = cerebros.pausa('groq')
    assert pausa['motivo'] == 'o limite grátis acabou'
    assert 25 < pausa['ate'] - time.time() <= 30


def test_abrir_nao_troca_a_pausa_certa_pela_padrao(monkeypatch):
    """O retry-after de 30 s não pode virar 30 min no abrir()."""
    async def responde(nome, sistema, prompt, etapas=None):
        cerebros.pausar(nome, time.time() + 30, 'o limite grátis acabou')
        raise cerebros.CerebroFalhou('o limite grátis acabou')
        yield  # pragma: no cover
    monkeypatch.setattr(apis, 'responder', responde)
    with pytest.raises(cerebros.CerebroFalhou):
        asyncio.run(cerebros.abrir('groq', 's', 'p'))
    assert cerebros.pausa('groq')['ate'] - time.time() <= 30


def test_chave_recusada_na_resposta_pausa_um_dia():
    com_chave()
    t = servico(lambda req: httpx.Response(401))
    with pytest.raises(cerebros.CerebroFalhou, match='chave foi recusada'):
        coletar(apis.responder('groq', 's', 'p', transporte=t))
    assert cerebros.pausa('groq')['ate'] - time.time() > 23 * 3600


def test_sem_chave_falha_sem_chamar_ninguem():
    with pytest.raises(cerebros.CerebroFalhou, match='sem chave'):
        coletar(apis.responder('gemini', 's', 'p', transporte=servico(lambda req: 1 / 0)))


def test_quem_nao_comeca_a_responder_cai_pro_proximo(monkeypatch):
    """16/11/2026: o Gemini grátis ficou 60 s calado numa resposta por voz."""
    com_chave()
    monkeypatch.setattr(apis, 'PRIMEIRO_MAX', 0.2)

    class Calado(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(5)
            yield b''

    t = servico(lambda req: httpx.Response(200, stream=Calado(), headers={'content-type': 'text/event-stream'}))
    with pytest.raises(cerebros.CerebroFalhou, match='não começou a responder'):
        coletar(apis.responder('groq', 's', 'p', transporte=t))


def test_na_voz_o_gpt_oss_pensa_pouco():
    com_chave()
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        return httpx.Response(200, text=sse({'choices': [{'delta': {'content': 'Oi.'}}]}),
                              headers={'content-type': 'text/event-stream'})
    coletar(apis.responder('groq', 's', 'p', transporte=servico(rota), rapido=True))
    coletar(apis.responder('groq', 's', 'p', transporte=servico(rota)))
    # Medido em 16/11/2026: 10 de 10 certas nos dois, a 1a palavra de 0,68 s pra 0,47 s.
    assert pedidos[0]['reasoning_effort'] == 'low' and 'reasoning_effort' not in pedidos[1]


def test_na_voz_quem_demora_a_comecar_cai_em_poucos_segundos(monkeypatch):
    """16/11/2026: o Gemini levou 12 s só pra devolver 503. Na voz, o prazo vale
    do pedido à primeira palavra — inclusive esperando o cabeçalho."""
    com_chave()
    monkeypatch.setattr(apis, 'PRIMEIRO_VOZ', 0.2)

    async def rota(req):
        await asyncio.sleep(5)
        return httpx.Response(503)
    t0 = time.monotonic()
    with pytest.raises(cerebros.CerebroFalhou, match='não começou a responder'):
        coletar(apis.responder('groq', 's', 'p', transporte=httpx.MockTransport(rota), rapido=True))
    assert time.monotonic() - t0 < 2


def test_na_voz_o_prazo_acaba_na_primeira_palavra(monkeypatch):
    """Depois da primeira palavra, a resposta pode levar o tempo que for."""
    com_chave()
    monkeypatch.setattr(apis, 'PRIMEIRO_VOZ', 0.3)

    class Devagar(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ('data: ' + json.dumps({'choices': [{'delta': {'content': 'Um '}}]}) + '\n\n').encode()
            await asyncio.sleep(0.6)
            yield ('data: ' + json.dumps({'choices': [{'delta': {'content': 'dois.'}}]}) + '\n\ndata: [DONE]\n\n').encode()

    t = servico(lambda req: httpx.Response(200, stream=Devagar(), headers={'content-type': 'text/event-stream'}))
    assert ''.join(coletar(apis.responder('groq', 's', 'p', transporte=t, rapido=True))) == 'Um dois.'


# --- modelo lotado: outro do mesmo serviço atende ---------------------------

def _gemini_com(reservas):
    com_chave('gemini', reservas[0])
    banco.guardar_ajuste('modelos:gemini', reservas)


@pytest.fixture(autouse=True)
def _sem_lotados():
    apis._lotados.clear()
    yield
    apis._lotados.clear()


def test_gemini_lotado_troca_de_modelo_e_responde():
    """Medido em 19/11/2026: o gemini-3.8-flash deu 503 três dias; o 3-flash-preview atendia."""
    _gemini_com(['gemini-3.8-flash', 'gemini-3-flash-preview', 'gemini-3.1-flash-lite'])
    vistos = []

    def rota(req):
        modelo = json.loads(req.content)['model']
        vistos.append(modelo)
        if modelo == 'gemini-3.8-flash':
            return httpx.Response(503, text='This model is currently experiencing high demand.')
        return httpx.Response(200, text=sse({'choices': [{'delta': {'content': 'Oi!'}}]}),
                              headers={'content-type': 'text/event-stream'})

    g = Gravador()
    assert ''.join(coletar(apis.responder('gemini', 'sis', 'oi', g, servico(rota)))) == 'Oi!'
    assert vistos == ['gemini-3.8-flash', 'gemini-3-flash-preview']
    assert ('modelo', {'cerebro': 'gemini', 'modelo': 'gemini-3-flash-preview', 'antes': 'gemini-3.8-flash',
                       'motivo': 'o modelo está lotado (503)'}) in g.lista
    # A próxima vai direto no que atende: o lotado fica de lado por um tempo.
    vistos.clear()
    coletar(apis.responder('gemini', 'sis', 'oi de novo', Gravador(), servico(rota)))
    assert vistos == ['gemini-3-flash-preview']
    assert cerebros.pausa('gemini') is None


def test_gemini_no_limite_de_um_modelo_tenta_outro():
    """No grátis do Gemini o limite é por modelo."""
    _gemini_com(['gemini-3.8-flash', 'gemini-3.1-flash-lite'])

    def rota(req):
        if json.loads(req.content)['model'] == 'gemini-3.8-flash':
            return httpx.Response(429, text='quota', headers={'retry-after': '60'})
        return httpx.Response(200, text=sse({'choices': [{'delta': {'content': 'ok'}}]}),
                              headers={'content-type': 'text/event-stream'})

    assert ''.join(coletar(apis.responder('gemini', 'sis', 'oi', Gravador(), servico(rota)))) == 'ok'


def test_todos_lotados_o_cerebro_cai():
    _gemini_com(['gemini-3.8-flash', 'gemini-3-flash-preview'])
    rota = lambda req: httpx.Response(503, text='lotado')  # noqa: E731
    with pytest.raises(cerebros.CerebroFalhou):
        coletar(apis.responder('gemini', 'sis', 'oi', Gravador(), servico(rota)))


def test_quem_nem_comeca_a_responder_conta_como_lotado(monkeypatch):
    _gemini_com(['gemini-3.8-flash', 'gemini-3-flash-preview'])
    monkeypatch.setattr(apis, 'PRIMEIRO_MAX', 0.2)

    async def rota(req):
        if json.loads(req.content)['model'] == 'gemini-3.8-flash':
            await asyncio.sleep(2)
        return httpx.Response(200, text=sse({'choices': [{'delta': {'content': 'cheguei'}}]}),
                              headers={'content-type': 'text/event-stream'})

    assert ''.join(coletar(apis.responder('gemini', 'sis', 'oi', Gravador(), servico(rota)))) == 'cheguei'


def test_a_groq_sem_reserva_lotada_cai():
    com_chave()
    with pytest.raises(cerebros.CerebroFalhou):
        coletar(apis.responder('groq', 'sis', 'oi', Gravador(), servico(lambda req: httpx.Response(503, text='x'))))


def test_guardar_a_chave_guarda_a_lista_de_reserva():
    def rota(req):
        return httpx.Response(200, json={'data': [{'id': i} for i in (
            'gemini-3.1-flash-lite', 'gemini-3.8-flash', 'gemini-3-flash-preview', 'gemini-3.8-flash-tts')]})
    assert asyncio.run(apis.guardar_chave('gemini', 'AIza_boa', servico(rota))) == 'gemini-3.8-flash'
    assert banco.ajuste('modelos:gemini') == ['gemini-3.8-flash', 'gemini-3-flash-preview', 'gemini-3.1-flash-lite']


def test_a_ordem_e_pela_versao_com_ou_sem_preview_e_o_404_fica_de_lado_um_dia():
    ids = ['gemini-2.5-flash', 'gemini-3.5-flash', 'gemini-3-flash-preview', 'gemini-3.8-flash', 'gemini-3.1-flash-lite',
           'gemini-omni-1.2-flash', 'gemini-flash-latest']
    assert apis._reservas_de('gemini', ids) == ['gemini-3.8-flash', 'gemini-3.5-flash', 'gemini-3-flash-preview',
                                                'gemini-2.5-flash', 'gemini-3.1-flash-lite']
    _gemini_com(['gemini-2.5-flash', 'gemini-3-flash-preview'])

    def rota(req):
        if json.loads(req.content)['model'] == 'gemini-2.5-flash':
            return httpx.Response(404, text='no longer available to new users')
        return httpx.Response(200, text=sse({'choices': [{'delta': {'content': 'ok'}}]}),
                              headers={'content-type': 'text/event-stream'})
    assert ''.join(coletar(apis.responder('gemini', 'sis', 'oi', Gravador(), servico(rota)))) == 'ok'
    assert apis._lotados[('gemini', 'gemini-2.5-flash')] - time.time() > 23 * 3600


def test_a_assinatura_do_gemini_volta_na_rodada_seguinte():
    """Gemini 3: sem a thought_signature de volta, a rodada seguinte dá 400."""
    from solis import corpo
    _gemini_com(['gemini-3-flash-preview'])
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        if len(pedidos) == 1:
            return httpx.Response(200, text=sse({'choices': [{'delta': {'tool_calls': [{
                'index': 0, 'id': 'c1', 'type': 'function', 'function': {'name': 'mcp__solis__hora', 'arguments': '{}'},
                'extra_content': {'google': {'thought_signature': 'ASSINATURA'}}}]}}]}),
                headers={'content-type': 'text/event-stream'})
        return httpx.Response(200, text=sse({'choices': [{'delta': {'content': 'São 10h.'}}]}),
                              headers={'content-type': 'text/event-stream'})

    g = Gravador()
    saida = ''.join(coletar(apis.responder('gemini', 'sis', 'que horas', g, servico(rota),
                                           corpo=corpo.Corpo(1, g, navegar=False))))
    assert saida == 'São 10h.'
    chamada = pedidos[1]['messages'][-2]['tool_calls'][0]
    assert chamada['extra_content'] == {'google': {'thought_signature': 'ASSINATURA'}}
    # A Groq não recebe nada a mais.
    assert apis._assinatura('groq', {'id': 'x'}) == {}


def test_gemini_lotado_no_meio_da_tarefa_troca_e_segue_sem_a_assinatura_do_outro():
    """Visto em 19/11/2026: a Wikipédia parou com o modelo lotando na segunda rodada."""
    from solis import corpo
    _gemini_com(['gemini-3-flash-preview', 'gemini-3.1-flash-lite'])
    pedidos = []

    def rota(req):
        p = json.loads(req.content)
        pedidos.append(p)
        if len(pedidos) == 1:
            return httpx.Response(200, text=sse({'choices': [{'delta': {'tool_calls': [{
                'index': 0, 'id': 'c1', 'type': 'function', 'function': {'name': 'mcp__solis__hora', 'arguments': '{}'},
                'extra_content': {'google': {'thought_signature': 'DO_PREVIEW'}}}]}}]}),
                headers={'content-type': 'text/event-stream'})
        if p['model'] == 'gemini-3-flash-preview':
            return httpx.Response(503, text='lotado')
        return httpx.Response(200, text=sse({'choices': [{'delta': {'content': 'São 10h.'}}]}),
                              headers={'content-type': 'text/event-stream'})

    g = Gravador()
    saida = ''.join(coletar(apis.responder('gemini', 'sis', 'que horas', g, servico(rota),
                                           corpo=corpo.Corpo(1, g, navegar=False))))
    assert saida == 'São 10h.'
    assert [p['model'] for p in pedidos] == ['gemini-3-flash-preview', 'gemini-3-flash-preview', 'gemini-3.1-flash-lite']
    chamada = pedidos[2]['messages'][-2]['tool_calls'][0]
    assert chamada['extra_content'] == {'google': {'thought_signature': 'skip_thought_signature_validator'}}


def test_a_groq_lotada_no_meio_nao_troca():
    """Só o Gemini troca no meio (a Groq não tem reserva)."""
    from solis import corpo
    com_chave()
    n = []

    def rota(req):
        n.append(1)
        if len(n) == 1:
            return resposta_sse({'choices': [{'delta': {'tool_calls': [{
                'index': 0, 'id': 'c1', 'type': 'function', 'function': {'name': 'mcp__solis__hora', 'arguments': '{}'}}]}}]})
        return httpx.Response(503, text='lotado')

    g = Gravador()
    with pytest.raises(cerebros.CerebroFalhou):
        coletar(apis.responder('groq', 'sis', 'que horas', g, servico(rota), corpo=corpo.Corpo(1, g, navegar=False)))


def resposta_sse(*eventos):
    return httpx.Response(200, text=sse(*eventos), headers={'content-type': 'text/event-stream'})
