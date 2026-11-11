"""O Solis responde como o Solis (11/11/2026): sabe a hora, os cérebros de nuvem
sabem o que ele faz em volta deles (lembrete com aviso, agenda), e a resposta
pedida pela voz é curta."""
from solis import ativacao, ollama, roteador


def test_contexto_tem_a_data_e_a_hora():
    assert ollama.contexto([]).startswith('Agora: ')


def test_nuvem_sabe_que_o_solis_lembra_e_avisa():
    s = roteador.SISTEMA_NUVEM
    assert 'COMO o Solis' in s and 'aviso no Windows' in s and 'nunca diga que não consegue' in s
    assert 'você sabe que horas são' in s


def test_modo_voz_pede_resposta_curta_nos_dois():
    assert ollama.VOZ in ollama.sistema([], voz=True)
    assert ollama.VOZ not in ollama.sistema([])
    assert ollama.VOZ in roteador.prompt_nuvem([], [], None, [], 'oi', voz=True)
    assert ollama.VOZ not in roteador.prompt_nuvem([], [], None, [], 'oi')


def test_palavra_sem_o_s_do_comeco():
    assert ativacao.palavra_no_inicio('Olis, que horas são?') == (True, 'Que horas são?')
    assert ativacao.palavra_no_inicio('Olímpico é o estádio.')[0] is False


# — Voz rápida no local (11/11/2026) ——————————————————————————————————————————

import datetime as dt

import pytest

from solis import memoria


AGORA = dt.datetime(2026, 11, 11, 10, 12)


@pytest.mark.parametrize('frase, esperado', [
    ('Me lembra de tomar o remédio daqui a 30 minutos.', ('2026-11-11', '10:42', True)),
    ('Me lembra de ligar pra minha mãe daqui a uma hora.', ('2026-11-11', '11:12', True)),
    ('em meia hora me chama', ('2026-11-11', '10:42', True)),
    ('daqui a uma hora e meia', ('2026-11-11', '11:42', True)),
    ('beber água daqui a mais ou menos 20 minutos', ('2026-11-11', '10:32', True)),
    ('Me lembra de sair de casa às 15h.', ('2026-11-11', '15:00', False)),
    ('às 3 da tarde liga pro João', ('2026-11-11', '15:00', False)),
    ('às 8h tomar café', ('2026-11-12', '08:00', False)),  # já passou hoje: amanhã
    ('Que horas são?', None),
    ('em 2 dias pagar conta', None),
])
def test_hora_do_lembrete_calculada_em_codigo(frase, esperado):
    assert memoria.hora_pedida(frase, AGORA) == esperado


def test_voz_vai_pro_local_primeiro(monkeypatch):
    from solis import cerebros, pc
    monkeypatch.setattr(cerebros, 'disponivel', lambda nome: True)
    monkeypatch.setattr(pc, 'disponivel', lambda: False)
    assert roteador.escolher('Que horas são?')[1][0] != 'local'
    assert roteador.escolher('Que horas são?', voz=True)[1][0] == 'local'
    # Comando na frente manda, mesmo pela voz.
    assert roteador.escolher('/claude que horas são?', voz=True)[1] == ['claude']


def test_voz_sem_raciocinio_salvo_pergunta_de_arquivo(monkeypatch):
    from solis import pc
    monkeypatch.setattr(pc, 'disponivel', lambda: True)
    assert roteador._modo_local('Que horas são?', voz=True) == {'ferramentas': False, 'pensar': False}
    assert roteador._modo_local('O que tem no meu contrato?', voz=True) == {'ferramentas': True}
    assert roteador._modo_local('Que horas são?', voz=False) == {'ferramentas': True}


def test_lembrete_entra_no_contexto_com_a_hora_pronta():
    rel = ollama.contexto([], [{'lembrete': True, 'dia': dt.date.today().isoformat(), 'hora': '10:42', 'relativa': True, 'privada': False}])
    assert 'hoje às 10:42' in rel
    absoluta = ollama.contexto([], [{'lembrete': True, 'dia': '2099-01-01', 'hora': '15:00', 'relativa': False, 'privada': False}])
    assert 'é às 15:00' in absoluta


@pytest.mark.parametrize('frase, esperado', [
    ('Me lembra de beber água daqui a 20 minutos.', ('Beber água', '10:32')),
    ('Daqui a 15 minutos me avisa pra tirar o bolo do forno.', ('Tirar o bolo do forno', '10:27')),
    ('Solis, me lembra de ligar pra minha mãe às 15h', ('Ligar pra minha mãe', '15:00')),
    ('Me lembra de tomar o remédio daqui a mais ou menos meia hora, por favor', ('Tomar o remédio', '10:42')),
    ('Me lembra daqui a 10 minutos de olhar o forno', ('Olhar o forno', '10:22')),
])
def test_lembrete_anotado_na_hora_sem_modelo(frase, esperado):
    r = memoria.lembrete_rapido(frase, AGORA)
    assert (r['texto'], r['hora']) == esperado


@pytest.mark.parametrize('frase', ['me avisa que horas são', 'Que horas são?', 'Me lembra do nome do filme'])
def test_sem_hora_fica_com_a_extracao(frase):
    assert memoria.lembrete_rapido(frase, AGORA) is None


def test_a_extracao_de_fundo_nao_anota_o_lembrete_de_novo(monkeypatch):
    import asyncio

    from solis import banco

    async def falso(modelo, instrucao, texto, esquema, *_):
        return {'memorias': [], 'tarefas': [{'texto': 'Beber água', 'prazo': '2026-11-11', 'hora': '10:32'}]}
    monkeypatch.setattr(ollama, 'responder_json', falso)
    conversa = banco.nova_conversa()
    ja = {'texto': 'Beber água', 'prazo': '2026-11-11', 'hora': '10:32'}
    banco.adicionar_tarefa(ja['texto'], ja['prazo'], ja['hora'], conversa)
    criadas = [ja]
    asyncio.run(memoria.aprender('qwen3:8b', conversa, 'Me lembra de beber água daqui a 20 minutos', [], tarefas=criadas, agora=AGORA))
    assert [t['texto'] for t in banco.tarefas_abertas(10)] == ['Beber água']
    assert criadas == [ja]
