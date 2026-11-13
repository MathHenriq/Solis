"""Voltar atrás e o terminal ao vivo (docs/PARIDADE.md → Trabalhar num projeto):
os pontos de volta de cada fala, a rota que volta os arquivos pelo CLI, e a
saída do comando lida enquanto ele roda."""
import asyncio

import pytest
from fastapi.testclient import TestClient

pytest.importorskip('claude_agent_sdk')

import claude_agent_sdk  # noqa: E402
from claude_agent_sdk import (  # noqa: E402
    AssistantMessage, ResultMessage, StreamEvent, SystemMessage, TaskStartedMessage, ToolResultBlock, ToolUseBlock,
    UserMessage,
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
    """Um CLI falso: cada query() solta o roteiro da vez em receive_messages();
    `depois` é o que o CLI manda sozinho, sem query (o aviso de um comando em
    segundo plano que acabou). Item chamável no roteiro: espera ele."""
    roteiros: list = []
    depois: list = []
    opcoes = None
    instancias: list = []

    def __init__(self, options):
        SessaoFalsa.opcoes = options
        SessaoFalsa.instancias.append(self)
        self.fila: asyncio.Queue | None = None
        self.queries: list[str] = []
        self.paradas: list[str] = []
        self.modelos: list = []

    async def __aenter__(self):
        self.fila = asyncio.Queue()
        return self

    async def __aexit__(self, *a):
        return False

    async def _soltar(self, roteiro):
        for m in roteiro:
            if callable(m):
                await m()
            else:
                await self.fila.put(m)

    async def query(self, prompt):
        self.queries.append(prompt)
        roteiro = SessaoFalsa.roteiros.pop(0)
        asyncio.ensure_future(self._soltar(roteiro))
        if len(self.queries) == 1 and SessaoFalsa.depois:
            asyncio.ensure_future(self._soltar(SessaoFalsa.depois))

    async def receive_messages(self):
        while True:
            yield await self.fila.get()

    async def stop_task(self, tarefa):
        self.paradas.append(tarefa)

    async def set_model(self, modelo):
        self.modelos.append(modelo)

    async def set_permission_mode(self, modo):
        pass


def _fim(sessao='S1'):
    return ResultMessage(subtype='success', duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                         session_id=sessao, total_cost_usd=0.0)


def _texto(t):
    return StreamEvent(uuid='x', session_id='S1', parent_tool_use_id=None,
                       event={'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': t}})


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

    SessaoFalsa.depois = []
    SessaoFalsa.roteiros = [[
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
        _fim(),
    ]]
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


# — segundo plano: a sessão que fica aberta ———————————————————————————————————————
def _bg_turno():
    return [
        SystemMessage(subtype='init', data={'session_id': 'S1'}),
        UserMessage(content='sobe o servidor', uuid='U-1'),
        AssistantMessage(content=[ToolUseBlock(id='bg1', name='Bash',
                                               input={'command': 'npm run dev', 'run_in_background': True})], model='m'),
        SystemMessage(subtype='task_started', data={'task_id': 'T1', 'tool_use_id': 'bg1', 'task_type': 'local_bash',
                                                    'is_backgrounded': True, 'description': 'servidor'}),
        SystemMessage(subtype='background_tasks_changed', data={'tasks': [{'task_id': 'T1'}]}),
        UserMessage(content=[ToolResultBlock(tool_use_id='bg1', content='Command running in background', is_error=False)]),
        _texto('subiu'),
        _fim(),
    ]


def _rodar_claude(c, prompt, retomar=None):
    async def rodar():
        partes = []
        async for p in agente.claude('sis', prompt, retomar=retomar, conversa=c):
            partes.append(p)
        return ''.join(partes)
    return asyncio.run(rodar())


@pytest.fixture
def cli_falso(monkeypatch, tmp_path):
    monkeypatch.setattr(agente.tempfile, 'gettempdir', lambda: str(tmp_path))
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: tmp_path)
    monkeypatch.setattr(agente, '_ferramentas_solis', lambda: None)
    monkeypatch.setattr(agente, 'OCIOSA_S', 0.3)
    monkeypatch.setattr(claude_agent_sdk, 'ClaudeSDKClient', SessaoFalsa)
    SessaoFalsa.instancias = []
    tarefas = tmp_path / 'claude' / 'x' / 'S1' / 'tasks'
    tarefas.mkdir(parents=True)
    (tarefas / 'T1.output').write_bytes(b'ouvindo na 5173\n')
    yield
    for v in list(agente._vivas.values()):
        v.fechar_ja = True
    agente._vivas.clear()


