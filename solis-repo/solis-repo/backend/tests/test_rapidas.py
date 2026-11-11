"""O básico em código (rapidas.py): sai na hora, sem modelo e sem busca, e
não erra a hora."""
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from solis import banco, main, ollama, rapidas, roteador

AGORA = dt.datetime(2026, 11, 11, 10, 38)


@pytest.mark.parametrize('frase, resposta', [
    ('Que horas são?', 'São 10h38.'),
    ('Solis, que horas são agora?', 'São 10h38.'),
    ('Que dia é hoje?', 'Hoje é quarta-feira, 11 de novembro.'),
    ('Que dia é amanhã?', 'Amanhã é quinta-feira, 12 de novembro.'),
    ('Me lembra de beber água daqui a 20 minutos.', 'Anotado: beber água. Te aviso hoje às 10h58.'),
    ('Me lembra de ir no banco amanhã às 15h', 'Anotado: ir no banco. Te aviso amanhã às 15h.'),
    ('me lembra de ligar pro João na sexta às 10h', 'Anotado: ligar pro João. Te aviso sexta às 10h.'),
])
def test_respostas_na_hora(frase, resposta):
    assert rapidas.responder(frase, AGORA)['texto'] == resposta


@pytest.mark.parametrize('frase', [
    'que horas são boas pra marcar com a Paula?',
    'Quero ação.',
    'Me explica o que é IGP-M',
    'Me lembra do nome daquele filme?',
])
def test_o_resto_vai_pro_modelo(frase):
    assert rapidas.responder(frase, AGORA) is None


def test_agenda_e_tarefas_do_banco():
    banco.adicionar_compromisso('Dentista', '2026-11-12', '14:00', 60, 'Clínica Sorriso')
    banco.adicionar_tarefa('Pagar a conta de luz', '2026-11-11')
    banco.adicionar_tarefa('Ligar pro João', '2026-11-10', '09:00')  # atrasada: entra no "hoje"
    banco.adicionar_tarefa('Renovar a CNH', '2026-11-30')
    assert rapidas.responder('O que eu tenho na agenda amanhã?', AGORA)['texto'] == 'Amanhã você tem dentista às 14h, na Clínica Sorriso.'
    assert rapidas.responder('O que eu tenho hoje?', AGORA)['texto'] == 'Nada na agenda hoje.'
    assert rapidas.responder('Quais são minhas tarefas pra hoje?', AGORA)['texto'] == (
        '2 tarefas pra hoje: ligar pro João às 9h e pagar a conta de luz.'
    )


def test_que_horas_sao_nao_chama_modelo_nem_busca(monkeypatch):
    async def nao(*a, **k):
        raise AssertionError('chamou o modelo')
    monkeypatch.setattr(roteador, 'responder', nao)
    monkeypatch.setattr(ollama, 'embeddings', nao)
    c = TestClient(main.app)
    conversa = c.post('/conversas').json()['id']
    r = c.post(f'/conversas/{conversa}/mensagens', json={'texto': 'Que horas são?', 'voz': True})
    linhas = [json.loads(l) for l in r.text.splitlines() if l]
    texto = ''.join(l.get('texto', '') for l in linhas)
    assert texto.startswith('São ') and texto.endswith('.')
    assert [l['etapa'] for l in linhas if 'etapa' in l] == ['guardada', 'rapida', 'fim']


def test_lembrete_pela_conversa_vira_tarefa_e_aparece_anotado(monkeypatch):
    async def nao(*a, **k):
        raise AssertionError('chamou o modelo')
    monkeypatch.setattr(roteador, 'responder', nao)
    c = TestClient(main.app)
    conversa = c.post('/conversas').json()['id']
    r = c.post(f'/conversas/{conversa}/mensagens', json={'texto': 'Me lembra de beber água daqui a 20 minutos'})
    linhas = [json.loads(l) for l in r.text.splitlines() if l]
    aprendeu = next(l for l in linhas if l.get('etapa') == 'aprendizado')
    assert aprendeu['tarefas'][0]['texto'] == 'Beber água'
    assert [t['texto'] for t in banco.tarefas_abertas(5)] == ['Beber água']


@pytest.mark.parametrize('ouvido, tipo', [
    ('E horas são.', 'hora'),            # o Whisper comeu o "qu"
    ('O que eu tenho a manhã?', 'agenda'),
    ('Ok, eu tenho a manhã.', 'agenda'),
    ('Me lembro de beber água daqui a 20 minutos.', 'lembrete'),
])
def test_erros_de_ouvido_que_nao_mudam_o_pedido(ouvido, tipo):
    assert rapidas.responder(ouvido, AGORA)['tipo'] == tipo
