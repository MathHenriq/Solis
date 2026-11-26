"""O Atlas · Pesquisador (pesquisador.py, 25/11/2026): as novidades de IA da semana,
das fontes de verdade, escolhidas por qualquer cérebro e sem link inventado."""
import asyncio
import datetime as dt

import httpx
import pytest

from solis import apis, avisos, banco, corpo, pesquisador as p

AGORA = dt.datetime(2026, 11, 25, 10, 0)


def _fontes(pedido: httpx.Request) -> httpx.Response:
    url = str(pedido.url)
    if 'hn.algolia.com' in url:
        return httpx.Response(200, json={'hits': [
            {'title': 'Show HN: A tiny TTS model that runs on a laptop', 'url': 'https://tts.example/post',
             'points': 300, 'objectID': '1'},
            {'title': 'The history of the bicycle', 'url': 'https://bike.example', 'points': 900, 'objectID': '2'}]})
    if 'api.github.com/search' in url:
        return httpx.Response(200, json={'items': [
            {'full_name': 'ana/voz-rapida', 'html_url': 'https://github.com/ana/voz-rapida', 'stargazers_count': 800,
             'description': 'Fast speech-to-text for Portuguese', 'topics': ['asr']},
            {'full_name': 'bob/css-grid', 'html_url': 'https://github.com/bob/css-grid', 'stargazers_count': 2000,
             'description': 'A CSS layout library', 'topics': []}]})
    if 'huggingface.co/api/models' in url:
        return httpx.Response(200, json=[{'id': 'lab/modelo-x', 'likes': 500, 'pipeline_tag': 'text-generation',
                                          'createdAt': '2026-11-20T00:00:00Z'}])
    if 'api.github.com/repos/ana/voz-rapida/readme' in url:
        return httpx.Response(200, text='# Voz rápida\n![badge](x.svg)\nTranscreve português em 0,2 s na CPU. MIT.')
    if 'huggingface.co/lab/modelo-x/raw' in url:
        return httpx.Response(200, text='---\nlicense: research-only\n---\nA 7B model for research only.')
    return httpx.Response(404)


@pytest.fixture
def fontes(monkeypatch):
    monkeypatch.setattr(p, '_transporte', httpx.MockTransport(_fontes))
    monkeypatch.setattr(p, '_cerebros', lambda: ['groq'])


def _cerebro(monkeypatch, primeira, segunda):
    pedidos = []

    async def responder_json(nome, sistema, prompt, esquema, **_):
        pedidos.append((sistema, prompt))
        return primeira if len(pedidos) == 1 else segunda
    monkeypatch.setattr(apis, 'responder_json', responder_json)
    return pedidos


def test_so_as_de_ia_e_cada_fonte_contada(fontes):
    candidatas, contagem = asyncio.run(p.coletar(AGORA))
    assert contagem == {'hacker_news': 1, 'github': 1, 'hugging_face': 1}
    assert {x['titulo'] for x in candidatas} == {'Show HN: A tiny TTS model that runs on a laptop', 'ana/voz-rapida',
                                                  'lab/modelo-x'}


def test_o_cerebro_escolhe_pelo_numero_e_o_porque_sai_da_pagina(fontes, monkeypatch):
    candidatas, _ = asyncio.run(p.coletar(AGORA))
    n_voz = next(i for i, x in enumerate(candidatas, 1) if x['titulo'] == 'ana/voz-rapida')
    n_modelo = next(i for i, x in enumerate(candidatas, 1) if x['titulo'] == 'lab/modelo-x')
    pedidos = _cerebro(
        monkeypatch,
        {'itens': [{'numero': n_voz, 'por_que': '', 'o_que_fazer': ''},
                   {'numero': n_modelo, 'por_que': '', 'o_que_fazer': ''},
                   {'numero': 99, 'por_que': 'inventada', 'o_que_fazer': ''}]},
        {'itens': [{'numero': n_voz, 'por_que': 'Transcreve português em 0,2 s na CPU.', 'o_que_fazer': 'Testar.'},
                   {'numero': 99, 'por_que': 'inventada de novo', 'o_que_fazer': ''}]})
    escolhidas, cerebro = asyncio.run(p.escolher(candidatas))
    # O número que não está na lista não vira novidade; o link é o da fonte.
    assert cerebro == 'groq' and [(x['titulo'], x['url']) for x in escolhidas] == [
        ('ana/voz-rapida', 'https://github.com/ana/voz-rapida')]
    # A segunda passada leva o texto da página (sem os selos do README).
    assert 'Transcreve português em 0,2 s na CPU. MIT.' in pedidos[1][1] and 'badge' not in pedidos[1][1]
    assert 'A 7B model for research only.' in pedidos[1][1]
    assert 'só pra pesquisa' in pedidos[1][0]


