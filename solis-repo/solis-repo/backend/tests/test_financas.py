"""As finanças do Assessor (financas.py, 22/11/2026): "gastei 50 no mercado" vira
o lançamento certo, e o resumo do mês bate com a conta."""
import asyncio
from datetime import date

import pytest

from solis import banco, cofre, corpo, financas as f

HOJE = date(2026, 11, 25)


@pytest.mark.parametrize('texto, centavos', [
    ('50', 5000), ('12,90', 1290), ('R$ 1.234,56', 123456), ('2 mil', 200000), ('2,5 mil', 250000),
    ('2 mil e 500', 250000), ('18 e 50', 1850), ('cento e vinte', 12000), ('mil e duzentos', 120000),
    ('vinte e cinco reais e cinquenta centavos', 2550), ('50 conto', 5000), ('89.90', 8990), ('nada', None),
])
def test_os_valores_falados_viram_centavos(texto, centavos):
    assert f.valor_de(texto) == centavos


@pytest.mark.parametrize('frase, esperado', [
    ('Gastei 50 no mercado.', ('gasto', 5000, 'mercado', 'mercado')),
    ('Solis, anota que paguei 120 de luz', ('gasto', 12000, 'contas da casa', 'luz')),
    ('Almocei por 35 reais.', ('gasto', 3500, 'alimentação', 'almoço')),
    ('Recebi 2 mil de salário.', ('entrada', 200000, 'salário', 'salário')),
    ('Uber de 18 e 50.', ('gasto', 1850, 'transporte', 'uber')),
    ('Paguei cento e vinte no pix pro dentista.', ('gasto', 12000, 'saúde', 'dentista')),
    ('Vendi meu monitor por 700.', ('entrada', 70000, 'venda', 'monitor')),
    ('Paguei 89,90 da internet dia 10/11', ('gasto', 8990, 'contas da casa', 'internet')),
])
def test_a_frase_vira_o_lancamento_sem_ia(frase, esperado):
    r = f.interpretar(frase, HOJE)
    assert (r['tipo'], r['centavos'], r['categoria'], r['descricao']) == esperado


def test_a_forma_e_o_dia_e_o_que_nao_e_lancamento():
    assert f.interpretar('paguei cento e vinte no pix pro dentista', HOJE)['forma'] == 'pix'
    assert f.interpretar('abasteci 200 ontem', HOJE)['dia'] == '2026-11-24'
    assert f.interpretar('paguei 89,90 da internet dia 10/11', HOJE)['dia'] == '2026-11-10'
    assert f.interpretar('qual é a capital da Austrália?', HOJE) is None
    assert f.interpretar('quanto gastei esse mês?', HOJE) is None


def test_a_categoria_e_sempre_uma_das_fixas():
    assert f.categoria_de('pão e leite', sugerida='Mercado') == 'mercado'  # a sugerida, se é fixa
    assert f.categoria_de('gasolina', sugerida='carro e afins') == 'transporte'  # senão, pelas palavras
    assert f.categoria_de('coisa estranha') == 'outros'
    assert f.categoria_de('pix do João', tipo='entrada') == 'outras entradas'


def test_o_resumo_do_mes_bate_com_a_conta(monkeypatch):
    monkeypatch.setattr(corpo, '_hoje', lambda: HOJE)
    for valor, descricao, tipo, data in [('50', 'mercado', 'gasto', '03/11'), ('120', 'luz', 'gasto', '10/11'),
                                         ('35,50', 'almoço', 'gasto', 'hoje'), ('2 mil', 'salário', 'entrada', '05/11'),
                                         ('80', 'mercado', 'gasto', '20/11'), ('999', 'tv', 'gasto', '30/10')]:
        asyncio.run(corpo._lancar({'valor': valor, 'descricao': descricao, 'tipo': tipo, 'data': data}))
    r = f.resumo(*f.periodo_de('este mês', HOJE)[:2])
    # 50 + 120 + 35,50 + 80 (a TV é de outubro); entrada 2.000.
    assert r['gastos'] == 28550 and r['entradas'] == 200000 and r['saldo'] == 200000 - 28550
    assert r['por_categoria'] == {'contas da casa': 12000, 'mercado': 13000, 'alimentação': 3550}
    texto = asyncio.run(corpo._gastos({'periodo': 'este mês'}))
    assert 'gastos de R$ 285,50' in texto and 'saldo de R$ 1.714,50' in texto
    assert f.resumo(*f.periodo_de('mês passado', HOJE)[:2])['gastos'] == 99900


