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
