"""Voltar atrás e o terminal ao vivo (docs/PARIDADE.md → Trabalhar num projeto):
os pontos de volta de cada fala, a rota que volta os arquivos pelo CLI, e a
saída do comando lida enquanto ele roda."""
import asyncio

import pytest
from fastapi.testclient import TestClient

pytest.importorskip('claude_agent_sdk')

import claude_agent_sdk  # noqa: E402
from claude_agent_sdk import (  # noqa: E402
    AssistantMessage, SystemMessage, TaskStartedMessage, ToolResultBlock, ToolUseBlock, UserMessage,
)

from solis import agente, banco, main  # noqa: E402


def _conversa_com_falas(n=3):
    c = banco.nova_conversa()
    ids = []
    for i in range(n):
        ids.append(banco.adicionar(c, 'pessoa', f'pedido {i}'))
        banco.adicionar(c, 'solis', f'feito {i}', cerebro='claude')
    return c, ids


# — os pontos no banco ————————————————————————————————————————————————————————
def test_ponto_e_da_ultima_fala_e_so_conta_quando_muda_arquivo():
    c, (a, b, d) = _conversa_com_falas()
    banco.guardar_ponto(c, 's1', 'u-d', '/p')
    assert banco.ultimo_ponto_mudado(c) is None  # o Claude só leu: nada pra voltar
    banco.ponto_mudou(c, 's1')
    assert banco.ultimo_ponto_mudado(c) == d
    assert banco.pontos_desde(c, a) == [{'mensagem': d, 'sessao': 's1', 'uuid': 'u-d', 'pasta': '/p'}]
    assert banco.pontos_desde(c, d + 1) == []
    banco.limpar_pontos(c, a)
    assert banco.ultimo_ponto_mudado(c) is None


def test_editar_a_fala_nao_perde_o_ponto():
    # Editar apaga a fala; o que o Claude mudou nela ainda tem que voltar.
    c, (a, b, _) = _conversa_com_falas()
    banco.apagar_desde(c, b + 1)  # some a fala `d`, como no editar
    banco.adicionar(c, 'pessoa', 'outro pedido')
    banco.guardar_ponto(c, 's1', 'u', '/p')
    banco.ponto_mudou(c, 's1')
    banco.apagar_desde(c, b)
    assert banco.pontos_desde(c, a)


# — a rota ————————————————————————————————————————————————————————————————————
@pytest.fixture
def voltar_falso(monkeypatch):
    chamadas = []

    async def voltar(pontos, simular=False):
        chamadas.append((pontos, simular))
        return {'arquivos': ['/p/a.py'], 'mais': 1, 'menos': 2, 'erros': []}

    monkeypatch.setattr(agente, 'voltar', voltar)
    return chamadas


def test_rota_simula_volta_e_limpa(voltar_falso):
    c, (a, b, d) = _conversa_com_falas()
    banco.guardar_ponto(c, 's1', 'u-d', '/p')
    banco.ponto_mudou(c, 's1')
    cliente = TestClient(main.app)
    assert cliente.get(f'/conversas/{c}/voltar').json() == {'ultima': d}

    r = cliente.post(f'/conversas/{c}/voltar', json={'desde': b, 'simular': True}).json()
    assert r['arquivos'] == ['/p/a.py'] and voltar_falso[-1][1] is True
    assert banco.ultimo_ponto_mudado(c) == d  # simular não muda nada

    r = cliente.post(f'/conversas/{c}/voltar', json={'desde': b}).json()
    assert r['mais'] == 1 and voltar_falso[-1] == ([{'mensagem': d, 'sessao': 's1', 'uuid': 'u-d', 'pasta': '/p'}], False)
    assert cliente.get(f'/conversas/{c}/voltar').json() == {'ultima': None}
    assert banco.acoes(1)[0]['ferramenta'] == 'voltar_atras'
    assert len(banco.mensagens(c)) == 6  # só os arquivos: a conversa fica


