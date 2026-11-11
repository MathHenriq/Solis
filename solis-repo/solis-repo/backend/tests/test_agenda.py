"""Agenda: compromissos criados pela tela ou tirados da conversa — separados das
tarefas —, e os dos próximos dias indo no pedido ao modelo."""
import asyncio
import datetime as dt

from fastapi.testclient import TestClient

from solis import banco, cofre, main, memoria, ollama, roteador

AGORA = dt.datetime(2026, 11, 9, 10, 30)  # segunda-feira


def extrator(monkeypatch, resposta, pedidos=None):
    async def falso(modelo, instrucao, texto, esquema, *_):
        if pedidos is not None:
            pedidos.append({'instrucao': instrucao, 'esquema': esquema})
        return {'memorias': [], 'tarefas': [], 'compromissos': [], **resposta}
    monkeypatch.setattr(ollama, 'responder_json', falso)


def aprender(mensagem, **kw):
    conversa = banco.nova_conversa()
    tarefas, compromissos = [], []
    asyncio.run(memoria.aprender(
        'qwen3:8b', conversa, mensagem, [], tarefas=tarefas, compromissos=compromissos, agora=AGORA, **kw))
    return tarefas, compromissos, conversa


# --- tirar da conversa ----------------------------------------------------------

def test_compromisso_da_conversa_com_duracao_e_lugar(monkeypatch):
    pedidos = []
    extrator(monkeypatch, {'compromissos': [
        {'titulo': 'Reunião de alinhamento', 'dia': '2026-11-10', 'hora': '09:00', 'duracao': 60, 'onde': 'Google Meet'},
    ]}, pedidos)
    _, marcados, conversa = aprender('reunião de alinhamento amanhã às 9h no Google Meet, dura uma hora')
    assert marcados == [{'titulo': 'Reunião de alinhamento', 'dia': '2026-11-10', 'hora': '09:00', 'duracao': 60, 'onde': 'Google Meet'}]
    [c] = banco.compromissos('2026-11-10', '2026-11-10')
    assert (c['titulo'], c['hora'], c['duracao'], c['onde'], c['conversa'], c['privado']) == (
        'Reunião de alinhamento', '09:00', 60, 'Google Meet', conversa, False)
    assert 'compromissos' in pedidos[0]['esquema']['properties']
    assert 'NUNCA em tarefas' in pedidos[0]['instrucao']


def test_cancelado_nao_vira_compromisso(monkeypatch):
    extrator(monkeypatch, {'compromissos': [{'titulo': 'Reunião', 'dia': '2026-11-10', 'hora': '', 'duracao': 0, 'onde': ''}]})
    assert aprender('a reunião de amanhã foi cancelada')[1] == []
    assert banco.compromissos('2026-01-01', '2027-01-01') == []


def test_tarefa_que_repete_o_compromisso_sai(monkeypatch):
    extrator(monkeypatch, {
        'tarefas': [{'texto': 'Reunião com o orientador', 'prazo': '2026-11-23', 'hora': ''}],
        'compromissos': [{'titulo': 'Reunião com o orientador do TCC', 'dia': '2026-11-23', 'hora': '', 'duracao': 0, 'onde': ''}],
    })
    tarefas, marcados, _ = aprender('lembrete: reunião com o orientador do TCC daqui a duas semanas')
    assert tarefas == [] and len(marcados) == 1
    assert banco.tarefas() == []


def test_dia_corrigido_saude_privada_e_duracao_absurda_fora(monkeypatch):
    extrator(monkeypatch, {'compromissos': [
        {'titulo': 'Consulta com o psiquiatra', 'dia': '2026-11-11', 'hora': '15:00', 'duracao': 99999, 'onde': ''},
    ]})
    _, [c], _ = aprender('quinta às 15h tenho consulta com o psiquiatra')
    assert (c['dia'], c['duracao']) == ('2026-11-12', None)
    bruto = banco._con().execute('SELECT titulo, privado FROM compromissos').fetchone()
    assert bruto['privado'] == 1
    if cofre.DISPONIVEL:
        assert cofre.selado(bruto['titulo'])


def test_compromisso_sem_dia_e_ignorado(monkeypatch):
    extrator(monkeypatch, {'compromissos': [{'titulo': 'Aula de inglês', 'dia': '', 'hora': '19:00', 'duracao': 0, 'onde': ''}]})
    assert aprender('tenho aula de inglês às 19h')[1] == []


def test_conversa_importada_nao_vira_compromisso(monkeypatch):
    extrator(monkeypatch, {'compromissos': [{'titulo': 'Reunião', 'dia': '2026-11-10', 'hora': '', 'duracao': 0, 'onde': ''}]})
    aprender('reunião amanhã', antiga='ChatGPT, 14/03/2023')
    assert banco.compromissos('2026-01-01', '2027-01-01') == []


