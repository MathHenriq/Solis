"""Anexar arquivo e imagem na conversa (docs/PARIDADE.md)."""
import pytest
from fastapi.testclient import TestClient

from solis import agente, banco, main, roteador


@pytest.fixture(autouse=True)
def trabalho(tmp_path, monkeypatch):
    pasta = tmp_path / 'trabalho'
    pasta.mkdir()
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: pasta)
    return pasta


@pytest.fixture
def cliente():
    return TestClient(main.app)


def test_anexar_guarda_na_pasta_de_anexos(cliente, trabalho):
    r = cliente.post('/anexos?nome=foto da tela.png', content=b'\x89PNG...')
    a = r.json()
    assert r.status_code == 200 and a['nome'] == 'foto da tela.png' and a['tipo'] == 'image/png' and a['tamanho'] == 7
    assert a['caminho'].startswith(str((trabalho / 'anexos').resolve()))


def test_nome_perigoso_nao_sai_da_pasta(cliente, trabalho):
    a = cliente.post('/anexos?nome=../../fora.txt', content=b'oi').json()
    assert a['nome'] == 'fora.txt' and a['caminho'].startswith(str((trabalho / 'anexos').resolve()))


def test_vazio_e_grande_demais(cliente, monkeypatch):
    assert cliente.post('/anexos?nome=a.txt', content=b'').status_code == 400
    monkeypatch.setattr(main, 'ANEXO_MAX', 3)
    assert cliente.post('/anexos?nome=a.txt', content=b'1234').status_code == 413


def test_anexo_que_nao_veio_daqui_e_recusado(cliente, tmp_path):
    fora = tmp_path / 'segredo.txt'
    fora.write_text('x')
    c = banco.nova_conversa()
    r = cliente.post(f'/conversas/{c}/mensagens', json={'texto': 'leia', 'anexos': [str(fora)]})
    assert r.status_code == 400 and r.json()['erro'] == 'anexo_inexistente'
    assert banco.mensagens(c) == []


def test_mensagem_com_anexo_vai_pro_claude_com_o_caminho(cliente, monkeypatch):
    recebido = {}

    async def responder(ordem, modelo, conversa, historico, memorias, trechos, resumo, mensagem, *_, **__):
        recebido.update(ordem=ordem, mensagem=mensagem)

        async def fluxo():
            yield 'li'
        return fluxo(), 'claude'
    monkeypatch.setattr(roteador, 'responder', responder)
    monkeypatch.setattr(roteador, '_ordem', lambda: ['local', 'claude'])
    monkeypatch.setattr(roteador.cerebros, 'disponivel', lambda nome: True)

    async def nada(*_, **__):
        return None
    monkeypatch.setattr(main, '_depois', nada)
    a = cliente.post('/anexos?nome=nota.txt', content=b'codigo 1').json()
    c = banco.nova_conversa()
    cliente.post(f'/conversas/{c}/mensagens', json={'texto': 'o que diz?', 'anexos': [a['caminho']]})
    assert recebido['ordem'][0] == 'claude'
    assert a['caminho'] in recebido['mensagem'] and recebido['mensagem'].startswith('o que diz?')
    pessoa = banco.mensagens(c)[0]
    assert pessoa['texto'] == 'o que diz?' and pessoa['anexos'][0]['nome'] == 'nota.txt'


def test_anexo_aparece_no_historico_que_vai_pra_nuvem():
    historico = [
        {'id': 1, 'papel': 'pessoa', 'texto': 'veja', 'privada': False,
         'anexos': [{'nome': 'a.png', 'caminho': 'C:/t/anexos/a.png', 'tipo': 'image/png', 'tamanho': 1}]},
        {'id': 2, 'papel': 'solis', 'texto': 'vi', 'privada': False, 'anexos': []},
        {'id': 3, 'papel': 'pessoa', 'texto': 'e agora?', 'privada': False, 'anexos': []},
    ]
    prompt = roteador.prompt_nuvem([], [], None, historico, 'e agora?')
    assert 'C:/t/anexos/a.png' in prompt


def test_editar_apaga_os_anexos_da_mensagem():
    c = banco.nova_conversa()
    m = banco.adicionar(c, 'pessoa', 'veja')
    banco.guardar_anexos(m, [{'nome': 'a.txt', 'caminho': 'x', 'tipo': 'text/plain', 'tamanho': 1}])
    banco.apagar_desde(c, m)
    assert banco._con().execute('SELECT COUNT(*) FROM anexos').fetchone()[0] == 0
