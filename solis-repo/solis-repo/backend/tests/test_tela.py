"""Controle da tela (docs/PARIDADE.md): desligado até o Matheus ligar; ver é
livre, agir pede cartão com o print e o programa; nada cai no Solis. As funções
do Windows são trocadas por falsas: nenhum teste mexe no mouse dele."""
import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from solis import agente, main, tela

# Do corpo do PC: só existe no Windows (no servidor Linux, quem mexe no PC é o
# próprio PC). 26/11/2026.
so_no_windows = pytest.mark.skipif(os.name != 'nt', reason='corpo do PC: só no Windows')

T = 'mcp__solis__'


@pytest.fixture
def tela_falsa(monkeypatch):
    monkeypatch.setattr(tela, 'tamanho', lambda: (1920, 1080))
    alvo = {'programa': ('notepad.exe', 'Sem título - Bloco de Notas')}
    monkeypatch.setattr(tela, 'programa_alvo', lambda acao, entrada: (alvo['programa'][0], alvo['programa'][1]))
    monkeypatch.setattr(tela, 'imagem_do_cartao', lambda acao, entrada: 'data:image/png;base64,AAAA')
    return alvo


def test_desligada_por_padrao():
    assert tela.ligada() is False
    tela.ligar(True)
    assert tela.ligada() is (__import__('os').name == 'nt')


def test_coordenadas_do_print_pra_tela(tela_falsa):
    assert tela.escala() == pytest.approx(1366 / 1920)
    assert tela._real(683, 384) == (960, 540)
    with pytest.raises(tela.TelaRecusada, match='fora da tela'):
        tela._real(1400, 10)


def test_teclas_e_texto():
    assert tela._vk('Ctrl') == 0x11 and tela._vk('s') == ord('S') and tela._vk('f5') == 0x74
    with pytest.raises(tela.TelaRecusada, match='não existe'):
        tela._vk('banana')
    assert tela._utf16('ã') == [0xE3] and tela._utf16('😀') == [0xD83D, 0xDE00]


def test_frases():
    assert tela.resumo('tela_clicar', {'x': 10, 'y': 20}) == 'Clicar em (10, 20)'
    assert tela.resumo('tela_clicar', {'x': 1, 'y': 2, 'duplo': True}) == 'Clicar duas vezes em (1, 2)'
    assert tela.resumo('tela_tecla', {'teclas': 'ctrl+s'}) == 'Apertar ctrl+s'
    assert tela.nome_do_programa('notepad.exe', '') == 'notepad'


def test_nada_cai_no_solis(monkeypatch, tela_falsa):
    monkeypatch.setattr(tela, 'janela_em', lambda x, y: ('solis.exe', 'Solis'))
    monkeypatch.setattr(tela, 'janela_ativa', lambda: ('solis.exe', 'Solis'))
    with pytest.raises(tela.TelaRecusada, match='Solis'):
        tela.clicar(100, 100)
    with pytest.raises(tela.TelaRecusada, match='Solis'):
        tela.digitar('oi')
    with pytest.raises(tela.TelaRecusada, match='Solis'):
        tela.tecla('enter')


def _por(respostas):
    mandados = []

    def por(tipo, valor=None):
        mandados.append((tipo, valor))
        if tipo == 'etapa' and valor[0] == 'aprovacao':
            asyncio.get_running_loop().call_soon(agente.responder_aprovacao, valor[1]['id'], *respostas.pop(0))
    return por, mandados


def test_cartao_com_print_e_programa_e_sempre_do_programa(tela_falsa):
    pytest.importorskip('claude_agent_sdk')
    agente._sempre.clear()
    por, mandados = _por([(True, True)])
    r = asyncio.run(agente._decidir(T + 'tela_clicar', {'x': 300, 'y': 200}, por, conversa=5))
    assert r.behavior == 'allow'
    cartao = mandados[0][1][1]
    assert cartao['alvo'] == 'Clicar em (300, 200)' and cartao['site'] == 'Sem título - Bloco de Notas'
    assert cartao['imagem'].startswith('data:image/png') and cartao['resumo'] == 'Na tela: Clicar em (300, 200)'
    # "Sempre neste programa": o próximo no Bloco de Notas passa; noutro programa, pede.
    mandados.clear()
    assert asyncio.run(agente._decidir(T + 'tela_digitar', {'texto': 'oi'}, por, conversa=5)).behavior == 'allow'
    assert mandados == []
    tela_falsa['programa'] = ('excel.exe', 'Planilha')
    por2, mandados2 = _por([(False,)])
    asyncio.run(agente._decidir(T + 'tela_digitar', {'texto': 'oi'}, por2, conversa=5))
    assert mandados2[0][1][1]['entrada'] == 'oi'
    agente._sempre.clear()


def test_no_solis_nem_pergunta(tela_falsa):
    pytest.importorskip('claude_agent_sdk')
    from claude_agent_sdk.types import PermissionResultDeny
    tela_falsa['programa'] = ('solis.exe', 'Solis')
    por, mandados = _por([])
    r = asyncio.run(agente._decidir(T + 'tela_clicar', {'x': 1, 'y': 1}, por, conversa=5))
    assert isinstance(r, PermissionResultDeny) and 'Solis' in r.message and mandados == []


def test_ver_e_livre_e_as_ferramentas_so_com_a_tela_ligada(monkeypatch):
    pytest.importorskip('claude_agent_sdk')
    import claude_agent_sdk
    por, mandados = _por([])
    assert asyncio.run(agente._decidir(T + 'tela_ver', {}, por)).behavior == 'allow' and mandados == []
    monkeypatch.setattr(claude_agent_sdk, 'create_sdk_mcp_server', lambda name, tools: tools)
    nomes = lambda: {t.name for t in agente._ferramentas_solis()}  # noqa: E731
    assert 'tela_clicar' not in nomes()
    monkeypatch.setattr(tela, 'ligada', lambda: True)
    assert {'tela_ver', 'tela_clicar', 'tela_digitar', 'tela_tecla', 'tela_rolar', 'tela_mover'} <= nomes()


@so_no_windows
def test_acao_devolve_o_print_de_depois(monkeypatch):
    pytest.importorskip('claude_agent_sdk')
    import claude_agent_sdk
    monkeypatch.setattr(claude_agent_sdk, 'create_sdk_mcp_server', lambda name, tools: tools)
    monkeypatch.setattr(tela, 'ligada', lambda: True)
    monkeypatch.setattr(tela, 'DEPOIS_S', 0)
    feitos = []
    monkeypatch.setattr(tela, 'clicar', lambda *a: feitos.append(a))
    monkeypatch.setattr(tela, 'ver', lambda: (b'png', {'largura': 1366, 'altura': 768, 'ativa': 'Bloco de Notas'}))
    f = next(t for t in agente._ferramentas_solis() if t.name == 'tela_clicar')
    r = asyncio.run(f.handler({'x': 10, 'y': 20}))
    assert feitos == [(10, 20, 'esquerdo', False)]
    assert r['content'][0]['text'].startswith('Cliquei.') and r['content'][1]['type'] == 'image'

    def recusa(*a):
        raise tela.TelaRecusada('fora')
    monkeypatch.setattr(tela, 'clicar', recusa)
    assert asyncio.run(f.handler({'x': 1, 'y': 1}))['content'][0]['text'] == 'Não fiz: fora.'


def test_rotas():
    cli = TestClient(main.app)
    assert cli.get('/tela').json()['ligada'] is False
    r = cli.put('/tela', json={'ligada': True}).json()
    assert r['ligada'] is r['disponivel']
    assert cli.put('/tela', json={'ligada': False}).json()['ligada'] is False
