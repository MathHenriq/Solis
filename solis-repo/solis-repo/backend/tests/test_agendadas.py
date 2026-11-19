"""Tarefas agendadas (docs/PARIDADE.md): um pedido que o Claude faz sozinho num
horário. O relógio, a execução (uma conversa nova + o aviso do Windows), as
rotas da tela e a ferramenta do Claude, que pede cartão."""
import asyncio
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from solis import agendadas, agente, banco, main, roteador

# Sábado, 14/11/2026, 10:00.
AGORA = dt.datetime(2026, 11, 14, 10, 0)


@pytest.mark.parametrize('frequencia, hora, extra, esperado', [
    ('diaria', '08:00', {}, dt.datetime(2026, 11, 15, 8, 0)),           # 8h já passou hoje
    ('diaria', '18:30', {}, dt.datetime(2026, 11, 14, 18, 30)),
    ('dias_uteis', '09:00', {}, dt.datetime(2026, 11, 16, 9, 0)),       # pula sábado e domingo
    ('semanal', '09:00', {'dia_semana': 2}, dt.datetime(2026, 11, 18, 9, 0)),  # quarta
    ('semanal', '11:00', {'dia_semana': 5}, dt.datetime(2026, 11, 14, 11, 0)),  # hoje, mais tarde
    ('semanal', '09:00', {'dia_semana': 5}, dt.datetime(2026, 11, 21, 9, 0)),   # hoje já foi: semana que vem
    ('hora_em_hora', '00:15', {}, dt.datetime(2026, 11, 14, 10, 15)),
    ('hora_em_hora', '00:00', {}, dt.datetime(2026, 11, 14, 11, 0)),
    ('uma_vez', '12:00', {'data': '2026-11-20'}, dt.datetime(2026, 11, 20, 12, 0)),
    ('uma_vez', '12:00', {'data': '2026-11-01'}, None),
])
def test_proxima(frequencia, hora, extra, esperado):
    assert agendadas.proxima(frequencia, hora, AGORA, **extra) == esperado


@pytest.mark.parametrize('args', [
    ('mensal', '08:00'), ('diaria', '25:00'), ('diaria', 'oito'), ('semanal', '08:00'),
    ('semanal', '08:00', 7), ('uma_vez', '08:00', None, None), ('uma_vez', '08:00', None, '20/11'),
])
def test_validar_recusa(args):
    with pytest.raises(agendadas.AgendaInvalida):
        agendadas.validar(*args)


def test_descrever():
    d = lambda **k: agendadas.descrever({'dia_semana': None, 'data': None, **k})  # noqa: E731
    assert d(frequencia='diaria', hora='08:00') == 'Todo dia às 8:00'
    assert d(frequencia='dias_uteis', hora='18:30') == 'Dias úteis às 18:30'
    assert d(frequencia='semanal', hora='09:30', dia_semana=0) == 'Toda segunda às 9:30'
    assert d(frequencia='semanal', hora='10:00', dia_semana=6) == 'Todo domingo às 10:00'
    assert d(frequencia='hora_em_hora', hora='00:05') == 'De hora em hora, aos 05 minutos'
    assert d(frequencia='uma_vez', hora='00:30', data='2026-12-03') == 'Uma vez, 03/12 às 00:30'


def _criar(frequencia='diaria', hora='08:00', proxima='2026-11-14T08:00', **k):
    return banco.criar_agendada(k.get('nome', 'Resumo'), 'Resuma as notícias', frequencia, hora,
                                k.get('dia_semana'), k.get('data'), proxima)


def test_vencidas_e_avancar():
    a = _criar()                                            # venceu há 2 h: roda
    velha = _criar(proxima='2026-11-13T08:00')              # venceu há 26 h: pula
    _criar(proxima='2026-11-14T12:00')                      # ainda não
    desligada = _criar()
    banco.marcar_agendada(desligada['id'], desligada['proxima'], False)
    assert [x['id'] for x in agendadas.vencidas(AGORA)] == [a['id']]
    assert banco.agendada(velha['id'])['proxima'] == '2026-11-15T08:00'
    agendadas.avancar(a, AGORA)
    assert banco.agendada(a['id'])['proxima'] == '2026-11-15T08:00' and banco.agendada(a['id'])['ativa']
    # A de uma vez desliga depois de rodar.
    uma = _criar('uma_vez', '09:00', '2026-11-14T09:00', data='2026-11-14')
    agendadas.avancar(uma, AGORA)
    assert banco.agendada(uma['id'])['ativa'] is False and banco.agendada(uma['id'])['proxima'] is None


