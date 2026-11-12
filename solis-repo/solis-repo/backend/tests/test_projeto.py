"""Trabalhar num projeto (docs/PARIDADE.md): a pasta e o modo de cada
conversa, ler livre dentro dela, aceitar edições, o plano antes de fazer."""
import asyncio

import pytest
from fastapi.testclient import TestClient

pytest.importorskip('claude_agent_sdk')

from claude_agent_sdk.types import PermissionResultAllow  # noqa: E402

from solis import agente, banco, main  # noqa: E402


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    pasta = tmp_path / 'meu-projeto'
    (pasta / 'src').mkdir(parents=True)
    trabalho = tmp_path / 'trabalho'
    trabalho.mkdir()
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: trabalho)
    return pasta


def test_rota_guarda_a_pasta_e_o_modo(projeto, tmp_path):
    c = banco.nova_conversa()
    cliente = TestClient(main.app)
    assert cliente.get(f'/conversas/{c}/projeto').json()['pasta'] is None
    assert cliente.put(f'/conversas/{c}/projeto', json={'pasta': str(tmp_path / 'nao-existe')}).status_code == 400
    assert cliente.put(f'/conversas/{c}/projeto', json={'pasta': str(projeto), 'modo': 'turbo'}).status_code == 400
    banco.guardar_sessao_claude(c, 'velha')
    r = cliente.put(f'/conversas/{c}/projeto', json={'pasta': f'"{projeto}"', 'modo': 'aceitar'}).json()
    assert r['pasta'] == str(projeto.resolve()) and r['modo'] == 'aceitar' and r['recentes'] == [str(projeto.resolve())]
    # Outra pasta, outra sessão: a do Claude morava na pasta anterior.
    assert banco.sessao_claude(c) is None
    banco.guardar_sessao_claude(c, 'nova')
    cliente.put(f'/conversas/{c}/projeto', json={'pasta': str(projeto), 'modo': 'planejar'})
    assert banco.sessao_claude(c) == 'nova'  # só o modo mudou: a sessão segue


def test_ler_dentro_do_projeto_e_livre(projeto):
    assert agente._dentro('src/app.py', str(projeto))
    assert agente._dentro(str(projeto / 'README.md'), str(projeto))
    assert not agente._dentro(str(projeto.parent / 'outro' / 'x.txt'), str(projeto))


def _decidir(nome, entrada, projeto=None, modo='pedir', responder=None):
    mandados = []

    def por(tipo, valor=None):
        mandados.append((tipo, valor))
        if responder is not None and tipo == 'etapa' and valor[0] == 'aprovacao':
            asyncio.get_running_loop().call_soon(agente.responder_aprovacao, valor[1]['id'], responder)
    return asyncio.run(agente._decidir(nome, entrada, por, None, projeto, modo)), mandados


def test_aceitar_edicoes_dentro_do_projeto_nao_pede(projeto):
    r, mandados = _decidir('Edit', {'file_path': 'src/app.py'}, str(projeto), 'aceitar')
    assert isinstance(r, PermissionResultAllow) and mandados == []
    assert banco.acoes(1)[0]['resultado'].startswith('aceito pelo modo')


def test_aceitar_edicoes_fora_do_projeto_ainda_pede(projeto, tmp_path):
    fora = str(tmp_path / 'trabalho' / 'nota.txt')
    r, mandados = _decidir('Write', {'file_path': fora}, str(projeto), 'aceitar', responder=False)
    assert mandados[0][1][0] == 'aprovacao'


def test_comando_pede_mesmo_aceitando_edicoes(projeto):
    _, mandados = _decidir('Bash', {'command': 'rm -rf src'}, str(projeto), 'aceitar', responder=False)
    assert mandados[0][1][0] == 'aprovacao'


def test_plano_aprovado_sai_do_modo_de_planejar(projeto):
    r, mandados = _decidir('ExitPlanMode', {'plan': '1. ler\n2. editar'}, str(projeto), 'planejar', responder=True)
    pedido = mandados[0][1][1]
    assert pedido['resumo'] == 'Seguir com o plano' and pedido['alvo'] == '1. ler\n2. editar'
    assert isinstance(r, PermissionResultAllow)
    assert r.updated_permissions[0].type == 'setMode' and r.updated_permissions[0].mode == 'default'


def _opcoes_da_sessao(monkeypatch, **kw):
    import claude_agent_sdk
    capturadas = {}

    class Falso:
        def __init__(self, options):
            capturadas['opcoes'] = options

        async def __aenter__(self):
            raise RuntimeError('parou aqui')

        async def __aexit__(self, *_):
            return False
    monkeypatch.setattr(claude_agent_sdk, 'ClaudeSDKClient', Falso)
    mandados = []
    asyncio.run(agente._sessao('sistema', 'p', lambda t, v=None: mandados.append(t), **kw))
    # O CLI não abriu: quem espera recebe o erro e o fim, e não fica preso.
    assert mandados == ['erro', 'fim']
    return capturadas['opcoes']