def _esperar(condicao, limite=5.0):
    import time
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.05)
    return False


def test_comando_em_segundo_plano_segura_a_sessao_e_o_claude_conta_quando_acaba(cli_falso):
    c, _ = _conversa_com_falas(1)
    solta = {'agora': False}

    async def esperar_soltar():
        while not solta['agora']:
            await asyncio.sleep(0.05)

    SessaoFalsa.roteiros = [_bg_turno()]
    SessaoFalsa.depois = [
        esperar_soltar,
        SystemMessage(subtype='task_notification', data={'task_id': 'T1', 'status': 'completed'}),
        SystemMessage(subtype='background_tasks_changed', data={'tasks': []}),
        SystemMessage(subtype='init', data={'session_id': 'S1'}),
        _texto('O servidor parou: saiu com código 0.'),
        _fim(),
    ]
    assert _rodar_claude(c, 'sobe o servidor') == 'subiu'
    # A resposta acabou, o comando não: a sessão segue aberta, com ele.
    assert _esperar(lambda: c in agente._vivas)
    f = agente.fundo(c)
    assert [(x['id'], x['comando'], x['saida']) for x in f['comandos']] == [('T1', 'npm run dev', 'ouvindo na 5173\n')]
    assert f['resposta'] is None
    # O comando acaba: o Claude responde sozinho, a resposta vai pro banco, e
    # a sessão fecha.
    solta['agora'] = True
    assert _esperar(lambda: c not in agente._vivas)
    ultima = banco.mensagens(c)[-1]
    assert ultima['papel'] == 'solis' and ultima['texto'] == 'O servidor parou: saiu com código 0.'
    assert [e['etapa'] for e in ultima['etapas']][:2] == ['sozinha', 'cerebro']


def test_mensagem_nova_vai_pra_sessao_aberta_e_o_comando_para(cli_falso):
    c, _ = _conversa_com_falas(1)
    SessaoFalsa.roteiros = [_bg_turno(), [SystemMessage(subtype='init', data={'session_id': 'S1'}), _texto('sigo'), _fim()]]
    SessaoFalsa.depois = []
    _rodar_claude(c, 'sobe o servidor')
    assert _esperar(lambda: c in agente._vivas)
    # Retomando a mesma sessão: vai pro mesmo CLI, sem abrir outro.
    assert _rodar_claude(c, 'e agora?', retomar='S1') == 'sigo'
    assert len(SessaoFalsa.instancias) == 1 and SessaoFalsa.instancias[0].queries == ['sobe o servidor', 'e agora?']
    r = TestClient(main.app).post(f'/conversas/{c}/fundo/T1/parar')
    assert r.status_code == 200 and SessaoFalsa.instancias[0].paradas == ['T1']
    assert TestClient(main.app).post(f'/conversas/{c}/fundo/T9/parar').status_code == 404


def test_outra_sessao_fecha_a_aberta_parando_os_comandos(cli_falso):
    c, _ = _conversa_com_falas(1)
    SessaoFalsa.roteiros = [_bg_turno(), [SystemMessage(subtype='init', data={'session_id': 'S2'}), _texto('nova'), _fim('S2')]]
    SessaoFalsa.depois = []
    _rodar_claude(c, 'sobe o servidor')
    assert _esperar(lambda: c in agente._vivas)
    velha = SessaoFalsa.instancias[0]
    # Sem retomar (a conversa voltou atrás): outra sessão, e a aberta para o comando.
    assert _rodar_claude(c, 'de novo') == 'nova'
    assert _esperar(lambda: velha.paradas == ['T1']) and len(SessaoFalsa.instancias) == 2
    assert _esperar(lambda: c not in agente._vivas)


def test_rota_do_fundo_sem_nada(cli_falso):
    c, _ = _conversa_com_falas(1)
    assert TestClient(main.app).get(f'/conversas/{c}/fundo').json() == {'comandos': [], 'resposta': None, 'aprovacoes': []}


