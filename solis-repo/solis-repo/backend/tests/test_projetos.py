"""Projetos (docs/PARIDADE.md): nome, instruções, arquivos fixos e a pasta de
código; as conversas dentro herdam tudo — o projeto do claude.ai junto com a
pasta de projeto do Claude Code (decidido pelo Matheus, 13/11/2026)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solis import agente, banco, main, roteador


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    trabalho = tmp_path / 'trabalho'
    trabalho.mkdir()
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: trabalho)
    return TestClient(main.app)


def test_criar_editar_e_listar(cliente, tmp_path):
    codigo = tmp_path / 'codigo'
    codigo.mkdir()
    assert cliente.post('/projetos', json={'nome': '  '}).status_code == 400
    assert cliente.post('/projetos', json={'nome': 'X', 'pasta': str(tmp_path / 'nao')}).status_code == 400
    p = cliente.post('/projetos', json={'nome': 'Aulas WIT', 'instrucoes': 'Responda como professor.'}).json()
    assert p['nome'] == 'Aulas WIT' and p['arquivos'] == [] and p['pasta'] is None
    p = cliente.put(f'/projetos/{p["id"]}', json={'nome': 'Aulas', 'instrucoes': 'Curto.', 'pasta': str(codigo)}).json()
    assert p['instrucoes'] == 'Curto.' and p['pasta'] == str(codigo.resolve())
    lista = cliente.get('/projetos').json()['projetos']
    assert [(x['nome'], x['arquivos'], x['conversas']) for x in lista] == [('Aulas', 0, 0)]


def test_arquivos_fixos(cliente, tmp_path):
    p = cliente.post('/projetos', json={'nome': 'Casa'}).json()
    a = cliente.post(f'/projetos/{p["id"]}/arquivos', params={'nome': '../contrato.txt'}, content=b'aluguel 2000').json()
    assert a['nome'] == 'contrato.txt' and Path(a['caminho']).read_bytes() == b'aluguel 2000'
    assert Path(a['caminho']).parent == tmp_path / 'trabalho' / 'projetos' / str(p['id'])
    assert cliente.get(f'/projetos/{p["id"]}').json()['arquivos'][0]['nome'] == 'contrato.txt'
    assert cliente.delete(f'/projetos/{p["id"]}/arquivos/{a["id"]}').json() == {'ok': True}
    assert not Path(a['caminho']).exists()
    assert cliente.delete(f'/projetos/{p["id"]}/arquivos/999').status_code == 404


def test_conversa_no_projeto_herda_a_pasta_e_esquece_a_sessao(cliente, tmp_path):
    codigo = tmp_path / 'codigo'
    codigo.mkdir()
    p = cliente.post('/projetos', json={'nome': 'Site', 'pasta': str(codigo)}).json()
    c = banco.nova_conversa()
    banco.guardar_sessao_claude(c, 'velha')
    r = cliente.put(f'/conversas/{c}/projeto', json={'projeto': p['id'], 'modo': 'aceitar'}).json()
    assert r['projeto'] == {'id': p['id'], 'nome': 'Site'} and r['pasta'] == str(codigo.resolve()) and r['modo'] == 'aceitar'
    assert banco.sessao_claude(c) is None  # outro projeto: sessão nova
    banco.guardar_sessao_claude(c, 'nova')
    # Só o modo: o projeto fica, a sessão também.
    r = cliente.put(f'/conversas/{c}/projeto', json={'modo': 'planejar'}).json()
    assert r['projeto']['id'] == p['id'] and banco.sessao_claude(c) == 'nova'
    # O plano aprovado volta o modo sem tirar do projeto.
    assert banco.guardar_modo(c, 'pedir')['projeto']['id'] == p['id']
    # Tirar do projeto.
    r = cliente.put(f'/conversas/{c}/projeto', json={'projeto': None}).json()
    assert r['projeto'] is None and r['pasta'] is None
    assert cliente.put(f'/conversas/{c}/projeto', json={'projeto': 999}).status_code == 404


def test_apagar_projeto_deixa_as_conversas(cliente):
    p = cliente.post('/projetos', json={'nome': 'Velho'}).json()
    a = cliente.post(f'/projetos/{p["id"]}/arquivos', params={'nome': 'n.md'}, content=b'x').json()
    c = banco.nova_conversa()
    cliente.put(f'/conversas/{c}/projeto', json={'projeto': p['id']})
    assert cliente.delete(f'/projetos/{p["id"]}').json() == {'ok': True}
    assert banco.projeto_da_conversa(c)['projeto'] is None and banco.existe(c)
    assert not Path(a['caminho']).exists()


def test_o_que_chega_aos_cerebros(cliente):
    p = cliente.post('/projetos', json={'nome': 'Aulas', 'instrucoes': 'Use exemplos de escola.'}).json()
    txt = cliente.post(f'/projetos/{p["id"]}/arquivos', params={'nome': 'plano.md'}, content='Semana 1: IA'.encode()).json()
    cliente.post(f'/projetos/{p["id"]}/arquivos', params={'nome': 'foto.png'}, content=b'\x89PNG')
    c = banco.nova_conversa()
    assert roteador.nota_projeto(c, le_arquivos=True) == ''  # sem projeto, nada
    cliente.put(f'/conversas/{c}/projeto', json={'projeto': p['id']})
    claude = roteador.nota_projeto(c, le_arquivos=True)
    assert 'projeto "Aulas"' in claude and 'Use exemplos de escola.' in claude and txt['caminho'] in claude
    outros = roteador.nota_projeto(c, le_arquivos=False)
    assert '### plano.md\nSemana 1: IA' in outros and 'foto.png (não incluído aqui)' in outros
    assert txt['caminho'] not in outros