def test_rotas():
    cli = TestClient(main.app)
    r = cli.post('/agendadas', json={'nome': ' Notícias ', 'pedido': 'Resuma as notícias', 'frequencia': 'semanal',
                                     'hora': '09:30', 'dia_semana': 0})
    a = r.json()
    assert a['nome'] == 'Notícias' and a['descricao'] == 'Toda segunda às 9:30' and a['ativa']
    assert dt.datetime.fromisoformat(a['proxima']).weekday() == 0
    assert cli.get('/agendadas').json()['agendadas'][0]['id'] == a['id']
    # Inválida e data passada: 400, com o motivo.
    r = cli.post('/agendadas', json={'nome': 'x', 'pedido': 'y', 'frequencia': 'semanal', 'hora': '09:30'})
    assert r.status_code == 400 and r.json()['motivo'] == 'dia da semana'
    r = cli.post('/agendadas', json={'nome': 'x', 'pedido': 'y', 'frequencia': 'uma_vez', 'hora': '09:30',
                                     'data': '2020-01-01'})
    assert r.status_code == 400 and 'passou' in r.json()['motivo']
    assert cli.post('/agendadas', json={'nome': ' ', 'pedido': 'y', 'frequencia': 'diaria',
                                        'hora': '09:30'}).status_code == 400
    # Editar: desligar, mudar a hora.
    r = cli.put(f'/agendadas/{a["id"]}', json={'nome': 'Notícias', 'pedido': 'Resuma', 'frequencia': 'diaria',
                                               'hora': '07:00', 'ativa': False})
    assert r.json()['descricao'] == 'Todo dia às 7:00' and r.json()['ativa'] is False
    assert cli.put('/agendadas/999', json={'nome': 'a', 'pedido': 'b', 'frequencia': 'diaria',
                                           'hora': '07:00'}).status_code == 404
    assert cli.delete(f'/agendadas/{a["id"]}').json() == {'ok': True}
    assert cli.delete(f'/agendadas/{a["id"]}').status_code == 404
    assert cli.get('/agendadas').json() == {'agendadas': []}


@pytest.fixture
def capturado(monkeypatch):
    recebido = {}

    async def responder(ordem, modelo, conversa, historico, memorias, trechos, resumo, mensagem, *_, **__):
        recebido.update(ordem=ordem, mensagem=mensagem)

        async def fluxo():
            yield 'Hoje: três notícias.\n\nA primeira...'
        return fluxo(), 'claude'
    monkeypatch.setattr(roteador, 'responder', responder)
    monkeypatch.setattr(roteador, '_ordem', lambda: ['local', 'claude'])

    async def nada(*_, **__):
        return None
    monkeypatch.setattr(main, '_depois', nada)
    return recebido


def test_rodar_abre_conversa_manda_pro_claude_e_avisa(capturado, sem_aviso_de_verdade, monkeypatch):
    from solis import cerebros
    monkeypatch.setattr(cerebros, 'disponivel', lambda nome: True)
    a = _criar(nome='Notícias da manhã')
    conversa = main._conversa_da_agendada(a)
    asyncio.run(main._executar_agendada(a, conversa))
    assert banco.titulo(conversa) == 'Notícias da manhã'
    # Vai pro Claude, com a nota de que ninguém está olhando; guardado fica só o pedido.
    assert capturado['ordem'][0] == 'claude' and 'Notícias da manhã' in capturado['mensagem']
    assert 'não está olhando' in capturado['mensagem']
    msgs = banco.mensagens(conversa)
    assert [m['papel'] for m in msgs] == ['pessoa', 'solis'] and msgs[0]['texto'] == 'Resuma as notícias'
    depois = banco.agendada(a['id'])
    assert depois['ultima_conversa'] == conversa and depois['ultima']
    assert depois['proxima'] == a['proxima']  # rodar não mexe na próxima vez (quem mexe é o relógio)
    aviso = sem_aviso_de_verdade[-1]
    assert aviso['titulo'] == 'Tarefa agendada: Notícias da manhã'
    assert aviso['texto'] == 'Hoje: três notícias. A primeira...'


def test_rota_rodar_agora(monkeypatch):
    rodadas = []

    async def executar(a, conversa):
        rodadas.append((a['id'], conversa))
    monkeypatch.setattr(main, '_executar_agendada', executar)
    a = _criar()
    r = TestClient(main.app).post(f'/agendadas/{a["id"]}/rodar')
    assert banco.titulo(r.json()['conversa']) == 'Resumo'
    assert TestClient(main.app).post('/agendadas/999/rodar').status_code == 404


