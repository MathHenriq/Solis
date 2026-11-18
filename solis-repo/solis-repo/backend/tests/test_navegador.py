"""O navegador do Claude (docs/PARIDADE.md): o Chrome ou o Edge do PC, numa
janela com o perfil do Solis. Ler e abrir página é livre; clicar, escrever e
preencher pedem cartão, que diz o quê e em qual site."""
import asyncio
from pathlib import Path

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


# — o navegador de sempre (pela extensão do Playwright) ——————————————————————————
@pytest.fixture
def perfis(monkeypatch, tmp_path):
    """Os perfis do Chrome e do Edge de mentira (o LOCALAPPDATA do PC)."""
    base = tmp_path / 'Local'
    monkeypatch.setattr(navegador, '_perfis', lambda: base)

    def com_extensao(canal, perfil='Default', jeito='preferences'):
        p = base / navegador.PERFIS[canal] / perfil
        p.mkdir(parents=True, exist_ok=True)
        if jeito == 'pasta':
            (p / 'Extensions' / navegador.EXTENSAO_ID).mkdir(parents=True)
        else:
            (p / 'Preferences').write_text('{"extensions": {"settings": {"%s": {}}}}' % navegador.EXTENSAO_ID)
    return com_extensao


def test_de_sempre_e_a_escolha_com_o_sufixo(pc_com):
    pc_com('chrome', 'msedge')
    navegador.escolher('msedge:sempre')
    assert navegador.escolhido() == 'msedge' and navegador.de_sempre()
    navegador.escolher('chrome')
    assert navegador.escolhido() == 'chrome' and not navegador.de_sempre()
    with pytest.raises(ValueError):
        navegador.escolher('firefox:sempre')


def test_acha_a_extensao_como_o_playwright(pc_com, perfis):
    pc_com('chrome', 'msedge')
    assert not navegador.extensao_instalada('chrome')
    (navegador._perfis() / navegador.PERFIS['chrome'] / 'Profile 2').mkdir(parents=True)
    assert not navegador.extensao_instalada('chrome')  # um perfil sem ela
    perfis('chrome', 'Profile 3')
    assert navegador.extensao_instalada('chrome') and not navegador.extensao_instalada('msedge')
    perfis('msedge', jeito='pasta')
    assert navegador.extensao_instalada('msedge')
    navegador.escolher('chrome:sempre')
    e = navegador.estado()
    assert e['sempre'] and e['extensao'] and not e['chave'] and navegador.EXTENSAO_ID in e['extensao_url']


def test_comando_do_de_sempre_sem_perfil_nem_tamanho():
    c = navegador.comando('chrome', 9000, sempre=True)
    assert '--extension' in c and '--shared-browser-context' in c
    assert '--user-data-dir' not in c and '--viewport-size' not in c


def test_sem_a_extensao_o_claude_fica_sem_navegador(pc_com, perfis, monkeypatch):
    pc_com('chrome')
    monkeypatch.setattr(navegador, '_cli', lambda: Path(__file__))  # o servidor "instalado"
    subiu = []
    monkeypatch.setattr(navegador.subprocess, 'Popen', lambda *a, **k: subiu.append(a) or 1 / 0)
    navegador.escolher('chrome:sempre')
    assert navegador.servidor() is None and subiu == []
    with pytest.raises(navegador.NavegadorFalhou, match='sem a extensão'):
        navegador.abrir()


def test_a_chave_vai_pro_cofre_e_pro_ambiente(pc_com, monkeypatch):
    pc_com('chrome')
    from solis import cofre
    navegador.escolher('chrome:sempre')
    assert navegador._ambiente(True) is None
    assert navegador.guardar_chave('  abc123  ')['chave']
    guardada = banco.ajuste(navegador.CHAVE)
    assert 'abc123' not in guardada or not cofre.selado(guardada)  # selada (fora do Windows, fica como está)
    assert navegador._ambiente(True)['PLAYWRIGHT_MCP_EXTENSION_TOKEN'] == 'abc123'
    assert navegador._ambiente(False) is None  # a janela do Solis não leva a chave
    assert not navegador.guardar_chave('')['chave'] and banco.ajuste(navegador.CHAVE) is None


