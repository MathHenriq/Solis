"""O Solis como servidor (nuvem.py, 26/11/2026): com SOLIS_SERVIDOR=1, todo
pedido precisa do token; no PC, nada muda."""
import os
import stat

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from solis import cofre, main, nuvem

TOKEN = 'um-token-de-teste-bem-comprido-123'


@pytest.fixture
def servidor(monkeypatch):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setenv('SOLIS_TOKEN', TOKEN)
    return TestClient(main.app)


def test_no_pc_nada_muda():
    c = TestClient(main.app)
    assert c.get('/conversas').status_code == 200


def test_sem_token_nao_entra(servidor):
    r = servidor.get('/conversas')
    assert r.status_code == 401 and r.json() == {'erro': 'sem_token'}
    assert servidor.get('/conversas', headers={'Authorization': 'Bearer errado-errado-errado-errado'}).status_code == 401
    assert servidor.post('/conversas').status_code == 401


def test_saude_e_livre_pra_quem_confere_se_esta_de_pe(servidor):
    assert servidor.get('/saude').json() == {'ok': True}


def test_com_token_entra_pelo_cabecalho_ou_pelo_cookie(servidor):
    assert servidor.get('/conversas', headers={'Authorization': f'Bearer {TOKEN}'}).status_code == 200
    servidor.cookies.set('solis_token', TOKEN)
    assert servidor.get('/conversas').status_code == 200


def test_token_na_url_so_vale_no_websocket(servidor):
    # Na URL o token fica em histórico e log: só no WebSocket, que não aceita cabeçalho no navegador.
    assert servidor.get(f'/conversas?token={TOKEN}').status_code == 401
    with pytest.raises(WebSocketDisconnect) as fechou:
        with servidor.websocket_connect('/escuta') as ws:
            ws.receive_text()
    assert fechou.value.code == 1008


def test_token_fraco_nao_sobe(monkeypatch):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setenv('SOLIS_TOKEN', 'curto')
    with pytest.raises(nuvem.TokenFraco):
        nuvem.conferir_na_subida()


def test_sem_token_definido_cria_um_forte_so_do_usuario(monkeypatch, tmp_path):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    nuvem.conferir_na_subida()
    arquivo = tmp_path / 'token'
    valor = arquivo.read_text(encoding='utf-8').strip()
    assert len(valor) >= 40 and nuvem.token() == valor
    if os.name != 'nt':
        assert stat.S_IMODE(arquivo.stat().st_mode) == 0o600
    # Na próxima subida, o mesmo token (não troca sozinho).
    nuvem.esquecer()
    assert nuvem.token() == valor
    c = TestClient(main.app)
    assert c.get('/conversas', headers={'Authorization': f'Bearer {valor}'}).status_code == 200


# O cofre fora do Windows (cofre.py, "cofre:v2:"): roda em qualquer sistema,
# forçando o caminho do arquivo.

@pytest.fixture
def cofre_de_arquivo(monkeypatch):
    if cofre.AESGCM is None:
        pytest.skip('sem a biblioteca cryptography')
    monkeypatch.setattr(cofre, 'WINDOWS', False)
    monkeypatch.setattr(cofre, 'DISPONIVEL', True)
    cofre._chaves.clear()
    yield
    cofre._chaves.clear()


def test_cofre_de_arquivo_sela_e_abre(cofre_de_arquivo, tmp_path):
    selado = cofre.selar('chave-da-groq-secreta')
    assert selado.startswith(cofre.PREFIXO_ARQUIVO) and 'secreta' not in selado
    assert cofre.abrir(selado) == 'chave-da-groq-secreta'
    assert cofre.selar(selado) == selado
    # Duas vezes o mesmo texto não dá o mesmo selado (nonce novo).
    assert cofre.selar('x') != cofre.selar('x')
    chave = tmp_path / 'cofre.chave'
    assert chave.exists()
    if os.name != 'nt':
        assert stat.S_IMODE(chave.stat().st_mode) == 0o600


def test_cofre_de_arquivo_sem_a_chave_certa_nao_abre(cofre_de_arquivo, monkeypatch, tmp_path):
    selado = cofre.selar('segredo')
    # O banco foi copiado sem a chave (outra máquina): não abre, e não derruba.
    monkeypatch.setenv('SOLIS_COFRE_ARQUIVO', str(tmp_path / 'outra.chave'))
    assert cofre.abrir(selado) == cofre.ILEGIVEL
    assert cofre.abrir(cofre.PREFIXO_ARQUIVO + 'QUJD') == cofre.ILEGIVEL


def test_cofre_de_arquivo_nao_finge_abrir_o_do_windows(cofre_de_arquivo):
    assert cofre.abrir(cofre.PREFIXO_WINDOWS + 'QUJD') == cofre.ILEGIVEL