def test_a_descricao_fica_selada_e_apagar_se_desfaz_no_banco(monkeypatch):
    monkeypatch.setattr(corpo, '_hoje', lambda: HOJE)
    saida = asyncio.run(corpo._lancar({'valor': '40', 'descricao': 'farmácia', 'tipo': 'gasto'}))
    assert saida == ('Anotado: gasto de R$ 40,00 em saúde (farmácia), hoje. No mês, saúde soma R$ 40,00 e os '
                     'gastos, R$ 40,00. (lançamento nº 1)')
    bruto = banco._con().execute('SELECT descricao FROM lancamentos').fetchone()[0]
    assert 'farm' not in bruto and cofre.abrir(bruto) == 'farmácia'
    assert asyncio.run(corpo._apagar_lancamento({'numero': 'ultimo'})).startswith('Apagado o lançamento #1')
    assert banco.lancamentos('2026-11-01', '2026-11-30') == []
    assert banco._con().execute('SELECT apagado FROM lancamentos').fetchone()[0]  # marcado, não sumiu


def test_valor_que_nao_da_pra_ler_nao_vira_lancamento():
    assert 'Não entendi o valor' in asyncio.run(corpo._lancar({'valor': 'uns trocados', 'descricao': 'x'}))
    assert banco.ultimo_lancamento() is None


def test_as_ferramentas_sao_do_solis_e_vao_ao_vivo():
    from solis import pedido_ao_vivo
    nomes = [x.nome for x in corpo.DO_SOLIS]
    assert {'lancar', 'gastos', 'apagar_lancamento'} <= set(nomes)
    c = corpo.Corpo(1, None, navegar=False, cerebro='gemini-live')
    c.voz = True
    ao_vivo = [s['function']['name'] for s in pedido_ao_vivo.ferramentas(c, asyncio.run(c.especificacoes()))]
    assert {'mcp__solis__lancar', 'mcp__solis__gastos'} <= set(ao_vivo)


# --- o lançamento como pedido rápido (rapidas.py) ------------------------------

@pytest.mark.parametrize('frase, e_lancamento', [
    ('Gastei 50 no mercado.', True), ('Uber de 18 e 50.', True), ('Netflix, 55,90.', True),
    ('Solis, anota que paguei 120 de luz', True), ('Vendi meu monitor por 700.', True),
    ('lança 45 de farmácia', True), ('anota 30 de uber', True), ('anota 50', False),
    ('quanto custa 50 reais em dólar?', False), ('me lembra de pagar 120 de luz amanhã', False),
    ('vou pagar 200 de aluguel', False), ('o jogo foi 2 a 1', False), ('o Flamengo ganhou de 3 a 0', False),
    ('minha senha é 1234', False), ('em 2025 eu gastei muito', False), ('comprei pão', False),
])
def test_so_o_que_e_lancamento_vira_lancamento_na_hora(frase, e_lancamento):
    assert f.parece_lancamento(frase) is e_lancamento


@pytest.mark.parametrize('frase', [
    'recebi uma proposta de emprego em outra empresa', 'recebi um email do meu chefe', 'comprei um livro',
    'ganhei uma camiseta', 'gastei um pouco hoje', 'paguei uma conta', 'comprei dois pães',
])
def test_numero_que_e_quantidade_nao_vira_lancamento(frase):
    """25/11/2026: o "um" de "recebi um email" era lido como valor, e a frase virava
    lançamento de R$ 1,00 sozinha."""
    assert not f.parece_lancamento(frase)


def test_a_quantidade_antes_do_valor_nao_e_o_valor():
    assert f.interpretar('comprei 3 camisetas por 90', HOJE)['centavos'] == 9000
    assert f.interpretar('paguei 2 parcelas de 150', HOJE)['centavos'] == 15000
    assert f.interpretar('comprei um livro de sessenta reais', HOJE)['centavos'] == 6000


