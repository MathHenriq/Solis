"""A chamada de ferramenta escrita como texto sai da resposta (marcacao.py).

O caso real (26/11/2026, servidor de teste, cérebro claude, "Quanto é 7 vezes
8?"): a primeira tentativa do Claude saiu com a chamada malformada, o CLI
descartou e pediu de novo, mas os pedaços dela já tinham ido pelo stream. A
resposta guardada e mostrada foi a de REAL, e tem que ser só "7 × 8 = 56."."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from solis import banco, cerebros, main, marcacao, memoria, roteador

P = 'an' + 'tml:'  # o prefixo, montado: escrito inteiro, viraria marca neste arquivo
REAL = P + 'invoke name="mcp__solis__hora">\n</invoke>7 × 8 = 56.'


def _aos_pedacos(pedacos: list[str]) -> str:
    f = marcacao.Filtro()
    return ''.join(f.passar(p) for p in pedacos) + f.fechar()


# — o filtro ——————————————————————————————————————————————————————————————————————
def test_o_caso_real_sai_so_a_resposta():
    assert marcacao.limpar(REAL) == '7 × 8 = 56.'


def test_a_marca_partida_em_dois_pedacos():
    # No meio do nome, do atributo, do fechamento: em qualquer ponto, o mesmo.
    assert _aos_pedacos([P + 'inv', 'oke name="mcp__solis__hora">\n</invoke>7 × 8 = 56.']) == '7 × 8 = 56.'
    assert _aos_pedacos([P + 'invoke name="mcp__solis__hora">\n</inv', 'oke>7 × 8 = 56.']) == '7 × 8 = 56.'
    for k in range(len(REAL) + 1):
        assert _aos_pedacos([REAL[:k], REAL[k:]]) == '7 × 8 = 56.', k


def test_o_que_nao_e_marca_sai_na_hora():
    # Nada de segurar texto à toa: só o que pode ser o começo de uma marca espera.
    f = marcacao.Filtro()
    assert f.passar('7 × 8 ') == '7 × 8 '
    assert f.passar('= 56. Pronto') == '= 56. Pronto'
    assert f.passar(' <') == ' '  # pode ser <invoke...: espera
    assert f.passar('b>ok') == '<b>ok'
    assert f.fechar() == ''


@pytest.mark.parametrize('bruto, limpo', [
    # O bloco inteiro, com o prefixo, e os parâmetros dentro.
    ('<' + P + 'function_calls>\n<' + P + 'invoke name="hora">\n<' + P + 'parameter name="fuso">BRT</' + P
     + 'parameter>\n</' + P + 'invoke>\n</' + P + 'function_calls>\nSão 21h.', 'São 21h.'),
    # Sem o prefixo, no meio da resposta: não sobra linha em branco.
    ('Vou ver.\n\n<function_calls>\n<invoke name="hora">\n</invoke>\n</function_calls>\n\nSão 21h.',
     'Vou ver.\n\nSão 21h.'),
    # Um fechamento solto.
    ('Olá </invoke>mundo', 'Olá mundo'),
    # Uma marca que nunca fechou, no fim.
    ('Resposta.\n<invoke name="x"', 'Resposta.\n'),
    ('Resposta.\n<' + P + 'invoke name="x">\n<' + P + 'parameter name="q">abc', 'Resposta.\n'),
])
def test_tira_as_formas_da_marca(bruto, limpo):
    assert marcacao.limpar(bruto) == limpo
    assert _aos_pedacos(list(bruto)) == limpo  # um caractere por pedaço


@pytest.mark.parametrize('texto', [
    # Dentro de código a marca pode ser o assunto (um exemplo, um XML de BPEL).
    'Use `<invoke name="x">` no XML.',
    'Exemplo:\n```xml\n<invoke name="a">\n  <parameter name="b">1</parameter>\n</invoke>\n```\nPronto.',
    '~~~\n<' + P + 'invoke name="z"></' + P + 'invoke>\n~~~\nok',
    # Texto comum com "<", crase e til.
    'x < y, <b>negrito</b>, <invoke> sem nome, <parameters>.',
    'a casa, as antas, ~5 min, `x`, ```inline```, fim com <inv',
])
def test_codigo_e_texto_comum_ficam_como_vieram(texto):
    assert marcacao.limpar(texto) == texto
    assert _aos_pedacos(list(texto)) == texto


def test_o_fluxo_nao_solta_pedaco_vazio():
    async def fluxo():
        yield P + 'invoke name="mcp__solis__hora">'
        yield '\n</invoke>'
        yield '7 × 8 = 56.'

    async def juntar():
        return [p async for p in marcacao.sem_marcacao(fluxo())]
    # A primeira palavra (cerebros.abrir) é a de verdade, não a marca.
    assert asyncio.run(juntar()) == ['7 × 8 = 56.']


# — o Claude pelo Agent SDK ———————————————————————————————————————————————————————————
def _eventos_do_caso_real():
    """Como o CLI manda: a tentativa com a chamada malformada (partida em
    pedaços), que ele descarta, e a tentativa de novo, cada uma numa mensagem."""
    from claude_agent_sdk import ResultMessage, StreamEvent

    def ev(evento):
        return StreamEvent(uuid='x', session_id='S1', parent_tool_use_id=None, event=evento)

    def texto(t):
        return ev({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': t}})
    return [
        ev({'type': 'message_start', 'message': {}}),
        ev({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}),
        texto(P + 'invoke name="mcp__so'), texto('lis__hora">\n</inv'), texto('oke>'),
        ev({'type': 'content_block_stop', 'index': 0}),
        ev({'type': 'message_start', 'message': {}}),
        ev({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}),
        texto('7 × 8 '), texto('= 56.'),
        ev({'type': 'content_block_stop', 'index': 0}),
        ResultMessage(subtype='success', duration_ms=1, duration_api_ms=1, is_error=False, num_turns=2,
                      session_id='S1', total_cost_usd=0.0),
    ]


def _receber(por, eventos, sozinha=False):
    from solis import agente

    async def ir():
        viva = agente._Viva(None, None, None, 'pedir')
        r = agente._Resposta(viva, por, {}, 'pedir', sozinha=sozinha)
        for m in eventos:
            r.receber(m)
        assert r.feito.done()
    asyncio.run(ir())


def test_agente_manda_pra_tela_so_a_resposta():
    pytest.importorskip('claude_agent_sdk')
    mandados = []
    _receber(lambda t, v=None: mandados.append((t, v)), _eventos_do_caso_real())
    assert ''.join(v for t, v in mandados if t == 'texto') == '7 × 8 = 56.'


def test_agente_tentativa_descartada_com_a_marca_aberta_nao_engole_a_seguinte():
    pytest.importorskip('claude_agent_sdk')
    from claude_agent_sdk import StreamEvent
    eventos = _eventos_do_caso_real()
    # A tentativa descartada parou no meio da marca (sem o fechamento).
    eventos[3] = StreamEvent(uuid='x', session_id='S1', parent_tool_use_id=None, event={
        'type': 'content_block_delta', 'index': 0,
        'delta': {'type': 'text_delta', 'text': 'lis__hora">\n<' + P + 'parameter name="fuso">BR'}})
    del eventos[4]
    mandados = []
    _receber(lambda t, v=None: mandados.append((t, v)), eventos)
    assert ''.join(v for t, v in mandados if t == 'texto') == '7 × 8 = 56.'


def test_agente_resposta_que_comecou_sozinha_vai_limpa_pro_banco():
    pytest.importorskip('claude_agent_sdk')
    from solis import agente
    c = banco.nova_conversa()
    coletor = agente._Coletor(c)
    _receber(coletor.por, _eventos_do_caso_real(), sozinha=True)
    assert coletor.agora()['texto'] == '7 × 8 = 56.'
    coletor.guardar()
    assert banco.mensagens(c)[-1]['texto'] == '7 × 8 = 56.'


# — a conversa inteira: o que a tela recebe e o que fica no banco ————————————————————
def test_a_rota_guarda_e_mostra_so_a_resposta(monkeypatch):
    """Qualquer cérebro passa pelo filtro em cerebros.abrir: aqui o do Claude
    manda os pedaços do caso real, a marca partida entre eles."""
    async def claude_falso(sistema, prompt, etapas=None, **_):
        yield P + 'invoke name="mcp__solis__hora">\n</inv'
        yield 'oke>7 × 8 = 56.'
    monkeypatch.setitem(cerebros.EXECUTORES, 'claude', claude_falso)
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: True)
    monkeypatch.setattr(roteador, 'ORDEM', ['claude'])

    async def nada(*_, **__):
        pass
    monkeypatch.setattr(memoria, 'aprender', nada)

    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']
    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': '/claude Quanto é 7 vezes 8?'})
    eventos = [json.loads(linha) for linha in r.text.splitlines()]
    assert ''.join(e.get('texto', '') for e in eventos) == '7 × 8 = 56.'
    assert all(e['texto'] for e in eventos if 'texto' in e)  # nenhum pedaço vazio na tela
    ultima = banco.mensagens(cid)[-1]
    assert (ultima['texto'], ultima['cerebro']) == ('7 × 8 = 56.', 'claude')