# O celular (26/11/2026): o servidor entrega a tela do Solis no mesmo endereço,
# com a página de entrar.

@pytest.fixture
def front(monkeypatch, tmp_path):
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<!doctype html><title>Solis</title>', encoding='utf-8')
    (dist / 'assets' / 'app-abc123.js').write_text('console.log(1)', encoding='utf-8')
    (tmp_path / 'segredo.txt').write_text('não sai', encoding='utf-8')
    monkeypatch.setenv('SOLIS_FRONT', str(dist))
    return dist


def test_o_navegador_sem_senha_vai_pra_pagina_de_entrar(servidor, front):
    r = servidor.get('/', headers={'Accept': 'text/html'}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/entrar'
    pagina = servidor.get('/entrar')
    assert pagina.status_code == 200 and 'name="token"' in pagina.text and 'Cole a senha' in pagina.text
    # A tela pedindo dados (sem pedir página) continua levando 401, não a página.
    assert servidor.get('/conversas').status_code == 401


def test_entrar_guarda_o_cookie_e_a_tela_abre(servidor, front):
    errado = servidor.post('/entrar', content='token=nao-e-esse', headers={'Content-Type': 'application/x-www-form-urlencoded'})
    assert errado.status_code == 401 and 'não é a do servidor' in errado.text
    r = servidor.post('/entrar', content=f'token={TOKEN}', headers={'Content-Type': 'application/x-www-form-urlencoded'},
                      follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/'
    biscoito = r.headers['set-cookie']
    assert f'solis_token={TOKEN}' in biscoito and 'HttpOnly' in biscoito and 'samesite=lax' in biscoito.lower()
    assert 'Secure' not in biscoito  # http puro (teste): o navegador não guardaria um Secure
    # Com o cookie: a tela, os arquivos dela e os dados.
    assert servidor.get('/').text.startswith('<!doctype html>')
    assert servidor.get('/conversa/12').text.startswith('<!doctype html>')  # rota da tela → index.html
    js = servidor.get('/assets/app-abc123.js')
    assert js.status_code == 200 and 'immutable' in js.headers['cache-control']
    # O tipo certo, fixo (o service worker é recusado se vier como texto).
    assert js.headers['content-type'].startswith('text/javascript')
    assert servidor.get('/').headers['cache-control'] == 'no-cache'
    assert servidor.get('/conversas').status_code == 200
    assert servidor.get('/assets/nao-existe.js').status_code == 404
    # Sair apaga o cookie.
    saiu = servidor.post('/sair', follow_redirects=False)
    assert saiu.status_code == 303 and 'solis_token=""' in saiu.headers['set-cookie']


def test_pelo_tunel_https_o_cookie_e_secure(servidor, front):
    r = servidor.post('/entrar', content=f'token={TOKEN}', follow_redirects=False,
                      headers={'Content-Type': 'application/x-www-form-urlencoded', 'X-Forwarded-Proto': 'https'})
    assert 'Secure' in r.headers['set-cookie']


def test_nao_sai_da_pasta_da_tela(servidor, front):
    servidor.cookies.set('solis_token', TOKEN)
    for caminho in ('/../segredo.txt', '/%2e%2e/segredo.txt', '/assets/../../segredo.txt'):
        r = servidor.get(caminho)
        assert 'não sai' not in r.text
    assert nuvem.arquivo_do_front('../segredo.txt') is None


def test_no_pc_nao_tem_pagina_de_entrar_nem_tela(front):
    c = TestClient(main.app)
    assert c.get('/entrar').status_code == 404
    assert c.get('/').status_code == 404
    assert c.get('/qualquer/coisa').status_code == 404


def test_tela_nao_construida_diz_onde_procurou(servidor, monkeypatch, tmp_path):
    monkeypatch.setenv('SOLIS_FRONT', str(tmp_path / 'sem-dist'))
    servidor.cookies.set('solis_token', TOKEN)
    r = servidor.get('/')
    assert r.status_code == 404 and r.json()['erro'] == 'tela_nao_construida'


def test_o_que_o_celular_busca_sem_cookie_e_livre(servidor, front):
    """O navegador busca o manifesto sem credencial, e o iPhone o ícone, ao pôr
    o Solis na Tela de Início: sem isso, nem nome nem ícone."""
    (front / 'manifest.webmanifest').write_text('{"name": "Solis"}', encoding='utf-8')
    (front / 'sw.js').write_text('// avisos', encoding='utf-8')
    manifesto = servidor.get('/manifest.webmanifest')
    assert manifesto.status_code == 200 and manifesto.headers['content-type'] == 'application/manifest+json'
    sw = servidor.get('/sw.js')
    assert sw.status_code == 200 and sw.headers['content-type'].startswith('text/javascript')
    # O resto continua pedindo a senha.
    assert servidor.get('/assets/app-abc123.js').status_code == 401
