"""O navegador do Claude (docs/PARIDADE.md): o Chrome ou o Edge do PC, numa
janela com o perfil do Solis. Ler e abrir página é livre; clicar, escrever e
preencher pedem cartão, que diz o quê e em qual site."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from solis import agente, banco, main, navegador

N = navegador.PREFIXO


@pytest.fixture
def pc_com(monkeypatch, tmp_path):
    """Um PC de mentira com os navegadores pedidos instalados."""
    def instalar(*canais):
        base = tmp_path / 'Program Files'
        for c in canais:
            exe = base / navegador.NAVEGADORES[c][1][0]
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_text('')
        monkeypatch.setattr(navegador, '_programas', lambda: [base])
        monkeypatch.setattr(navegador, 'parar', lambda: None)
    return instalar


def test_escolhido_prefere_o_chrome_e_respeita_a_escolha(pc_com):
    pc_com('chrome', 'msedge')
    assert navegador.instalados() == ['chrome', 'msedge']
    assert navegador.escolhido() == 'chrome'
    navegador.escolher('msedge')
    assert navegador.escolhido() == 'msedge'
    navegador.escolher('desligado')
    assert navegador.escolhido() is None and navegador.estado()['desligado']
    with pytest.raises(ValueError):
        navegador.escolher('firefox')


def test_sem_o_escolhido_no_pc_usa_o_que_tem(pc_com, monkeypatch):
    pc_com('msedge')
    banco.guardar_ajuste('navegador', 'chrome')  # desinstalado depois de escolhido
    assert navegador.escolhido() == 'msedge'
    monkeypatch.setattr(navegador, '_programas', lambda: [])  # nenhum navegador no PC
    assert navegador.escolhido() is None


def test_comando_usa_o_perfil_do_solis():
    c = navegador.comando('chrome', 9000)
    assert c[c.index('--browser') + 1] == 'chrome' and c[c.index('--port') + 1] == '9000'
    perfil = c[c.index('--user-data-dir') + 1]
    assert perfil == str(banco.caminho_padrao().parent / 'navegador' / 'chrome')
    assert '--shared-browser-context' in c and '--host' in c


def test_frases_do_cartao():
    r = lambda a, **e: navegador.resumo(N + a, e)  # noqa: E731
    assert r('browser_click', element='botão Enviar') == 'Clicar em botão Enviar'
    assert r('browser_click', element='link', doubleClick=True) == 'Clicar duas vezes em link'
    assert r('browser_type', element='campo Busca', text='tênis', submit=True) == 'Escrever em campo Busca e enviar'
    assert r('browser_fill_form', fields=[{}, {}]) == 'Preencher 2 campos do formulário'
    assert r('browser_press_key', key='Enter') == 'Apertar a tecla Enter'
    assert r('browser_select_option', element='Tamanho', values=['42']) == 'Escolher 42 em Tamanho'
    assert r('browser_handle_dialog', accept=False) == 'Recusar o aviso da página'
    d = lambda a, **e: navegador.detalhe(N + a, e)  # noqa: E731
    assert d('browser_type', text='tênis de corrida') == 'tênis de corrida'
    assert d('browser_fill_form', fields=[{'name': 'Nome', 'value': 'Matheus'}, {'name': 'Cidade', 'value': 'SP'}]) \
        == 'Nome: Matheus\nCidade: SP'
    assert d('browser_evaluate', function='() => document.title') == '() => document.title'
    assert d('browser_click', element='x') == ''


def test_site_e_pagina():
    assert navegador.site('https://www.mercadolivre.com.br/ofertas?x=1') == 'mercadolivre.com.br'
    assert navegador.site(None) == ''
    texto = '### Page\n- Page URL: https://example.com/\n- Page Title: Example Domain\n'
    assert navegador.pagina_do_resultado(texto) == 'https://example.com/'
    assert navegador.pagina_do_resultado('nada') is None
    assert navegador.alvo(N + 'browser_navigate', {'url': 'https://g1.globo.com'}, None) == 'https://g1.globo.com'
    assert navegador.alvo(N + 'browser_snapshot', {}, 'https://www.g1.globo.com/x') == 'g1.globo.com'
    assert navegador.alvo(N + 'browser_click', {'element': 'Entrar'}, None) == 'Cliquei em Entrar'
    assert navegador.alvo(N + 'browser_fill_form', {'fields': [{}]}, None) == 'Preenchi 1 campo do formulário'


def _por(respostas):
    mandados = []

    def por(tipo, valor=None):
        mandados.append((tipo, valor))
        if tipo == 'etapa' and valor[0] == 'aprovacao':
            asyncio.get_running_loop().call_soon(agente.responder_aprovacao, valor[1]['id'], *respostas.pop(0))
    return por, mandados


def test_ler_e_abrir_sao_livres():
    pytest.importorskip('claude_agent_sdk')
    por, mandados = _por([])
    for a in ('browser_snapshot', 'browser_navigate', 'browser_take_screenshot', 'browser_tabs'):
        assert asyncio.run(agente._decidir(N + a, {'url': 'https://x.com'}, por)).behavior == 'allow'
    assert mandados == []
    assert 'mcp__navegador__browser_run_code_unsafe' in navegador.PROIBIDAS


def test_clicar_pede_cartao_com_o_site_e_sempre_vale_pro_site():
    pytest.importorskip('claude_agent_sdk')
    from claude_agent_sdk.types import PermissionResultDeny
    agente._sempre.clear()
    por, mandados = _por([(False,), (True, True)])
    entrada = {'element': 'botão Comprar', 'target': 'e12'}
    r = asyncio.run(agente._decidir(N + 'browser_click', entrada, por, conversa=7,
                                    pagina='https://www.loja.com.br/item'))
    assert isinstance(r, PermissionResultDeny)
    cartao = mandados[0][1][1]
    assert cartao['alvo'] == 'Clicar em botão Comprar' and cartao['site'] == 'loja.com.br'
    assert cartao['resumo'] == 'No navegador: Clicar em botão Comprar' and 'entrada' not in cartao
    # Escrever: o texto inteiro vai no cartão. "Sempre": vale pra este site...
    mandados.clear()
    r = asyncio.run(agente._decidir(N + 'browser_type', {'element': 'Busca', 'text': 'fone'}, por, conversa=7,
                                    pagina='https://loja.com.br/'))
    assert r.behavior == 'allow' and mandados[0][1][1]['entrada'] == 'fone'
    mandados.clear()
    r = asyncio.run(agente._decidir(N + 'browser_click', entrada, por, conversa=7, pagina='https://loja.com.br/b'))
    assert r.behavior == 'allow' and mandados == []
    # ... e não pra outro site, nem pra outra conversa.
    por2, mandados2 = _por([(False,), (False,)])
    asyncio.run(agente._decidir(N + 'browser_click', entrada, por2, conversa=7, pagina='https://banco.com.br'))
    asyncio.run(agente._decidir(N + 'browser_click', entrada, por2, conversa=8, pagina='https://loja.com.br'))
    assert len([m for m in mandados2 if m[1][0] == 'aprovacao']) == 2
    agente._sempre.clear()


def test_o_que_o_navegador_guarda_e_livre_de_ler(tmp_path):
    arquivo = navegador.pasta_saida() / 'page-1.yml'
    assert agente._dentro(str(arquivo))
    assert not agente._dentro(str(tmp_path.parent / 'outro.yml'))


def test_rotas(pc_com, monkeypatch):
    pc_com('chrome', 'msedge')
    cli = TestClient(main.app)
    r = cli.get('/navegador').json()
    assert r['escolhido'] == 'chrome' and [n['nome'] for n in r['instalados']] == ['Google Chrome', 'Microsoft Edge']
    assert cli.put('/navegador', json={'navegador': 'msedge'}).json()['escolhido'] == 'msedge'
    assert cli.put('/navegador', json={'navegador': 'opera'}).status_code == 400
    abertos = []
    monkeypatch.setattr(navegador, 'abrir', lambda: abertos.append(1))
    assert cli.post('/navegador/abrir').status_code == 200 and abertos == [1]

    def falha():
        raise navegador.NavegadorFalhou('navegador desligado')
    monkeypatch.setattr(navegador, 'abrir', falha)
    r = cli.post('/navegador/abrir')
    assert r.status_code == 503 and r.json()['motivo'] == 'navegador desligado'