def test_rota_da_chave_nao_devolve_a_chave(pc_com):
    pc_com('chrome')
    cli = TestClient(main.app)
    r = cli.put('/navegador/chave', json={'chave': 'segredo-1'})
    assert r.status_code == 200 and r.json()['chave'] is True and 'segredo-1' not in r.text
    assert 'segredo-1' not in cli.get('/navegador').text
    assert cli.put('/navegador/chave', json={'chave': ''}).json()['chave'] is False


def test_no_de_sempre_abrir_site_novo_pede_e_no_mesmo_site_nao(pc_com):
    pytest.importorskip('claude_agent_sdk')
    pc_com('chrome')
    agente._sempre.clear()
    ir = lambda url: {'url': url}  # noqa: E731
    # Na janela do Solis, abrir é livre como antes.
    por, mandados = _por([])
    assert asyncio.run(agente._decidir(N + 'browser_navigate', ir('https://banco.com.br'), por)).behavior == 'allow'
    navegador.escolher('chrome:sempre')
    # No de sempre: andar no mesmo site é livre; um site novo pede, com o site de destino.
    assert asyncio.run(agente._decidir(N + 'browser_navigate', ir('https://loja.com.br/b'), por, conversa=3,
                                       pagina='https://www.loja.com.br/a')).behavior == 'allow'
    assert asyncio.run(agente._decidir(N + 'browser_snapshot', {}, por, conversa=3,
                                       pagina='https://loja.com.br/a')).behavior == 'allow'
    assert mandados == []
    por, mandados = _por([(True, True)])
    r = asyncio.run(agente._decidir(N + 'browser_navigate', ir('https://www.banco.com.br/extrato'), por, conversa=3,
                                    pagina='https://loja.com.br/a'))
    cartao = mandados[0][1][1]
    assert r.behavior == 'allow' and cartao['site'] == 'banco.com.br'
    assert cartao['alvo'] == 'Abrir https://www.banco.com.br/extrato'
    # "Sempre neste site": abrir de novo e agir nele não pedem mais; outro site pede.
    mandados.clear()
    assert asyncio.run(agente._decidir(N + 'browser_navigate', ir('https://banco.com.br/pix'), por, conversa=3,
                                       pagina='https://outro.com')).behavior == 'allow'
    assert asyncio.run(agente._decidir(N + 'browser_click', {'element': 'Ver'}, por, conversa=3,
                                       pagina='https://banco.com.br/pix')).behavior == 'allow'
    assert mandados == []
    por, mandados = _por([(False,)])
    r = asyncio.run(agente._decidir(N + 'browser_tabs', {'action': 'new', 'url': 'https://mail.com'}, por,
                                    conversa=3, pagina='https://banco.com.br/pix'))
    assert r.behavior == 'deny' and mandados[0][1][1]['site'] == 'mail.com'
    # Trocar de aba (sem endereço) continua livre.
    assert asyncio.run(agente._decidir(N + 'browser_tabs', {'action': 'select', 'index': 1}, por,
                                       conversa=3)).behavior == 'allow'
    agente._sempre.clear()


def test_link_abre_no_navegador_padrao_so_pagina_da_web(monkeypatch):
    """O app (Tauri) não abre link em nova janela: a tela manda pro servidor."""
    import webbrowser
    abertos = []
    monkeypatch.setattr(webbrowser, 'open', lambda url, new=0: abertos.append((url, new)) or True)
    cli = TestClient(main.app)
    r = cli.post('/link/abrir', json={'url': navegador.EXTENSAO_URL})
    assert r.status_code == 200 and r.json()['ok'] and abertos == [(navegador.EXTENSAO_URL, 2)]
    for ruim in ['file:///C:/Windows/System32/calc.exe', 'C:\Windows\notepad.exe', 'javascript:alert(1)',
                 'ms-settings:privacy', 'https://', 'https://x.com/a b', 'https://x.com/\nabc']:
        assert cli.post('/link/abrir', json={'url': ruim}).status_code == 400, ruim
    # Corpo que não é JSON (um site tentando pelo formulário) não passa.
    assert cli.post('/link/abrir', content='url=https://x.com',
                    headers={'Content-Type': 'text/plain'}).status_code == 422
    assert len(abertos) == 1