def test_rota_volta_a_conversa_junto(voltar_falso):
    c, (a, b, d) = _conversa_com_falas()
    banco.guardar_ponto(c, 's1', 'u-d', '/p')
    banco.ponto_mudou(c, 's1')
    banco.guardar_sessao_claude(c, 's1')
    cliente = TestClient(main.app)
    cliente.post(f'/conversas/{c}/voltar', json={'desde': b, 'conversa': True})
    assert [m['texto'] for m in banco.mensagens(c)] == ['pedido 0', 'feito 0']
    assert banco.sessao_claude(c) is None


def test_rota_sem_ponto_nao_chama_o_cli(voltar_falso):
    c, (a, _, _) = _conversa_com_falas()
    r = TestClient(main.app).post(f'/conversas/{c}/voltar', json={'desde': a, 'simular': True}).json()
    assert r['arquivos'] == [] and voltar_falso == []


def test_rota_espera_a_resposta_acabar(voltar_falso):
    c, (a, _, _) = _conversa_com_falas()
    main._paradas[c] = asyncio.Event()
    try:
        assert TestClient(main.app).post(f'/conversas/{c}/voltar', json={'desde': a}).status_code == 409
    finally:
        main._paradas.pop(c, None)


# — voltar as sessões, pelo CLI ———————————————————————————————————————————————
class ClienteFalso:
    feitos: list = []

    def __init__(self, options):
        self.sessao = options.resume
        self._query = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _send_control_request(self, pedido):
        self.feitos.append(('dry', self.sessao, pedido['user_message_id']))
        return {'canRewind': True, 'filesChanged': [f'/p/{self.sessao}.py'], 'insertions': 1, 'deletions': 1}

    async def rewind_files(self, uuid):
        self.feitos.append(('volta', self.sessao, uuid))


def test_volta_da_sessao_mais_nova_pra_mais_antiga(monkeypatch, tmp_path):
    ClienteFalso.feitos = []
    monkeypatch.setattr(claude_agent_sdk, 'ClaudeSDKClient', ClienteFalso)
    p = str(tmp_path)
    pontos = [
        {'mensagem': 3, 'sessao': 'A', 'uuid': 'a3', 'pasta': p},
        {'mensagem': 5, 'sessao': 'A', 'uuid': 'a5', 'pasta': p},
        {'mensagem': 8, 'sessao': 'B', 'uuid': 'b8', 'pasta': p},
    ]
    r = asyncio.run(agente.voltar(pontos))
    # B primeiro; A no primeiro ponto dela (a3), não no a5.
    assert ClienteFalso.feitos == [('dry', 'B', 'b8'), ('volta', 'B', 'b8'), ('dry', 'A', 'a3'), ('volta', 'A', 'a3')]
    assert r == {'arquivos': ['/p/B.py', '/p/A.py'], 'mais': 2, 'menos': 2, 'erros': []}

    ClienteFalso.feitos = []
    asyncio.run(agente.voltar(pontos, simular=True))
    assert [f[0] for f in ClienteFalso.feitos] == ['dry', 'dry']


def test_pasta_que_sumiu_vira_erro(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_agent_sdk, 'ClaudeSDKClient', ClienteFalso)
    r = asyncio.run(agente.voltar([{'mensagem': 1, 'sessao': 'A', 'uuid': 'a', 'pasta': str(tmp_path / 'sumiu')}]))
    assert r['erros'] and r['arquivos'] == []


# — a saída do comando ————————————————————————————————————————————————————————
def test_limpar_saida_tira_cor_e_barra_de_progresso():
    assert agente._limpar_saida('\x1b[32mok\x1b[0m\r\nbaixando 10%\rbaixando 100%\nfim') == 'ok\nbaixando 100%\nfim'
    longa = '\n'.join(f'linha {i}' for i in range(100))
    assert agente._limpar_saida(longa).split('\n')[0] == f'linha {100 - agente.SAIDA_LINHAS}'


