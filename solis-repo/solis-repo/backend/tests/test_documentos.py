"""Criar documentos: a pasta das bibliotecas das skills, o que entra na sessão
do Claude, o arquivo criado e o abrir (só documento, só de onde o Solis trabalha)."""
import os
import time

import pytest
from fastapi.testclient import TestClient

from solis import documentos, main


@pytest.fixture
def ferramentas(tmp_path, monkeypatch):
    monkeypatch.setenv('SOLIS_FERRAMENTAS', str(tmp_path / 'ferramentas'))
    return tmp_path / 'ferramentas'


def _instalar_falso(base):
    for n in documentos.NODE:
        (base / 'node' / 'node_modules' / n).mkdir(parents=True)
        (base / 'node' / 'node_modules' / n / 'package.json').write_text('{}')
    for p in documentos.PYTHON:
        (base / 'python' / documentos.IMPORTA[p]).mkdir(parents=True)


def test_estado_e_env(ferramentas):
    e = documentos.estado()
    assert not e['pronto'] and 'docx' in e['falta'] and 'openpyxl' in e['falta']
    assert documentos.env() == {}
    _instalar_falso(ferramentas)
    assert documentos.estado()['pronto']
    env = documentos.env()
    assert env['NODE_PATH'].endswith(os.path.join('node', 'node_modules'))
    assert env['PYTHONPATH'].split(os.pathsep)[0].endswith('python')


def test_preparar_instala_na_pasta_do_solis(ferramentas, monkeypatch):
    feitos = []

    def rodar(cmd, **kw):
        feitos.append(cmd)
        if '--target' in cmd:
            _instalar_falso(ferramentas)
    monkeypatch.setattr(documentos, '_rodar', rodar)
    monkeypatch.setattr(documentos.shutil, 'which', lambda n: f'/bin/{n}')
    assert documentos.preparar()['pronto']
    npm, pip = feitos
    assert npm[1:4] == ['install', '--prefix', str(ferramentas / 'node')] and 'pptxgenjs' in npm
    assert pip[1:4] == ['-m', 'pip', 'install'] and str(ferramentas / 'python') in pip and 'python-pptx' in pip


def test_preparar_sem_node_avisa(ferramentas, monkeypatch):
    monkeypatch.setattr(documentos.shutil, 'which', lambda n: None)
    with pytest.raises(documentos.PrepararFalhou, match='npm'):
        documentos.preparar()


def test_o_que_o_claude_criou(tmp_path):
    (tmp_path / 'velho.pdf').write_bytes(b'x')
    (tmp_path / 'codigo.py').write_text('x')
    (tmp_path / 'node_modules').mkdir()
    antes = documentos.fotografia(tmp_path)
    time.sleep(0.02)
    (tmp_path / 'relatorio.docx').write_bytes(b'x')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'planilha.xlsx').write_bytes(b'x')
    (tmp_path / 'node_modules' / 'lixo.pdf').write_bytes(b'x')
    novos = documentos.novos(antes, documentos.fotografia(tmp_path))
    assert sorted(os.path.basename(n) for n in novos) == ['planilha.xlsx', 'relatorio.docx']


def test_abrir_so_documento_e_so_de_onde_o_solis_trabalha(tmp_path, monkeypatch):
    from solis import agente
    trabalho = tmp_path / 'trabalho'
    trabalho.mkdir()
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: trabalho)
    abertos = []
    monkeypatch.setattr(documentos, 'abrir', lambda c, pasta=False: abertos.append((os.path.basename(c), pasta)))
    (trabalho / 'relatorio.docx').write_bytes(b'x')
    fora = tmp_path / 'outra' / 'segredo.docx'
    fora.parent.mkdir()
    fora.write_bytes(b'x')
    c = TestClient(main.app)
    assert c.post('/arquivos/abrir', json={'caminho': str(trabalho / 'relatorio.docx')}).status_code == 200
    assert c.post('/arquivos/abrir', json={'caminho': str(trabalho / 'relatorio.docx'), 'pasta': True}).status_code == 200
    assert abertos == [('relatorio.docx', False), ('relatorio.docx', True)]
    assert c.post('/arquivos/abrir', json={'caminho': str(fora)}).status_code == 403


def test_abrir_recusa_executavel(tmp_path):
    exe = tmp_path / 'virus.exe'
    exe.write_bytes(b'MZ')
    with pytest.raises(documentos.PrepararFalhou):
        documentos.abrir(str(exe))


def test_rotas_de_estado_e_preparar(ferramentas, monkeypatch):
    c = TestClient(main.app)
    assert c.get('/documentos').json()['pronto'] is False
    monkeypatch.setattr(documentos, 'preparar', lambda: (_ for _ in ()).throw(documentos.PrepararFalhou('sem rede')))
    r = c.post('/documentos/preparar')
    assert r.status_code == 502 and r.json()['motivo'] == 'sem rede'
