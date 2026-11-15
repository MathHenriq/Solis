"""Pesquisa longa (docs/PARIDADE.md): o botão Pesquisa manda pro Claude com a
orientação, e as fontes (o que a busca achou e o que foi lido) ficam nas etapas."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from solis import agente, banco, main, roteador


@pytest.fixture
def capturado(monkeypatch):
    recebido = {}

    async def responder(ordem, modelo, conversa, historico, memorias, trechos, resumo, mensagem, *_, **__):
        recebido.update(ordem=ordem, mensagem=mensagem)

        async def fluxo():
            yield 'pronto'
        return fluxo(), 'claude'
    monkeypatch.setattr(roteador, 'responder', responder)
    monkeypatch.setattr(roteador, '_ordem', lambda: ['local', 'claude'])

    async def nada(*_, **__):
        return None
    monkeypatch.setattr(main, '_depois', nada)
    return recebido


def test_pesquisa_vai_pro_claude_com_a_orientacao(capturado):
    c = banco.nova_conversa()
    r = TestClient(main.app).post(f'/conversas/{c}/mensagens', json={'texto': 'qual o melhor banco digital?', 'pesquisa': True})
    eventos = r.text
    assert capturado['ordem'] == ['claude']
    assert capturado['mensagem'].startswith('qual o melhor banco digital?') and roteador.NOTA_PESQUISA in capturado['mensagem']
    assert '"etapa": "pesquisa"' in eventos
    # O que fica guardado é o que o Matheus disse, sem a orientação.
    assert banco.mensagens(c)[0]['texto'] == 'qual o melhor banco digital?'


def test_sem_pesquisa_nao_muda_nada(capturado):
    c = banco.nova_conversa()
    TestClient(main.app).post(f'/conversas/{c}/mensagens', json={'texto': 'oi'})
    assert roteador.NOTA_PESQUISA not in capturado['mensagem']


def test_links_da_busca():
    texto = ('Web search results for query: "x"\n\nLinks: [{"title":"A","url":"https://a.com/1"},'
             '{"title":"B","url":"https://b.org"},{"title":"de novo","url":"https://a.com/1"},{"title":"x","url":"ftp://x"}]\n\nresumo')
    assert agente._links_da_busca(texto) == [{'titulo': 'A', 'url': 'https://a.com/1'}, {'titulo': 'B', 'url': 'https://b.org'}]
    assert agente._links_da_busca('sem links') == []


def test_pagina_lida_por_ajudante_vira_fonte_da_resposta():
    from claude_agent_sdk import AssistantMessage, ToolResultBlock, ToolUseBlock, UserMessage
    viva = agente._Viva(None, None, None, 'pedir')
    viva.fundo['A1'] = {'id': 'A1', 'tipo': 'ajudante', 'tool_use_id': 'ag1', 'passos': [], 'agora': None}
    mandados = []

    async def montar():
        viva.resposta = agente._Resposta(viva, lambda t, v=None: mandados.append((t, v)), {}, 'pedir')
        viva._do_ajudante(AssistantMessage(content=[ToolUseBlock(id='w1', name='WebFetch',
                                                                 input={'url': 'https://python.org/downloads/'})],
                                           model='m', parent_tool_use_id='ag1'))
        viva._do_ajudante(UserMessage(content=[ToolResultBlock(tool_use_id='w1', content='pagina', is_error=False)],
                                      parent_tool_use_id='ag1'))
    asyncio.run(montar())
    assert ('etapa', ('fonte', {'url': 'https://python.org/downloads/'})) in mandados


def test_resposta_que_vem_sozinha_leva_as_fontes_da_rodada():
    from claude_agent_sdk import AssistantMessage, ToolResultBlock, ToolUseBlock, UserMessage
    viva = agente._Viva(None, None, None, 'pedir')
    viva.fundo['A1'] = {'id': 'A1', 'tipo': 'ajudante', 'tool_use_id': 'ag1', 'passos': [], 'agora': None}

    async def montar():
        # Entre respostas (nenhuma aberta), o ajudante busca e lê.
        viva._do_ajudante(AssistantMessage(content=[ToolUseBlock(id='s1', name='WebSearch', input={'query': 'x'})],
                                           model='m', parent_tool_use_id='ag1'))
        viva._do_ajudante(UserMessage(content=[ToolResultBlock(
            tool_use_id='s1', is_error=False,
            content='Links: [{"title":"Doc","url":"https://doc.org"},{"title":"Blog","url":"https://blog.dev"}]\n')],
            parent_tool_use_id='ag1'))
        viva._do_ajudante(AssistantMessage(content=[ToolUseBlock(id='w1', name='WebFetch', input={'url': 'https://doc.org'})],
                                           model='m', parent_tool_use_id='ag1'))
        viva._do_ajudante(UserMessage(content=[ToolResultBlock(tool_use_id='w1', content='ok', is_error=False)],
                                      parent_tool_use_id='ag1'))
        viva._comecar_sozinha()
    asyncio.run(montar())
    fontes = [e for e in viva.sozinha.etapas if e['etapa'] == 'fontes'][0]['fontes']
    assert fontes == [{'url': 'https://doc.org', 'titulo': 'Doc', 'lida': True},
                      {'url': 'https://blog.dev', 'titulo': 'Blog', 'lida': False}]
