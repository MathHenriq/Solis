"""Os conectores da conta do claude.ai no Claude do Solis: o que só lê é livre,
o resto pede com o que vai ser mandado, e a lista pra tela."""
import asyncio

import pytest
from fastapi.testclient import TestClient

pytest.importorskip('claude_agent_sdk')

import claude_agent_sdk  # noqa: E402
from claude_agent_sdk.types import PermissionResultAllow  # noqa: E402

from solis import agente, main  # noqa: E402

AGENDA = 'mcp__claude_ai_Google_Calendar__'


def test_nome_do_conector_e_resumo():
    assert agente.conector_de(AGENDA + 'create_event') == ('Google Calendar', 'create_event')
    assert agente.conector_de('mcp__solis__hora') is None and agente.conector_de('Bash') is None
    assert agente.resumo(AGENDA + 'delete_event', {}) == 'Usar o Google Calendar: delete_event'


def _decidir(nome, entrada, so_le, responder=None):
    mandados = []

    def por(tipo, valor=None):
        mandados.append((tipo, valor))
        if responder is not None and tipo == 'etapa' and valor[0] == 'aprovacao':
            asyncio.get_running_loop().call_soon(agente.responder_aprovacao, valor[1]['id'], responder)
    return asyncio.run(agente._decidir(nome, entrada, por, None, None, 'pedir', None, None, so_le)), mandados


def test_conector_que_so_le_e_livre():
    r, mandados = _decidir(AGENDA + 'list_events', {'timeMin': 'hoje'}, so_le=True)
    assert isinstance(r, PermissionResultAllow) and mandados == []


def test_conector_que_muda_pede_mostrando_o_que_vai():
    r, mandados = _decidir(AGENDA + 'create_event', {'summary': 'Dentista', 'start': '15h'}, so_le=False, responder=False)
    pedido = mandados[0][1][1]
    assert pedido['resumo'] == 'Usar o Google Calendar: create_event'
    assert pedido['alvo'] == 'create_event'
    assert '"summary": "Dentista"' in pedido['entrada']
    assert r.behavior == 'deny'


class ClienteStatus:
    """Um CLI falso só com o get_mcp_status."""
    chamadas = 0
    respostas: list = []

    def __init__(self, options=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get_mcp_status(self):
        ClienteStatus.chamadas += 1
        return ClienteStatus.respostas[min(ClienteStatus.chamadas - 1, len(ClienteStatus.respostas) - 1)]


STATUS = {'mcpServers': [
    {'name': 'claude.ai Google Calendar', 'status': 'connected', 'config': {'type': 'claudeai-proxy'},
     'tools': [{'name': 'list_events', 'annotations': {'readOnly': True}},
               {'name': 'create_event', 'annotations': {}},
               {'name': 'delete_event', 'annotations': {'destructive': True}}]},
    {'name': 'claude.ai Gmail', 'status': 'needs-auth', 'config': {'type': 'claudeai-proxy'}},
    {'name': 'solis', 'status': 'connected', 'config': {'type': 'stdio'}, 'tools': [{'name': 'hora'}]},
]}


def test_sessao_sabe_o_que_so_le_perguntando_uma_vez():
    ClienteStatus.chamadas, ClienteStatus.respostas = 0, [STATUS]
    viva = agente._Viva(None, None, None, 'pedir')
    viva.cliente = ClienteStatus()

    async def ver():
        return [await viva.so_le(AGENDA + n) for n in ('list_events', 'create_event', 'delete_event')] + \
            [await viva.so_le('Read')]
    assert asyncio.run(ver()) == [True, False, False, False]
    assert ClienteStatus.chamadas == 1


def test_lista_dos_conectores_espera_conectar(monkeypatch, tmp_path):
    pendente = {'mcpServers': [{**STATUS['mcpServers'][0], 'status': 'pending', 'tools': []}]}
    # Primeiro vazia (os conectores ainda não chegaram), depois conectando, depois pronta.
    ClienteStatus.chamadas, ClienteStatus.respostas = 0, [{'mcpServers': []}, pendente, STATUS]
    monkeypatch.setattr(claude_agent_sdk, 'ClaudeSDKClient', ClienteStatus)
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: tmp_path)
    agente._conectores.update(quando=0.0, lista=None)
    lista = asyncio.run(agente.conectores())
    assert lista == [
        {'nome': 'Google Calendar', 'estado': 'conectado', 'ferramentas': 3, 'so_leem': 1},
        {'nome': 'Gmail', 'estado': 'precisa_entrar', 'ferramentas': 0, 'so_leem': 0},
    ]
    # Guardada: a segunda vez não sobe outro CLI.
    antes = ClienteStatus.chamadas
    asyncio.run(agente.conectores())
    assert ClienteStatus.chamadas == antes


def test_rota(monkeypatch):
    async def falsa(atualizar=False):
        return [{'nome': 'Canva', 'estado': 'conectado', 'ferramentas': 48, 'so_leem': 20, 'atualizou': atualizar}]
    monkeypatch.setattr(agente, 'conectores', falsa)
    c = TestClient(main.app)
    assert c.get('/conectores').json()['conectores'][0]['nome'] == 'Canva'
    assert c.get('/conectores', params={'atualizar': True}).json()['conectores'][0]['atualizou'] is True
