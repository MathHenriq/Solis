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
    with pytest.raises(RuntimeError):
        asyncio.run(agente._sessao('sistema', 'p', lambda *_: None, **kw))
    return capturadas['opcoes']


def test_sessao_no_projeto_le_o_claude_md_e_trabalha_la(projeto, monkeypatch):
    o = _opcoes_da_sessao(monkeypatch, projeto=str(projeto), modo='planejar')
    assert o.cwd == str(projeto.resolve()) and o.setting_sources == ['project', 'local']
    assert o.permission_mode == 'plan' and str(projeto) in o.system_prompt


def test_sessao_sem_projeto_nao_le_nada_do_disco(projeto, monkeypatch):
    o = _opcoes_da_sessao(monkeypatch)
    assert o.setting_sources == [] and o.permission_mode == 'default'
    assert o.cwd == str(agente._pasta_trabalho().resolve())
