"""Tarefas: criadas pela tela ou tiradas da conversa, com o prazo em data, e as
abertas indo no pedido ao modelo — a privada nunca pra nuvem."""
import asyncio
import datetime as dt

from fastapi.testclient import TestClient

from solis import banco, cofre, main, memoria, ollama, roteador

AGORA = dt.datetime(2026, 11, 9, 10, 30)  # segunda-feira


def extrator(monkeypatch, resposta, pedidos=None):
    async def falso(modelo, instrucao, texto, esquema, *_):
        if pedidos is not None:
            pedidos.append({'instrucao': instrucao, 'texto': texto, 'esquema': esquema})
        return resposta
    monkeypatch.setattr(ollama, 'responder_json', falso)


def aprender(mensagem, **kw):
    conversa = banco.nova_conversa()
    criadas = []
    memorias = asyncio.run(memoria.aprender('qwen3:8b', conversa, mensagem, [], tarefas=criadas, agora=AGORA, **kw))
    return memorias, criadas, conversa


# --- tirar da conversa ----------------------------------------------------------

def test_tarefa_da_conversa_com_prazo_e_calendario_no_pedido(monkeypatch):
    pedidos = []
    extrator(monkeypatch, {'memorias': [], 'tarefas': [
        {'texto': 'Entregar o relatório da Syngenta', 'prazo': '2026-11-13', 'hora': '14:00'},
    ]}, pedidos)
    _, criadas, conversa = aprender('tenho que entregar o relatório da Syngenta sexta às 14h')
    assert criadas == [{'texto': 'Entregar o relatório da Syngenta', 'prazo': '2026-11-13', 'hora': '14:00'}]
    [t] = banco.tarefas()
    assert (t['texto'], t['prazo'], t['hora'], t['conversa'], t['feita']) == (
        'Entregar o relatório da Syngenta', '2026-11-13', '14:00', conversa, None)
    # O modelo recebe o calendário: copia a data em vez de fazer conta.
    assert 'sexta-feira 13/11 = 2026-11-13' in pedidos[0]['texto']
    assert 'Agora: segunda-feira, 09/11/2026, 10:30.' in pedidos[0]['texto']
    assert 'tarefas' in pedidos[0]['esquema']['properties']


def test_memoria_que_repete_a_tarefa_sai(monkeypatch):
    extrator(monkeypatch, {
        'memorias': [
            {'texto': 'Renovar CNH no fim do mês', 'tema': 'Pessoal', 'privada': False, 'substitui': 0},
            {'texto': 'Trabalha na Syngenta', 'tema': 'Trabalho', 'privada': False, 'substitui': 0},
        ],
        'tarefas': [{'texto': 'Renovar a CNH', 'prazo': '2026-11-30', 'hora': ''}],
    })
    memorias, criadas, _ = aprender('fim do mês tenho que renovar a CNH; trabalho na Syngenta')
    assert memorias == ['Trabalha na Syngenta']
    assert criadas == [{'texto': 'Renovar a CNH', 'prazo': '2026-11-30', 'hora': None}]


def test_prazo_copiado_do_agora_e_prazo_invalido_viram_sem_prazo(monkeypatch):
    extrator(monkeypatch, {'memorias': [], 'tarefas': [
        {'texto': 'Comprar ração do cachorro', 'prazo': '2026-11-09', 'hora': '10:30'},
        {'texto': 'Ligar pro banco', 'prazo': 'sexta', 'hora': '25:00'},
        {'texto': 'Mandar o email', 'prazo': '2026-11-09', 'hora': '20:00'},
        {'texto': '  ', 'prazo': '', 'hora': ''},
    ]})
    _, criadas, _ = aprender('anota aí: comprar ração, ligar pro banco, e hoje à noite mandar o email')
    assert [(t['texto'], t['prazo'], t['hora']) for t in criadas] == [
        ('Comprar ração do cachorro', None, None),
        ('Ligar pro banco', None, None),
        ('Mandar o email', '2026-11-09', '20:00'),
    ]


def test_mensagem_privada_faz_tarefa_privada_selada(monkeypatch, tmp_path):
    extrator(monkeypatch, {'memorias': [], 'tarefas': [{'texto': 'Marcar exame de sangue', 'prazo': '', 'hora': ''}]})
    aprender('isso é privado: preciso marcar o exame de sangue')
    bruto = banco._con().execute('SELECT texto, privada FROM tarefas').fetchone()
    assert bruto['privada'] == 1
    if cofre.DISPONIVEL:
        assert cofre.selado(bruto['texto'])
    assert banco.tarefas()[0]['texto'] == 'Marcar exame de sangue'


