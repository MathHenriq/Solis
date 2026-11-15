"""Tarefas agendadas (docs/PARIDADE.md): um pedido que o Claude faz sozinho num
horário — uma vez, todo dia, nos dias úteis, toda semana ou de hora em hora —,
como as tarefas agendadas do Claude Desktop. Cada vez que roda, abre uma
conversa com o nome da tarefa (aparece nos Recentes) e avisa no Windows quando
acaba. Quem roda é o main (_rodar_agendada): o mesmo caminho de uma mensagem.

O relógio é o do servidor, como o dos avisos (avisos.py): com o app fechado,
não roda; a que venceu com o app fechado roda quando ele abrir de novo, uma
vez só, se ainda estiver dentro de ATRASO_MAX.
"""
import datetime as dt
import logging

from . import banco

log = logging.getLogger('solis.agendadas')

FREQUENCIAS = ('uma_vez', 'diaria', 'dias_uteis', 'semanal', 'hora_em_hora')
# A que venceu com o app fechado ainda roda se o atraso for menor que isto.
ATRASO_MAX = dt.timedelta(hours=6)
DIAS = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')


class AgendaInvalida(ValueError):
    pass


def validar(frequencia: str, hora: str, dia_semana: int | None = None, data: str | None = None) -> None:
    if frequencia not in FREQUENCIAS:
        raise AgendaInvalida('frequência')
    try:
        dt.time.fromisoformat(hora)
    except (TypeError, ValueError) as e:
        raise AgendaInvalida('hora') from e
    if frequencia == 'semanal' and (dia_semana is None or not 0 <= dia_semana <= 6):
        raise AgendaInvalida('dia da semana')
    if frequencia == 'uma_vez':
        try:
            dt.date.fromisoformat(data or '')
        except ValueError as e:
            raise AgendaInvalida('data') from e


def proxima(frequencia: str, hora: str, depois_de: dt.datetime, dia_semana: int | None = None,
            data: str | None = None) -> dt.datetime | None:
    """A próxima vez depois de `depois_de` (hora local, sem fuso). None: uma
    vez só, e já passou."""
    h = dt.time.fromisoformat(hora)
    if frequencia == 'uma_vez':
        quando = dt.datetime.combine(dt.date.fromisoformat(data), h)
        return quando if quando > depois_de else None
    if frequencia == 'hora_em_hora':
        quando = depois_de.replace(minute=h.minute, second=0, microsecond=0)
        return quando if quando > depois_de else quando + dt.timedelta(hours=1)
    dia = depois_de.date()
    for _ in range(8):
        quando = dt.datetime.combine(dia, h)
        ok = (frequencia == 'diaria'
              or (frequencia == 'dias_uteis' and dia.weekday() < 5)
              or (frequencia == 'semanal' and dia.weekday() == dia_semana))
        if ok and quando > depois_de:
            return quando
        dia += dt.timedelta(days=1)
    return None


def descrever(a: dict) -> str:
    """"Todo dia às 8:00", "Toda segunda às 9:30"... pra tela e pro cartão."""
    h = a['hora'][:5].lstrip('0') if not a['hora'].startswith('00') else a['hora'][:5]
    if a['frequencia'] == 'uma_vez':
        d = dt.date.fromisoformat(a['data'])
        return f'Uma vez, {d.day:02d}/{d.month:02d} às {h}'
    if a['frequencia'] == 'hora_em_hora':
        return f'De hora em hora, aos {a["hora"][3:5]} minutos'
    if a['frequencia'] == 'semanal':
        return f'Toda {DIAS[a["dia_semana"]]} às {h}' if a['dia_semana'] < 5 else f'Todo {DIAS[a["dia_semana"]]} às {h}'
    return {'diaria': f'Todo dia às {h}', 'dias_uteis': f'Dias úteis às {h}'}[a['frequencia']]


def vencidas(agora: dt.datetime) -> list[dict]:
    """As ativas cuja vez chegou (e não passou de ATRASO_MAX)."""
    saida = []
    for a in banco.agendadas():
        if not a['ativa'] or not a['proxima']:
            continue
        quando = dt.datetime.fromisoformat(a['proxima'])
        if quando <= agora:
            if agora - quando <= ATRASO_MAX:
                saida.append(a)
            else:
                # Venceu com o app fechado há muito tempo: pula pra próxima vez.
                log.info('agendada %s pulada (venceu em %s)', a['id'], a['proxima'])
                avancar(a, agora)
    return saida


def avancar(a: dict, agora: dt.datetime) -> None:
    """Depois de rodar (ou pular): marca a próxima vez; a de uma vez desliga."""
    nova = proxima(a['frequencia'], a['hora'], agora, a['dia_semana'], a['data'])
    banco.marcar_agendada(a['id'], proxima=nova.isoformat(timespec='minutes') if nova else None,
                          ativa=bool(nova) and a['ativa'])