def test_segue_o_arquivo_da_saida_enquanto_roda(monkeypatch, tmp_path):
    monkeypatch.setattr(agente.tempfile, 'gettempdir', lambda: str(tmp_path))
    tarefas = tmp_path / 'claude' / 'abc123' / 'sessao-1' / 'tasks'
    tarefas.mkdir(parents=True)
    arquivo = tarefas / 't1.output'
    mandados = []

    async def rodar():
        leitura = asyncio.ensure_future(agente._seguir_saida('sessao-1', 't1', 'tool-1', 'npm test',
                                                             lambda t, v: mandados.append(v), passo=0.01))
        await asyncio.sleep(0.05)  # o arquivo ainda não existe: nada
        arquivo.write_bytes(b'linha 1\n')
        await asyncio.sleep(0.05)
        with arquivo.open('ab') as f:
            f.write('linha 2 ção\n'.encode())
        await asyncio.sleep(0.05)
        leitura.cancel()

    asyncio.run(rodar())
    textos = [d['saida'] for _, d in mandados]
    assert textos == ['linha 1\n', 'linha 1\nlinha 2 ção\n']
    assert mandados[0] == ('saida', {'id': 'tool-1', 'comando': 'npm test', 'saida': 'linha 1\n'})


# — o laço da sessão, com um CLI falso ———————————————————————————————————————————
class SessaoFalsa:
    mensagens: list = []
    opcoes = None

    def __init__(self, options):
        SessaoFalsa.opcoes = options

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def query(self, prompt):
        pass

    async def receive_response(self):
        for m in self.mensagens:
            if callable(m):
                await m()
            else:
                yield m


def test_sessao_marca_o_ponto_a_mudanca_e_a_saida(monkeypatch, tmp_path):
    c, (_, _, d) = _conversa_com_falas()
    monkeypatch.setattr(agente.tempfile, 'gettempdir', lambda: str(tmp_path))
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: tmp_path)
    monkeypatch.setattr(agente, '_ferramentas_solis', lambda: None)
    tarefas = tmp_path / 'claude' / 'x' / 'S1' / 'tasks'
    tarefas.mkdir(parents=True)
    (tarefas / 'tk.output').write_bytes(b'compilando...\n')

    async def esperar():
        await asyncio.sleep(0.5)  # a leitura da saída roda neste meio tempo

    SessaoFalsa.mensagens = [
        SystemMessage(subtype='init', data={'session_id': 'S1'}),
        UserMessage(content='pedido 2', uuid='U-2'),
        AssistantMessage(content=[ToolUseBlock(id='e1', name='Edit', input={'file_path': 'a.py'}),
                                  ToolUseBlock(id='b1', name='Bash', input={'command': 'make'})], model='m'),
        UserMessage(content=[ToolResultBlock(tool_use_id='e1', content='ok', is_error=False)]),
        TaskStartedMessage(subtype='task_started', data={'task_id': 'tk', 'tool_use_id': 'b1', 'task_type': 'local_bash'},
                           task_id='tk', description='make', uuid='x', session_id='S1', tool_use_id='b1',
                           task_type='local_bash'),
        esperar,
        UserMessage(content=[ToolResultBlock(tool_use_id='b1', content='compilando...\npronto', is_error=False)]),
    ]
    monkeypatch.setattr(claude_agent_sdk, 'ClaudeSDKClient', SessaoFalsa)
    mandados = []
    asyncio.run(agente._sessao('sis', 'pedido 2', lambda t, v=None: mandados.append((t, v)), conversa=c))

    assert SessaoFalsa.opcoes.enable_file_checkpointing
    assert SessaoFalsa.opcoes.extra_args == {'replay-user-messages': None}
    assert banco.pontos_desde(c, d) == [{'mensagem': d, 'sessao': 'S1', 'uuid': 'U-2', 'pasta': str(tmp_path)}]
    ao_vivo = [v for t, v in mandados if t == 'aovivo']
    assert ao_vivo and ao_vivo[0] == ('saida', {'id': 'b1', 'comando': 'make', 'saida': 'compilando...\n'})
    bash = [v[1] for t, v in mandados if t == 'etapa' and v[0] == 'ferramenta' and v[1]['ferramenta'] == 'Bash'][0]
    assert bash['saida'] == 'compilando...\npronto' and bash['id'] == 'b1'