def test_conversa_importada_nao_vira_tarefa(monkeypatch):
    pedidos = []
    extrator(monkeypatch, {'memorias': [], 'tarefas': [{'texto': 'Pagar a luz', 'prazo': '', 'hora': ''}]}, pedidos)
    aprender('tenho que pagar a luz', antiga='ChatGPT, 14/03/2023')
    assert banco.tarefas() == []
    assert 'tarefas' not in pedidos[0]['esquema']['properties']
    assert 'Calendário' not in pedidos[0]['texto']


def test_modelo_fora_nao_cria_nada_e_nao_quebra():
    # conftest: o Ollama está fora
    memorias, criadas, _ = aprender('tenho que pagar a luz')
    assert (memorias, criadas, banco.tarefas()) == ([], [], [])


# --- pela tela ------------------------------------------------------------------

def test_criar_marcar_mudar_e_apagar_pela_tela():
    c = TestClient(main.app)
    t = c.post('/tarefas', json={'texto': '  Pagar a conta de luz ', 'prazo': '2026-11-15'}).json()['tarefa']
    assert (t['texto'], t['prazo'], t['hora'], t['feita']) == ('Pagar a conta de luz', '2026-11-15', None, None)

    t = c.patch(f'/tarefas/{t["id"]}', json={'hora': '09:00'}).json()['tarefa']
    assert (t['prazo'], t['hora']) == ('2026-11-15', '09:00')
    t = c.patch(f'/tarefas/{t["id"]}', json={'feita': True}).json()['tarefa']
    assert t['feita'] is not None
    # Feita hoje continua na lista (riscada na tela).
    assert [x['id'] for x in c.get('/tarefas').json()['tarefas']] == [t['id']]
    t = c.patch(f'/tarefas/{t["id"]}', json={'feita': False, 'texto': 'Pagar a luz'}).json()['tarefa']
    assert (t['feita'], t['texto']) == (None, 'Pagar a luz')
    # Tirar o prazo leva a hora junto.
    t = c.patch(f'/tarefas/{t["id"]}', json={'prazo': ''}).json()['tarefa']
    assert (t['prazo'], t['hora']) == (None, None)

    assert c.delete(f'/tarefas/{t["id"]}').json() == {'ok': True}
    assert c.get('/tarefas').json()['tarefas'] == []
    assert c.delete(f'/tarefas/{t["id"]}').status_code == 404
    assert c.patch(f'/tarefas/{t["id"]}', json={'feita': True}).status_code == 404


def test_recusa_vazio_e_data_fora_do_formato():
    c = TestClient(main.app)
    assert c.post('/tarefas', json={'texto': ' '}).json() == {'erro': 'texto_vazio'}
    assert c.post('/tarefas', json={'texto': 'x', 'prazo': '15/11'}).json() == {'erro': 'prazo_invalido'}
    assert c.post('/tarefas', json={'texto': 'x', 'prazo': '2026-11-15', 'hora': '9h'}).json() == {'erro': 'hora_invalida'}
    id_ = c.post('/tarefas', json={'texto': 'x'}).json()['tarefa']['id']
    assert c.patch(f'/tarefas/{id_}', json={'texto': ''}).status_code == 400


def test_feita_antes_de_hoje_sai_da_lista_e_ordem_por_prazo():
    c = TestClient(main.app)
    ids = {}
    for texto, prazo, hora in [('sem prazo', None, None), ('sexta', '2026-11-13', None),
                               ('segunda 9h', '2026-11-09', '09:00'), ('segunda', '2026-11-09', None)]:
        ids[texto] = banco.adicionar_tarefa(texto, prazo, hora)
    velha = banco.adicionar_tarefa('feita ontem')
    banco._con().execute("UPDATE tarefas SET feita = '2020-01-01T00:00:00+00:00' WHERE id = ?", (velha,))
    banco._con().commit()
    assert [t['texto'] for t in c.get('/tarefas').json()['tarefas']] == ['segunda 9h', 'segunda', 'sexta', 'sem prazo']