def test_nada_util_diz_que_nao_achou(fontes, monkeypatch):
    _cerebro(monkeypatch, {'itens': []}, {'itens': []})
    candidatas, contagem = asyncio.run(p.coletar(AGORA))
    escolhidas, _ = asyncio.run(p.escolher(candidatas))
    assert escolhidas == []
    assert p.relatorio(escolhidas, candidatas, contagem, AGORA).startswith('Nada que valha o seu tempo nesta semana')


def test_rodar_entrega_na_conversa_e_avisa(fontes, monkeypatch):
    candidatas, _ = asyncio.run(p.coletar(AGORA))
    n = next(i for i, x in enumerate(candidatas, 1) if x['titulo'] == 'ana/voz-rapida')
    _cerebro(monkeypatch, {'itens': [{'numero': n, 'por_que': '', 'o_que_fazer': ''}]},
             {'itens': [{'numero': n, 'por_que': 'Transcreve português rápido.', 'o_que_fazer': 'Testar.'}]})
    avisados = []

    async def mostrar(titulo, texto, tag):
        avisados.append((titulo, texto))
        return True
    monkeypatch.setattr(avisos, 'mostrar', mostrar)
    monkeypatch.setattr(avisos, 'ligados', lambda: True)
    feito = asyncio.run(p.rodar(AGORA))
    [m] = banco.mensagens(feito['conversa'])
    assert m['personalidade'] == 'jarvis' and m['cerebro'] == 'groq'
    assert '**ana/voz-rapida** (GitHub, 800 estrelas). Transcreve português rápido.' in m['texto']
    assert 'https://github.com/ana/voz-rapida' in m['texto']
    assert banco.titulo(feito['conversa']) == 'Novidades da semana · Atlas'
    assert avisados == [('Jarvis · Atlas', '1 novidade da semana que serve pra você. Está nos Recentes do Solis.')]
    # A ferramenta, logo depois, devolve a mesma (não pesquisa de novo). "Logo
    # depois" pelo relógio de verdade, que a ferramenta usa: com o AGORA fixo, o
    # teste quebrou no dia seguinte (26/11/2026).
    banco.guardar_ajuste('pesquisador_ultima', {**p.ultima(), 'quando': dt.datetime.now().isoformat()})
    monkeypatch.setattr(p, 'rodar', None)
    assert asyncio.run(corpo._novidades_da_semana({})) == m['texto']


def test_roda_toda_segunda_das_9h_uma_vez():
    segunda_8h = dt.datetime(2026, 11, 23, 8, 0)
    assert not p.hora_de_rodar(segunda_8h)
    assert p.hora_de_rodar(segunda_8h + dt.timedelta(hours=1))
    assert p.hora_de_rodar(dt.datetime(2026, 11, 25, 20, 0))  # o Solis só abriu na quarta
    banco.guardar_ajuste('pesquisador_ultima', {'quando': '2026-11-23T09:05:00', 'conversa': 1})
    assert not p.hora_de_rodar(dt.datetime(2026, 11, 25, 20, 0))
    assert p.hora_de_rodar(dt.datetime(2026, 11, 30, 9, 0))  # a semana seguinte


def test_online_primeiro_o_local_e_a_reserva(monkeypatch):
    from solis import roteador
    monkeypatch.setattr(roteador, 'preferencia', lambda: [{'nome': n, 'ligado': True}
                                                          for n in ('claude', 'local', 'groq', 'gemini')])
    monkeypatch.setattr(apis, 'tem_chave', lambda n: n in ('groq', 'gemini'))
    assert p._cerebros() == ['groq', 'gemini', 'local']
