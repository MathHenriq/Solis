"""Hooks do Claude pela tela: lidos e gravados no ~/.claude/settings.json, só na
chave "hooks", sem mexer no resto (o arquivo é do Claude Code)."""
import json

import pytest
from fastapi.testclient import TestClient

from solis import hooks, main


@pytest.fixture
def casa(monkeypatch, tmp_path):
    monkeypatch.setattr(hooks, '_casa', lambda: tmp_path)
    (tmp_path / '.claude').mkdir()
    return tmp_path


def _arquivo(casa):
    return json.loads((casa / '.claude' / 'settings.json').read_text(encoding='utf-8'))


def test_adiciona_sem_mexer_no_resto(casa):
    (casa / '.claude' / 'settings.json').write_text(json.dumps({'model': 'opus', 'permissions': {'allow': ['Read']}}))
    h = hooks.salvar('PreToolUse', 'Bash', 'echo antes', 30)
    assert (h['evento'], h['ferramenta'], h['comando'], h['tempo'], h['editavel']) == ('PreToolUse', 'Bash', 'echo antes', 30, True)
    hooks.salvar('PreToolUse', 'Bash', 'echo outro')
    hooks.salvar('Stop', 'ignorado: Stop não tem ferramenta', 'notify-send pronto')
    d = _arquivo(casa)
    assert d['model'] == 'opus' and d['permissions'] == {'allow': ['Read']}
    assert d['hooks']['PreToolUse'] == [{'matcher': 'Bash', 'hooks': [
        {'type': 'command', 'command': 'echo antes', 'timeout': 30}, {'type': 'command', 'command': 'echo outro'}]}]
    assert d['hooks']['Stop'] == [{'hooks': [{'type': 'command', 'command': 'notify-send pronto'}]}]
    assert [l['rotulo'] for l in hooks.listar()] == ['Antes de usar uma ferramenta'] * 2 + ['Quando a resposta termina']


def test_mudar_e_remover(casa):
    a = hooks.salvar('PostToolUse', 'Write|Edit', 'npx prettier --write')
    b = hooks.salvar('PostToolUse', 'Write|Edit', 'npx prettier --write')  # igual: duas linhas, ids diferentes
    assert a['id'] != b['id'] and len(hooks.listar()) == 2
    c = hooks.salvar('PostToolUse', 'Edit', 'npx eslint --fix', antigo=a['id'])
    grupos = _arquivo(casa)['hooks']['PostToolUse']
    assert [g['matcher'] for g in grupos] == ['Write|Edit', 'Edit'] and len(grupos[0]['hooks']) == 1
    hooks.remover(c['id'])
    hooks.remover(hooks.listar()[0]['id'])
    assert 'hooks' not in _arquivo(casa)  # vazio, a chave sai inteira
    with pytest.raises(hooks.HookInvalido, match='não existe'):
        hooks.remover(c['id'])


def test_os_de_fora_aparecem_mas_nao_se_mexem(casa):
    (casa / '.claude' / 'settings.json').write_text(json.dumps({'hooks': {
        'PreCompact': [{'hooks': [{'type': 'command', 'command': 'echo resumo'}]}],
        'Stop': [{'hooks': [{'type': 'prompt', 'prompt': 'Terminou tudo?'}]}]}}))
    lista = hooks.listar()
    assert [(l['rotulo'], l['editavel']) for l in lista] == [('PreCompact', False), ('Quando a resposta termina', False)]
    with pytest.raises(hooks.HookInvalido):
        hooks.remover(lista[0]['id'])


@pytest.mark.parametrize('args, motivo', [
    (('Notification', '', 'x'), 'evento'),
    (('Stop', '', '   '), 'comando'),
    (('Stop', '', 'a\nb'), 'comando'),
    (('Stop', '', 'x', 0), 'tempo'),
    (('Stop', '', 'x', 601), 'tempo'),
])
def test_recusa(casa, args, motivo):
    with pytest.raises(hooks.HookInvalido, match=motivo):
        hooks.salvar(*args)


def test_arquivo_quebrado_nao_e_sobrescrito(casa):
    (casa / '.claude' / 'settings.json').write_text('{ isto não é json')
    with pytest.raises(hooks.HookInvalido, match='não é JSON'):
        hooks.salvar('Stop', '', 'echo oi')
    assert (casa / '.claude' / 'settings.json').read_text() == '{ isto não é json'


def test_rotas(casa):
    cli = TestClient(main.app)
    r = cli.get('/hooks').json()
    assert r['hooks'] == [] and [e['id'] for e in r['eventos'] if e['ferramenta']] == ['PreToolUse', 'PostToolUse']
    h = cli.post('/hooks', json={'evento': 'PreToolUse', 'ferramenta': 'Bash', 'comando': 'echo a'}).json()
    assert cli.put(f'/hooks/{h["id"]}', json={'evento': 'Stop', 'comando': 'echo b'}).json()['evento'] == 'Stop'
    assert cli.post('/hooks', json={'evento': 'Nada', 'comando': 'x'}).json()['motivo'] == 'evento'
    [l] = cli.get('/hooks').json()['hooks']
    assert cli.delete(f'/hooks/{l["id"]}').json() == {'ok': True}
    assert cli.delete(f'/hooks/{l["id"]}').status_code == 404
    (casa / '.claude' / 'settings.json').write_text('quebrado')
    assert cli.get('/hooks').status_code == 409