def test_as_20_frases_da_medicao_sao_todas_pedido_rapido():
    """As 20 da medição de 22/11/2026: a leitura acertou 20, a Groq 15 e o Gemini 19."""
    import sys
    from pathlib import Path
    frases = ['Gastei 50 no mercado.', 'Paguei 120 de luz.', 'Almocei por 35 reais.', 'Recebi 2 mil de salário.',
              'Uber de 18 e 50.', 'Comprei um tênis de 299 e 90 no cartão.', 'Paguei cento e vinte no pix pro dentista.',
              'Gastei R$ 1.200 no aluguel.', 'Abasteci 200 reais ontem.', 'Ganhei 350 de um freela.',
              'Gastei 25 e 50 no iFood.', 'Deixei 2 mil e 500 na oficina.', 'Paguei 89,90 da internet.',
              'Netflix, 55,90.', 'Gastei 40 na farmácia.', 'Paguei 150 na academia.', 'Comprei um livro de 60 reais.',
              'Gastei 80 no cinema com a minha namorada.', 'Vendi meu monitor por 700.', 'Gastei 12 reais no café.']
    assert [x for x in frases if not f.parece_lancamento(x)] == []


def test_pela_conversa_o_lancamento_sai_na_hora_sem_cerebro(monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from solis import main, roteador

    async def nao(*a, **k):
        raise AssertionError('chamou o cérebro')
    monkeypatch.setattr(roteador, 'responder', nao)
    c = TestClient(main.app)
    conversa = c.post('/conversas').json()['id']
    r = c.post(f'/conversas/{conversa}/mensagens', json={'texto': 'Gastei 50 no mercado', 'voz': True})
    linhas = [json.loads(l) for l in r.text.splitlines() if l]
    texto = ''.join(l.get('texto', '') for l in linhas)
    assert texto.startswith('Anotado: gasto de R$ 50,00 em mercado, hoje. No mês, mercado soma R$ 50,00')
    assert [l['etapa'] for l in linhas if 'etapa' in l] == ['guardada', 'personalidade', 'rapida', 'fim']
    [l] = banco.lancamentos('2000-01-01', '2999-12-31')
    assert (l['centavos'], l['categoria'], l['conversa']) == (5000, 'mercado', conversa)
    assert banco.tarefas_abertas(5) == []  # lançamento não vira tarefa


def test_ao_vivo_o_lancamento_vai_pelo_caminho_rapido(monkeypatch):
    """O pedido ao vivo não gasta o Gemini com o que o código responde na hora."""
    import json
    from fastapi.testclient import TestClient
    from solis import main, registro_voz
    from test_pedido_ao_vivo import GeminiFalso, _chamar, _escuta
    _escuta(monkeypatch, texto='gastei 50 no mercado')
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'falar': True}))
        _chamar(ws)
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'gastei 50 no mercado'}
    assert all(g.texto is None for g in GeminiFalso.criadas)
    assert [e['caminho'] for e in registro_voz.ler() if e['evento'] == 'pedido'] == ['rapida']


@pytest.mark.parametrize('pergunta, nome', [
    ('Quanto gastei esse mês?', 'Novembro até hoje'), ('Solis, quanto eu gastei hoje?', 'Hoje'),
    ('Meus gastos de outubro', 'Outubro de 2026'), ('Quanto recebi no mês passado?', 'Outubro de 2026'),
    ('Como estão minhas finanças?', 'Novembro até hoje'), ('quanto gastei essa semana', 'Esta semana'),
])
def test_quanto_gastei_sai_na_hora_e_bate_com_a_conta(pergunta, nome):
    import datetime as dt
    from solis import rapidas
    banco.adicionar_lancamento('2026-11-25', 5000, 'gasto', 'mercado', 'mercado')
    banco.adicionar_lancamento('2026-11-24', 1850, 'gasto', 'transporte', 'uber')
    banco.adicionar_lancamento('2026-10-10', 200000, 'entrada', 'salário', 'salário')
    r = rapidas.responder(pergunta, dt.datetime(2026, 11, 25, 10, 0))
    assert r['tipo'] == 'gastos' and r['texto'].startswith(f'{nome}: ')
    if nome == 'Hoje':
        assert 'gastos de R$ 50,00' in r['texto']
    if nome == 'Novembro até hoje':
        assert 'gastos de R$ 68,50' in r['texto'] and 'mercado R$ 50,00; transporte R$ 18,50' in r['texto']


def test_pergunta_de_gasto_que_o_codigo_nao_sabe_vai_pro_cerebro():
    import datetime as dt
    from solis import rapidas
    assert rapidas.responder('quanto gastei com uber?', dt.datetime(2026, 11, 25)) is None
    assert rapidas.responder('quanto custa um ps5?', dt.datetime(2026, 11, 25)) is None
    assert 'Nenhum lançamento hoje.' == f.resumo_em_texto(f.resumo(HOJE, HOJE), 'hoje')
