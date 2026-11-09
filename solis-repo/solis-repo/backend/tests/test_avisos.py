"""Avisos na hora: o que a notificação do Windows mostra, quando, e que nada se
repete — inclusive depois de religar o servidor."""
import asyncio
import datetime as dt
import os

import pytest

from solis import avisos, banco

SEG = dt.datetime(2026, 11, 9, 8, 50)  # segunda, 8h50


def conferir(agora):
    return asyncio.run(avisos.conferir(agora))


def test_compromisso_avisa_10_minutos_antes_uma_vez_so(sem_aviso_de_verdade):
    banco.adicionar_compromisso('Reunião de alinhamento', '2026-11-09', '09:00', 60, 'Google Meet')
    assert conferir(SEG - dt.timedelta(minutes=1)) == 0  # 8h49: ainda não
    assert conferir(SEG) == 1
    assert sem_aviso_de_verdade[0]['titulo'] == 'Reunião de alinhamento'
    assert sem_aviso_de_verdade[0]['texto'] == 'Às 9h, daqui a 10 min · Google Meet'
    assert conferir(SEG + dt.timedelta(minutes=5)) == 0  # já avisou
    assert len(sem_aviso_de_verdade) == 1


def test_servidor_ligado_atrasado_avisa_ate_o_compromisso_comecar(sem_aviso_de_verdade):
    banco.adicionar_compromisso('Reunião', '2026-11-09', '09:00')
    assert conferir(dt.datetime(2026, 11, 9, 9, 0)) == 0  # já começou: não serve mais
    assert conferir(dt.datetime(2026, 11, 9, 8, 59)) == 1
    assert sem_aviso_de_verdade[0]['texto'] == 'Às 9h, agora'


def test_mudar_a_hora_avisa_de_novo_na_hora_nova(sem_aviso_de_verdade):
    c = banco.adicionar_compromisso('Reunião', '2026-11-09', '09:00')
    conferir(SEG)
    banco.mudar_compromisso(c, hora='10:30')
    assert conferir(dt.datetime(2026, 11, 9, 10, 20)) == 1
    assert sem_aviso_de_verdade[1]['texto'] == 'Às 10h30, daqui a 10 min'


def test_tarefa_com_hora_avisa_na_hora_e_a_feita_nao(sem_aviso_de_verdade):
    banco.adicionar_tarefa('Mandar o email pro professor', '2026-11-09', '20:00')
    feita = banco.adicionar_tarefa('Já feita', '2026-11-09', '20:00')
    banco.mudar_tarefa(feita, feita=True)
    assert conferir(dt.datetime(2026, 11, 9, 19, 59)) == 0
    assert conferir(dt.datetime(2026, 11, 9, 20, 30)) == 1
    assert sem_aviso_de_verdade[-1] == {**sem_aviso_de_verdade[-1], 'titulo': 'Mandar o email pro professor',
                                         'texto': 'Tarefa pra agora (20h)'}
    # Passou da hora de tolerância: uma tarefa de outra que ninguém avisou não aparece mais.
    banco.adicionar_tarefa('Outra', '2026-11-09', '18:00')
    assert conferir(dt.datetime(2026, 11, 9, 20, 30)) == 0


def test_resumo_da_manha_junta_o_dia(sem_aviso_de_verdade):
    banco.adicionar_tarefa('Pagar a conta de luz', '2026-11-09')
    banco.adicionar_tarefa('Renovar a CNH', '2026-11-09')
    banco.adicionar_tarefa('Amanhã não entra', '2026-11-10')
    banco.adicionar_compromisso('Aniversário da mãe', '2026-11-09')
    assert conferir(dt.datetime(2026, 11, 9, 7, 59)) == 0
    assert conferir(dt.datetime(2026, 11, 9, 8, 0)) == 1
    assert sem_aviso_de_verdade[0] == {**sem_aviso_de_verdade[0], 'titulo': 'Hoje',
                                       'texto': 'Pagar a conta de luz · Renovar a CNH · Aniversário da mãe (dia todo)'}
    assert conferir(dt.datetime(2026, 11, 9, 12, 0)) == 0  # um por dia
    # Dia sem nada: sem resumo vazio.
    assert conferir(dt.datetime(2026, 11, 11, 8, 0)) == 0


def test_resumo_da_manha_corta_em_tres_e_a_noite_nao_avisa(sem_aviso_de_verdade):
    for i in range(5):
        banco.adicionar_tarefa(f'Tarefa {i}', '2026-11-09')
    assert conferir(dt.datetime(2026, 11, 9, 20, 0)) == 0  # ligou de noite: o da manhã não serve mais
    assert conferir(dt.datetime(2026, 11, 9, 19, 0)) == 1
    assert sem_aviso_de_verdade[0]['texto'] == 'Tarefa 0 · Tarefa 1 · Tarefa 2 · e mais 2'


def test_privado_nao_mostra_o_titulo(sem_aviso_de_verdade):
    banco.adicionar_compromisso('Consulta com o psiquiatra', '2026-11-09', '09:00', onde='Clínica X', privado=True)
    banco.adicionar_tarefa('Pagar a fatura do cartão', '2026-11-09', privada=True)
    conferir(SEG)
    textos = ' '.join(f'{a["titulo"]} {a["texto"]}' for a in sem_aviso_de_verdade)
    assert 'Compromisso privado' in textos and 'uma tarefa privada' in textos
    assert 'psiquiatra' not in textos and 'Clínica' not in textos and 'fatura' not in textos


def test_aviso_que_falhou_tenta_de_novo(monkeypatch):
    tentativas = []

    async def falha(titulo, texto, tag):
        tentativas.append(tag)
        return False
    monkeypatch.setattr(avisos, 'mostrar', falha)
    banco.adicionar_compromisso('Reunião', '2026-11-09', '09:00')
    assert conferir(SEG) == 0
    assert conferir(SEG + dt.timedelta(seconds=30)) == 0
    assert len(tentativas) == 2 and banco.avisos_mostrados() == set()


def test_desligados_nao_avisam(sem_aviso_de_verdade):
    banco.adicionar_compromisso('Reunião', '2026-11-09', '09:00')
    banco.guardar_ajuste('avisos', False)
    assert conferir(SEG) == 0 and sem_aviso_de_verdade == []


def test_marcados_velhos_saem_da_tabela():
    banco._con().execute("INSERT INTO avisos (chave, mostrado) VALUES ('velho', '2020-01-01T00:00:00+00:00')")
    banco._con().commit()
    banco.marcar_aviso('novo')
    assert banco.avisos_mostrados() == {'novo'}


@pytest.mark.skipif(os.name != 'nt', reason='o aviso é o do Windows')
def test_script_do_windows_recusa_entrada_quebrada():
    """O script de verdade, sem pôr aviso na tela: entrada que não é JSON falha
    com erro, e o Solis não marca o aviso como mostrado."""
    import subprocess
    r = subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(avisos.SCRIPT)],
        input=b'isto nao e json', capture_output=True, timeout=60,
    )
    assert r.returncode != 0 and not r.stdout.startswith(b'ok')
