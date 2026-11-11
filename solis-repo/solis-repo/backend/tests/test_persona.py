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
