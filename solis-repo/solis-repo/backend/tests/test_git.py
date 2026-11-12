"""O git da pasta de projeto na tela: estado, diff, commit, push (com um
remoto de verdade, num repositório "bare" do teste) e o PR sem gh."""
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from solis import banco, git, main

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='sem git')


def _g(pasta, *args):
    return subprocess.run(['git', '-C', str(pasta), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    remoto = tmp_path / 'remoto.git'
    _g(tmp_path, 'init', '--bare', '-q', '-b', 'main', str(remoto))
    pasta = tmp_path / 'projeto'
    pasta.mkdir()
    _g(pasta, 'init', '-q', '-b', 'main')
    _g(pasta, 'config', 'user.name', 'Teste')
    _g(pasta, 'config', 'user.email', 'teste@exemplo.invalid')
    _g(pasta, 'config', 'commit.gpgsign', 'false')
    (pasta / 'app.py').write_text('def soma(a, b):\n    return a + b\n', encoding='utf-8')
    _g(pasta, 'add', '-A')
    _g(pasta, 'commit', '-q', '-m', 'primeiro')
    _g(pasta, 'remote', 'add', 'origin', str(remoto))
    return pasta, remoto


def test_fora_de_repositorio(tmp_path):
    assert git.estado(str(tmp_path)) == {'repo': False}


def test_estado_com_mudado_novo_e_apagado(repo):
    pasta, _ = repo
    (pasta / 'app.py').write_text('def soma(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n', encoding='utf-8')
    (pasta / 'novo.txt').write_text('um\ndois\n', encoding='utf-8')
    e = git.estado(str(pasta))
    assert e['repo'] and e['ramo'] == 'main' and e['upstream'] is None
    por_nome = {a['caminho']: a for a in e['arquivos']}
    assert por_nome['app.py'] == {'caminho': 'app.py', 'status': 'M', 'mais': 4, 'menos': 0}
    assert por_nome['novo.txt'] == {'caminho': 'novo.txt', 'status': '?', 'mais': 2, 'menos': 0}


def test_diff_de_mudado_e_de_novo(repo):
    pasta, _ = repo
    (pasta / 'app.py').write_text('def soma(a, b):\n    return b + a\n', encoding='utf-8')
    (pasta / 'novo.txt').write_text('oi\n', encoding='utf-8')
    d = git.diff(str(pasta), 'app.py')
    assert d.startswith('@@') and '-    return a + b' in d and '+    return b + a' in d
    assert git.diff(str(pasta), 'novo.txt') == '@@ -0,0 +1,1 @@\n+oi'
    with pytest.raises(git.GitFalhou):
        git.diff(str(pasta), '../fora.txt')


def test_commit_e_push_criando_o_upstream(repo):
    pasta, remoto = repo
    (pasta / 'novo.txt').write_text('oi\n', encoding='utf-8')
    with pytest.raises(git.GitFalhou):
        git.commit(str(pasta), '   ')
    r = git.commit(str(pasta), 'acrescenta novo.txt\n\ncom o corpo')
    assert r['mensagem'] == 'acrescenta novo.txt' and len(r['hash']) >= 7
    e = git.estado(str(pasta))
    assert e['arquivos'] == []
    git.push(str(pasta))
    e = git.estado(str(pasta))
    assert e['upstream'] == 'origin/main' and e['frente'] == 0
    assert 'acrescenta novo.txt' in _g(remoto, 'log', '--oneline')
    # Mais um commit: à frente 1, e o push seguinte vai pelo upstream.
    (pasta / 'outro.txt').write_text('x\n', encoding='utf-8')
    git.commit(str(pasta), 'outro')
    assert git.estado(str(pasta))['frente'] == 1
    git.push(str(pasta))
    assert git.estado(str(pasta))['frente'] == 0


def test_commit_recusado_pelo_hook_nao_deixa_o_indice_pela_metade(repo):
    pasta, _ = repo
    gancho = pasta / '.git' / 'hooks' / 'pre-commit'
    gancho.write_text('#!/bin/sh\necho "recusado pelo hook" >&2\nexit 1\n', encoding='utf-8')
    gancho.chmod(0o755)
    (pasta / 'novo.txt').write_text('oi\n', encoding='utf-8')
    with pytest.raises(git.GitFalhou, match='recusado pelo hook'):
        git.commit(str(pasta), 'tentativa')
    assert _g(pasta, 'diff', '--cached', '--name-only') == ''


def test_pr_sem_gh(repo, monkeypatch):
    monkeypatch.setattr(git.shutil, 'which', lambda nome: None)
    with pytest.raises(git.GitFalhou, match='gh'):
        git.pr(str(repo[0]))


def test_rotas(repo):
    pasta, _ = repo
    c = banco.nova_conversa()
    cliente = TestClient(main.app)
    assert cliente.get(f'/conversas/{c}/git').json() == {'repo': False}  # sem projeto
    assert cliente.post(f'/conversas/{c}/git/push').status_code == 400
    banco.guardar_projeto(c, str(pasta), 'pedir')
    (pasta / 'app.py').write_text('mudou\n', encoding='utf-8')
    e = cliente.get(f'/conversas/{c}/git').json()
    assert e['ramo'] == 'main' and e['arquivos'][0]['caminho'] == 'app.py'
    assert '+mudou' in cliente.get(f'/conversas/{c}/git/diff', params={'arquivo': 'app.py'}).json()['diff']
    r = cliente.post(f'/conversas/{c}/git/commit', json={'mensagem': 'muda o app'})
    assert r.status_code == 200 and r.json()['mensagem'] == 'muda o app'
    assert banco.acoes(1)[0]['ferramenta'] == 'git_commit'
    r = cliente.post(f'/conversas/{c}/git/commit', json={'mensagem': 'nada'})
    assert r.status_code == 400 and r.json()['erro'] == 'git'
    assert banco.acoes(1)[0]['ok'] is False or banco.acoes(1)[0]['ok'] == 0