def test_ler_a_saida_do_proprio_comando_e_livre(monkeypatch, tmp_path):
    monkeypatch.setattr(agente.tempfile, 'gettempdir', lambda: str(tmp_path))
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: tmp_path / 'trabalho')
    saida = tmp_path / 'claude' / 'abc' / 'sessao' / 'tasks' / 'b1.output'
    assert agente._dentro(str(saida))
    # O resto do temporário continua pedindo.
    assert not agente._dentro(str(tmp_path / 'claude' / 'abc' / 'segredo.txt'))
    assert not agente._dentro(str(tmp_path / 'outro' / 'x' / 's' / 'tasks' / 'b1.output'))


# — ajudantes (subagentes) ————————————————————————————————————————————————————————
def test_ajudante_aparece_com_o_que_faz_e_pede_aprovacao_pelo_fundo(cli_falso):
    c, _ = _conversa_com_falas(1)
    solta = {'agora': False}

    async def esperar_soltar():
        while not solta['agora']:
            await asyncio.sleep(0.05)

    SessaoFalsa.roteiros = [[
        SystemMessage(subtype='init', data={'session_id': 'S1'}),
        AssistantMessage(content=[ToolUseBlock(id='ag1', name='Agent',
                                               input={'description': 'ler o LEIAME', 'prompt': 'leia'})], model='m'),
        SystemMessage(subtype='task_started', data={'task_id': 'A1', 'tool_use_id': 'ag1', 'task_type': 'local_agent',
                                                    'is_backgrounded': True, 'description': 'ler o LEIAME'}),
        SystemMessage(subtype='background_tasks_changed', data={'tasks': [{'task_id': 'A1'}]}),
        UserMessage(content=[ToolResultBlock(tool_use_id='ag1', content='async_launched', is_error=False)]),
        _texto('pedi a um ajudante'),
        _fim(),
    ]]
    SessaoFalsa.depois = [
        # O ajudante trabalha depois da resposta: as ações dele vêm com o pai.
        AssistantMessage(content=[ToolUseBlock(id='r1', name='Read', input={'file_path': 'LEIAME.md'})], model='m',
                         parent_tool_use_id='ag1'),
        UserMessage(content=[ToolResultBlock(tool_use_id='r1', content='oi', is_error=False)], parent_tool_use_id='ag1'),
        AssistantMessage(content=[ToolUseBlock(id='b2', name='Bash', input={'command': 'sleep 10'})], model='m',
                         parent_tool_use_id='ag1'),
        esperar_soltar,
        SystemMessage(subtype='task_notification', data={'task_id': 'A1', 'status': 'completed'}),
        SystemMessage(subtype='background_tasks_changed', data={'tasks': []}),
        SystemMessage(subtype='init', data={'session_id': 'S1'}),
        _texto('O ajudante leu: oi.'),
        _fim(),
    ]
    assert _rodar_claude(c, 'delega') == 'pedi a um ajudante'
    # Agora: a ação em andamento (o Bash), não a que já acabou.
    assert _esperar(lambda: ((agente.fundo(c)['comandos'] or [{}])[0].get('agora') or {}).get('ferramenta') == 'Bash')
    a = agente.fundo(c)['comandos'][0]
    assert a['tipo'] == 'ajudante' and a['descricao'] == 'ler o LEIAME' and a['comando'] == '' and a['saida'] == ''
    assert a['passos'] == [{'ferramenta': 'Read', 'alvo': 'LEIAME.md', 'ok': True}] and 'usadas' not in a

    # Um pedido de aprovação sem resposta em andamento vai pro /fundo.
    viva = agente._vivas[c]
    decidir = SessaoFalsa.opcoes.can_use_tool
    from claude_agent_sdk.types import ToolPermissionContext
    contexto = ToolPermissionContext(tool_use_id='x', agent_id='A1')
    pedido = asyncio.run_coroutine_threadsafe(decidir('Bash', {'command': 'ls'}, contexto), viva.laco)
    assert _esperar(lambda: agente.fundo(c)['aprovacoes'])
    card = agente.fundo(c)['aprovacoes'][0]
    # O cartão diz que quem pede é o ajudante, com a tarefa dele.
    assert card['etapa'] == 'aprovacao' and card['ferramenta'] == 'Bash' and card['ajudante'] == 'ler o LEIAME'
    agente.responder_aprovacao(card['id'], True)
    assert pedido.result(5).behavior == 'allow'
    assert _esperar(lambda: agente.fundo(c)['aprovacoes'] == [])

    solta['agora'] = True
    assert _esperar(lambda: c not in agente._vivas)
    assert banco.mensagens(c)[-1]['texto'] == 'O ajudante leu: oi.'