def test_origem_e_o_titulo_da_conversa():
    conversa = banco.nova_conversa(titulo='Plano da semana')
    banco.adicionar_tarefa('Revisar o TCC', conversa=conversa)
    assert TestClient(main.app).get('/tarefas').json()['tarefas'][0]['origem'] == 'Plano da semana'


# --- no pedido ao modelo ----------------------------------------------------------

def test_tarefas_abertas_vao_no_pedido_e_a_privada_nao_vai_pra_nuvem():
    banco.adicionar_tarefa('Entregar o relatório', '2026-11-13', '14:00')
    banco.adicionar_tarefa('Comprar ração')
    banco.adicionar_tarefa('Marcar exame de sangue', '2026-11-10', privada=True)
    feita = banco.adicionar_tarefa('Já feita')
    banco.mudar_tarefa(feita, feita=True)

    trechos = main._tarefas_no_pedido()
    local = ollama.contexto([], trechos)
    assert '- [terça-feira 10/11] Marcar exame de sangue' in local
    assert '- [sexta-feira 13/11 às 14:00] Entregar o relatório' in local
    assert '- [sem prazo] Comprar ração' in local
    assert 'Já feita' not in local
    # Tarefa não aparece como "trecho de conversa antiga".
    assert 'conversas antigas' not in local

    nuvem = roteador.prompt_nuvem([], [t for t in trechos if not t['privada']], None, [], 'o que tenho pra fazer?')
    assert 'Entregar o relatório' in nuvem and 'exame' not in nuvem


def test_migracao_11_num_banco_antigo(tmp_path):
    caminho = tmp_path / 'velho.db'
    banco.usar(caminho)
    banco._con().execute('DROP TABLE tarefas')
    banco._con().execute('DROP TABLE compromissos')
    banco._con().execute('DROP TABLE avisos')
    banco._con().execute('DROP TABLE acoes')
    banco._con().execute('DROP TABLE sessoes_claude')
    banco._con().execute('PRAGMA user_version = 10')
    banco._con().commit()
    banco.usar(caminho)
    assert banco._con().execute('PRAGMA user_version').fetchone()[0] == len(banco.MIGRACOES)
    assert banco.tarefas() == []


# --- as contas que o modelo erra -----------------------------------------------------

def test_corrige_dia_da_semana_e_daqui_a_n():
    c = memoria.corrigir_data
    assert c('quinta às 15h tenho consulta', '2026-11-11', AGORA) == '2026-11-12'
    assert c('prova na quinta que vem', '2026-11-19', AGORA) == '2026-11-19'  # já é quinta
    assert c('reunião daqui a duas semanas', '2026-12-01', AGORA) == '2026-11-23'
    assert c('em 3 dias entregar', None, AGORA) == '2026-11-12'
    assert c('quinta e sexta', '2026-11-11', AGORA) == '2026-11-11'  # duas: não mexe
    assert c('comprar ração', None, AGORA) is None


def test_saude_e_dinheiro_sao_privadas_mesmo_sem_o_modelo_dizer(monkeypatch):
    extrator(monkeypatch, {'memorias': [], 'tarefas': [
        {'texto': 'Pagar a fatura do cartão de crédito', 'prazo': '2026-11-20', 'hora': ''},
        {'texto': 'Comprar ração', 'prazo': '', 'hora': ''},
    ]})
    conversa = banco.nova_conversa()
    mensagem = banco.adicionar(conversa, 'pessoa', 'pagar a fatura dia 20 e comprar ração')
    asyncio.run(memoria.aprender('qwen3:8b', conversa, 'pagar a fatura dia 20 e comprar ração', [], mensagem, agora=AGORA))
    assert {t['texto']: t['privada'] for t in banco.tarefas()} == {
        'Pagar a fatura do cartão de crédito': True, 'Comprar ração': False}
    # A mensagem que deu tarefa privada sai da nuvem, como a de memória privada.
    assert banco._con().execute('SELECT privada FROM mensagens WHERE id = ?', (mensagem,)).fetchone()[0] == 1


def test_uma_tarefa_so_tem_a_data_corrigida(monkeypatch):
    extrator(monkeypatch, {'memorias': [], 'tarefas': [
        {'texto': 'Consulta com o psiquiatra', 'prazo': '2026-11-11', 'hora': '15:00'},
    ]})
    _, criadas, _ = aprender('quinta às 15h tenho consulta com o psiquiatra')
    assert criadas[0]['prazo'] == '2026-11-12'