def test_sessao_no_projeto_le_o_claude_md_e_trabalha_la(projeto, monkeypatch):
    o = _opcoes_da_sessao(monkeypatch, projeto=str(projeto), modo='planejar')
    assert o.cwd == str(projeto.resolve()) and o.setting_sources == ['project', 'local']
    assert o.permission_mode == 'plan' and str(projeto) in o.system_prompt


def test_sessao_sem_projeto_nao_le_nada_do_disco(projeto, monkeypatch):
    o = _opcoes_da_sessao(monkeypatch)
    assert o.setting_sources == [] and o.permission_mode == 'default'
    assert o.cwd == str(agente._pasta_trabalho().resolve())


# — O diff no cartão, o "sempre" e o modo depois do plano ————————————————————————

def test_diff_da_edicao_e_da_escrita(projeto):
    d = agente._diff('Edit', {'old_string': 'return a - b', 'new_string': 'return a + b'})
    assert '-return a - b' in d and '+return a + b' in d
    (projeto / 'src' / 'app.py').write_text('linha 1\nlinha 2\n', encoding='utf-8')
    d = agente._diff('Write', {'file_path': 'src/app.py', 'content': 'linha 1\nlinha dois\n'}, str(projeto))
    assert '-linha 2' in d and '+linha dois' in d and ' linha 1' in d
    novo = agente._diff('Write', {'file_path': 'novo.md', 'content': 'oi\n'}, str(projeto))
    assert novo.splitlines() == ['@@ -0,0 +1 @@', '+oi']
    assert agente._diff('Bash', {'command': 'dir'}) is None


def test_diff_longo_e_cortado():
    d = agente._diff('Write', {'file_path': 'x.txt', 'content': '\n'.join(str(i) for i in range(1000))}, limite=10)
    assert d.splitlines()[-1] == '… mais 991 linhas'


def test_cartao_leva_o_diff(projeto):
    _, mandados = _decidir('Edit', {'file_path': 'src/app.py', 'old_string': 'a', 'new_string': 'b'}, str(projeto),
                           responder=False)
    assert '+b' in mandados[0][1][1]['diff']


def _decidir_conversa(nome, entrada, conversa, responder=None, sempre=False, projeto=None, modo='pedir'):
    mandados = []

    def por(tipo, valor=None):
        mandados.append((tipo, valor))
        if responder is not None and tipo == 'etapa' and valor[0] == 'aprovacao':
            asyncio.get_running_loop().call_soon(agente.responder_aprovacao, valor[1]['id'], responder, sempre)
    return asyncio.run(agente._decidir(nome, entrada, por, None, projeto, modo, conversa)), mandados


def test_sempre_este_comando_nesta_conversa(projeto):
    c = banco.nova_conversa()
    agente._sempre.pop(c, None)
    _, m1 = _decidir_conversa('Bash', {'command': 'git status'}, c, responder=True, sempre=True)
    assert m1[0][1][0] == 'aprovacao'
    r, m2 = _decidir_conversa('Bash', {'command': 'git status'}, c)
    assert isinstance(r, PermissionResultAllow) and m2 == []
    # Outro comando, ou a mesma coisa em outra conversa, ainda pede.
    _, m3 = _decidir_conversa('Bash', {'command': 'git push'}, c, responder=False)
    _, m4 = _decidir_conversa('Bash', {'command': 'git status'}, c + 1000, responder=False)
    assert m3[0][1][0] == 'aprovacao' and m4[0][1][0] == 'aprovacao'
    agente._sempre.pop(c, None)


def test_sempre_nas_edicoes_vale_pra_qualquer_arquivo(projeto):
    c = banco.nova_conversa()
    _decidir_conversa('Write', {'file_path': 'a.txt', 'content': 'x'}, c, responder=True, sempre=True)
    r, m = _decidir_conversa('Edit', {'file_path': 'b.txt', 'old_string': 'x', 'new_string': 'y'}, c)
    assert isinstance(r, PermissionResultAllow) and m == []
    agente._sempre.pop(c, None)


def test_plano_aprovado_volta_a_conversa_pro_modo_de_pedir(projeto):
    c = banco.nova_conversa()
    banco.guardar_projeto(c, str(projeto), 'planejar')
    _, mandados = _decidir_conversa('ExitPlanMode', {'plan': 'x'}, c, responder=True, projeto=str(projeto), modo='planejar')
    assert banco.projeto_da_conversa(c) == {'pasta': str(projeto), 'modo': 'pedir'}
    assert ('etapa', ('modo', {'modo': 'pedir'})) in mandados


def test_rota_aceita_o_sempre():
    from concurrent.futures import Future
    fut = Future()
    agente._pendentes['s1'] = fut
    r = TestClient(main.app).post('/aprovacoes/s1', json={'aprovar': True, 'sempre': True})
    assert r.status_code == 200 and fut.result() == 'sempre'
    agente._pendentes.pop('s1', None)