# --- pela tela ------------------------------------------------------------------

def test_criar_listar_mudar_e_apagar_pela_tela():
    c = TestClient(main.app)
    m = c.post('/agenda', json={'titulo': ' Treino ', 'dia': '2026-11-10', 'hora': '19:30', 'duracao': 75, 'onde': 'academia'}).json()['compromisso']
    assert (m['titulo'], m['dia'], m['hora'], m['duracao'], m['onde']) == ('Treino', '2026-11-10', '19:30', 75, 'academia')
    c.post('/agenda', json={'titulo': 'Feriado', 'dia': '2026-11-10'})
    c.post('/agenda', json={'titulo': 'Outro dia', 'dia': '2026-11-11', 'hora': '08:00'})
    # O dia inteiro primeiro, depois pela hora; só o dia pedido.
    assert [x['titulo'] for x in c.get('/agenda', params={'de': '2026-11-10'}).json()['compromissos']] == ['Feriado', 'Treino']
    assert len(c.get('/agenda', params={'de': '2026-11-10', 'ate': '2026-11-11'}).json()['compromissos']) == 3

    m = c.patch(f'/agenda/{m["id"]}', json={'hora': '20:00', 'onde': ''}).json()['compromisso']
    assert (m['hora'], m['onde'], m['duracao']) == ('20:00', None, 75)
    assert c.delete(f'/agenda/{m["id"]}').json() == {'ok': True}
    assert c.delete(f'/agenda/{m["id"]}').status_code == 404
    assert c.patch(f'/agenda/{m["id"]}', json={'hora': '10:00'}).status_code == 404


def test_recusa_o_que_nao_e_compromisso():
    c = TestClient(main.app)
    assert c.post('/agenda', json={'titulo': ' ', 'dia': '2026-11-10'}).json() == {'erro': 'titulo_vazio'}
    assert c.post('/agenda', json={'titulo': 'x', 'dia': '10/11'}).json() == {'erro': 'dia_invalido'}
    assert c.post('/agenda', json={'titulo': 'x', 'dia': '2026-11-10', 'hora': '25:00'}).json() == {'erro': 'hora_invalida'}
    assert c.post('/agenda', json={'titulo': 'x', 'dia': '2026-11-10', 'duracao': -5}).json() == {'erro': 'duracao_invalida'}
    assert c.get('/agenda', params={'de': 'ontem'}).status_code == 400
    id_ = c.post('/agenda', json={'titulo': 'x', 'dia': '2026-11-10'}).json()['compromisso']['id']
    assert c.patch(f'/agenda/{id_}', json={'dia': ''}).json() == {'erro': 'dia_vazio'}


# --- no pedido ao modelo ----------------------------------------------------------

def test_agenda_dos_proximos_dias_vai_no_pedido_e_a_privada_nao_vai_pra_nuvem():
    hoje = dt.date.today()
    dia = lambda n: (hoje + dt.timedelta(days=n)).isoformat()
    banco.adicionar_compromisso('Reunião de alinhamento', dia(1), '09:00', 60, 'Google Meet')
    banco.adicionar_compromisso('Consulta com o psiquiatra', dia(2), '15:00', privado=True)
    banco.adicionar_compromisso('Viagem longe', dia(30))
    banco.adicionar_compromisso('Ontem', dia(-1))

    trechos = main._agenda_no_pedido()
    local = ollama.contexto([], trechos)
    assert 'Reunião de alinhamento (Google Meet)' in local and 'psiquiatra' in local
    assert 'Viagem longe' not in local and 'Ontem' not in local
    assert 'conversas antigas' not in local
    nuvem = roteador.prompt_nuvem([], [t for t in trechos if not t['privada']], None, [], 'o que tenho amanhã?')
    assert 'alinhamento' in nuvem and 'psiquiatra' not in nuvem


def test_migracao_12_num_banco_antigo(tmp_path):
    caminho = tmp_path / 'velho.db'
    banco.usar(caminho)
    banco._con().execute('DROP TABLE compromissos')
    banco._con().execute('DROP TABLE avisos')
    banco._con().execute('DROP TABLE acoes')
    banco._con().execute('DROP TABLE sessoes_claude')
    banco._con().execute('PRAGMA user_version = 11')
    banco._con().commit()
    banco.usar(caminho)
    assert banco._con().execute('PRAGMA user_version').fetchone()[0] == len(banco.MIGRACOES)
    assert banco.compromissos('2000-01-01', '2100-01-01') == []