def test_relogio_roda_a_vencida_uma_vez(monkeypatch):
    rodadas = []

    async def executar(a, conversa):
        rodadas.append(a['id'])
    monkeypatch.setattr(main, '_executar_agendada', executar)
    agora = dt.datetime.now().replace(second=0, microsecond=0)
    a = _criar(hora=agora.strftime('%H:%M'), proxima=(agora - dt.timedelta(minutes=1)).isoformat(timespec='minutes'))

    async def duas_voltas():
        voltas = 0

        async def dormir(_):
            nonlocal voltas
            voltas += 1
            if voltas == 2:
                raise asyncio.CancelledError
            await asyncio.sleep(0)
        with monkeypatch.context() as m:
            m.setattr(main.asyncio, 'sleep', dormir)
            with pytest.raises(asyncio.CancelledError):
                await main._vigiar_agendadas()
    asyncio.run(duas_voltas())
    assert rodadas == [a['id']]
    assert dt.datetime.fromisoformat(banco.agendada(a['id'])['proxima']) > dt.datetime.now()


def _ferramenta(monkeypatch, nome):
    import claude_agent_sdk
    monkeypatch.setattr(claude_agent_sdk, 'create_sdk_mcp_server', lambda name, tools: tools)
    return next(t for t in agente._ferramentas_solis() if t.name == nome)


def test_ferramenta_agendar(monkeypatch):
    pytest.importorskip('claude_agent_sdk')
    f = _ferramenta(monkeypatch, 'agendar_tarefa')
    r = asyncio.run(f.handler({'nome': 'Resumo', 'pedido': 'Resuma', 'frequencia': 'dias_uteis', 'hora': '08:00'}))
    assert 'Agendada: Resumo, dias úteis às 8:00' in r['content'][0]['text']
    assert banco.agendadas()[0]['frequencia'] == 'dias_uteis'
    r = asyncio.run(f.handler({'nome': 'x', 'pedido': 'y', 'frequencia': 'semanal', 'hora': '08:00'}))
    assert 'Não deu' in r['content'][0]['text'] and len(banco.agendadas()) == 1


def test_agendar_pede_cartao():
    pytest.importorskip('claude_agent_sdk')
    from claude_agent_sdk.types import PermissionResultDeny
    mandados = []

    def por(tipo, valor=None):
        mandados.append((tipo, valor))
        if tipo == 'etapa' and valor[0] == 'aprovacao':
            asyncio.get_running_loop().call_soon(agente.responder_aprovacao, valor[1]['id'], False)
    entrada = {'nome': 'Notícias', 'pedido': 'Resuma as notícias', 'frequencia': 'diaria', 'hora': '08:00'}
    r = asyncio.run(agente._decidir('mcp__solis__agendar_tarefa', entrada, por))
    assert isinstance(r, PermissionResultDeny)
    cartao = mandados[0][1][1]
    assert cartao['resumo'] == 'Agendar "Notícias": Todo dia às 8:00'
    assert cartao['alvo'] == '"Notícias" · Todo dia às 8:00' and cartao['entrada'] == 'Resuma as notícias'
    # E as outras do Solis continuam livres, sem cartão (agendar não está em allowed_tools).
    assert 'mcp__solis__agendar_tarefa' not in agente.SOLIS_LIVRES
    assert asyncio.run(agente._decidir('mcp__solis__ver_tarefas', {}, por)).behavior == 'allow'


def test_sem_o_claude_a_agendada_segue_nos_outros(capturado, monkeypatch):
    """A cota do Claude acabou: a tarefa agendada não pode falhar (as funções são do Solis)."""
    from solis import cerebros
    monkeypatch.setattr(roteador, '_ordem', lambda: ['claude', 'groq', 'local'])
    monkeypatch.setattr(cerebros, 'disponivel', lambda nome: nome != 'claude')
    a = _criar(nome='Notícias da manhã')
    asyncio.run(main._executar_agendada(a, main._conversa_da_agendada(a)))
    assert capturado['ordem'] == ['groq', 'local']


def test_com_o_claude_ele_vem_primeiro_e_os_outros_de_reserva(capturado, monkeypatch):
    from solis import cerebros
    monkeypatch.setattr(roteador, '_ordem', lambda: ['groq', 'claude', 'local'])
    monkeypatch.setattr(cerebros, 'disponivel', lambda nome: True)
    a = _criar(nome='Resumo')
    asyncio.run(main._executar_agendada(a, main._conversa_da_agendada(a)))
    assert capturado['ordem'] == ['claude', 'groq', 'local']
