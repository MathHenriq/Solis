"""Juntar o PC e o servidor (juntar.py, 26/11/2026): dois bancos de verdade, um
de cada lado. O que viaja, o que não viaja (o privado), e rodar de novo não
duplica nada."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from solis import banco, juntar, main


@pytest.fixture
def lados(tmp_path):
    """`pc` e `servidor`: cada um põe o seu banco pra valer (banco.usar)."""
    caminhos = {'pc': tmp_path / 'pc.db', 'servidor': tmp_path / 'servidor.db'}

    def em(lado):
        banco.usar(caminhos[lado])
    em('servidor')
    em('pc')
    return em


def _pc_com_de_tudo():
    cv = banco.nova_conversa()
    banco.adicionar(cv, 'pessoa', 'Quanto é 2 + 2?')
    banco.adicionar(cv, 'solis', 'Dá 4.', cerebro='groq')
    banco.guardar_titulo(cv, 'Conta de cabeça')
    # Uma conversa com um pedaço privado: o resto viaja; o título fica selado aqui.
    mista = banco.nova_conversa()
    banco.adicionar(mista, 'pessoa', 'Bom dia, Solis.')
    banco.adicionar(mista, 'pessoa', 'isso é privado: minha senha é 1234', privada=True)
    so_privada = banco.nova_conversa()
    banco.adicionar(so_privada, 'pessoa', 'segredo de família', privada=True)
    velha = banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, cv)
    banco.adicionar_memoria('Tem asma.', 'Saúde', False, None, privada=True)
    banco.adicionar_tarefa('Comprar pão', '2026-11-27', None, cv)
    banco.adicionar_tarefa('Consulta no psiquiatra', '2026-11-28', '10:00', None, privada=True)
    banco.adicionar_compromisso('Reunião do projeto', '2026-11-27', '14:00', 60, 'Sala 3', None)
    banco.adicionar_compromisso('Exame', '2026-11-29', '08:00', 30, None, None, privado=True)
    return cv, velha


def test_o_que_viaja_e_o_que_fica(lados):
    _pc_com_de_tudo()
    pacote = juntar.exportar()
    lados('servidor')
    assert juntar.importar(pacote) == {'conversas': 2, 'mensagens': 3, 'memorias': 1, 'tarefas': 1,
                                       'compromissos': 1, 'feitas': 0}
    conta, mista = sorted(banco.conversas(), key=lambda c: c['id'])
    assert banco.titulo(conta['id']) == 'Conta de cabeça'
    assert [m['texto'] for m in banco.mensagens(conta['id'])] == ['Quanto é 2 + 2?', 'Dá 4.']
    assert [m['texto'] for m in banco.mensagens(mista['id'])] == ['Bom dia, Solis.']
    assert [m['texto'] for m in banco.memorias()] == ['Trabalha na Syngenta.']
    assert [t['texto'] for t in banco.tarefas_abertas(10)] == ['Comprar pão']
    assert [a['titulo'] for a in banco.compromissos('2026-11-01', '2026-12-31')] == ['Reunião do projeto']
    # Nada privado chegou, nem selado.
    tudo = str(banco._con().execute('SELECT * FROM mensagens').fetchall()) + str(banco.memorias())
    assert '1234' not in tudo and 'asma' not in tudo and 'segredo' not in tudo


def test_rodar_de_novo_nao_duplica_nos_dois_sentidos(lados):
    _pc_com_de_tudo()
    pacote = juntar.exportar()
    lados('servidor')
    juntar.importar(pacote)
    assert not any(juntar.importar(pacote).values())
    de_la = juntar.exportar()
    lados('pc')
    # O que o servidor manda de volta é o que veio daqui: nada entra.
    assert not any(juntar.importar(de_la).values())
    assert len(banco.conversas()) == 3  # as duas daqui com o público, e a só privada


def test_o_que_o_celular_fez_no_servidor_chega_no_pc(lados):
    cv_pc, velha = _pc_com_de_tudo()
    pacote = juntar.exportar()
    lados('servidor')
    juntar.importar(pacote)
    # No celular: uma mensagem nova na mesma conversa, uma memória que substitui
    # a do trabalho, e a tarefa feita.
    cv = min(banco.conversas(), key=lambda c: c['id'])  # a da conta
    banco.adicionar(cv['id'], 'pessoa', 'E 3 + 3?')
    [m] = banco.memorias()
    banco.adicionar_memoria('Trabalha na Bayer.', 'Trabalho', False, cv['id'], substitui=m['id'])
    [t] = banco.tarefas_abertas(10)
    with banco._con() as c:
        c.execute("UPDATE tarefas SET feita = '2026-11-27T10:00:00+00:00' WHERE id = ?", (t['id'],))
    de_la = juntar.exportar()
    lados('pc')
    assert juntar.importar(de_la) == {'conversas': 0, 'mensagens': 1, 'memorias': 1, 'tarefas': 0,
                                      'compromissos': 0, 'feitas': 1}
    assert banco.mensagens(cv_pc)[-1]['texto'] == 'E 3 + 3?'  # na mesma conversa
    validas = [m['texto'] for m in banco.memorias() if not m.get('privada')]
    assert 'Trabalha na Bayer.' in validas and 'Trabalha na Syngenta.' not in validas
    # A pública ficou feita; a privada é só daqui e continua aberta.
    assert [t['texto'] for t in banco.tarefas_abertas(10)] == ['Consulta no psiquiatra']


def test_o_que_foi_apagado_aqui_nao_volta_de_la(lados):
    _, velha = _pc_com_de_tudo()
    pacote = juntar.exportar()
    lados('servidor')
    juntar.importar(pacote)
    de_la = juntar.exportar()
    lados('pc')
    banco.apagar_memoria(velha)
    assert juntar.importar(de_la)['memorias'] == 0
    assert all(m['texto'] != 'Trabalha na Syngenta.' for m in banco.memorias())


def test_pacote_de_outra_versao_e_recusado(lados):
    with pytest.raises(juntar.PacoteInvalido):
        juntar.importar({'versao': 99})
    assert TestClient(main.app).post('/juntar', json={'versao': 99}).json()['erro'] == 'pacote_invalido'


def _servidor_falso(lados, senha='senha-do-servidor-bem-comprida-123'):
    """O servidor do outro lado da rede: o banco dele, as rotas /juntar dele."""
    def responder(pedido: httpx.Request):
        if pedido.headers.get('authorization') != f'Bearer {senha}':
            return httpx.Response(401, json={'erro': 'sem_token'})
        lados('servidor')
        try:
            if pedido.method == 'GET':
                return httpx.Response(200, json=juntar.exportar())
            import json
            return httpx.Response(200, json=juntar.importar(json.loads(pedido.content)))
        finally:
            lados('pc')
    return httpx.MockTransport(responder)


def test_juntar_pela_tela_traz_e_leva(lados, monkeypatch):
    _pc_com_de_tudo()
    monkeypatch.setattr(juntar, '_transporte', _servidor_falso(lados))
    c = TestClient(main.app)
    assert c.post('/servidor/juntar').json()['motivo'] == 'Falta o endereço ou a senha do servidor.'
    r = c.put('/servidor', json={'endereco': 'solis.exemplo.ts.net', 'token': 'senha-do-servidor-bem-comprida-123'})
    estado = r.json()
    assert (estado['endereco'], estado['tem_senha'], estado['ultima']) == ('https://solis.exemplo.ts.net', True, None)
    assert estado['usa_pc'] is False  # usar o PC de longe é outra chave, desligada até o Matheus ligar
    # A senha nunca volta pra tela, e fica selada no banco.
    assert 'senha-do-servidor' not in str(c.get('/servidor').json())
    feito = c.post('/servidor/juntar').json()
    assert feito['levados']['mensagens'] == 3 and feito['trazidos']['mensagens'] == 0
    # De novo: nada novo dos dois lados.
    feito = c.post('/servidor/juntar').json()
    assert not any(feito['levados'].values()) and not any(feito['trazidos'].values())
    assert c.get('/servidor').json()['ultima']['quando']
    # Trocar só o endereço mantém a senha.
    assert c.put('/servidor', json={'endereco': 'https://outro.ts.net'}).json()['tem_senha'] is True


def test_senha_errada_diz_em_palavras(lados, monkeypatch):
    monkeypatch.setattr(juntar, '_transporte', _servidor_falso(lados, senha='outra-senha-bem-comprida-456789'))
    c = TestClient(main.app)
    c.put('/servidor', json={'endereco': 'https://solis.exemplo.ts.net', 'token': 'senha-errada-bem-comprida-000'})
    r = c.post('/servidor/juntar')
    assert r.status_code == 502 and r.json()['motivo'] == 'O servidor não aceitou a senha.'
