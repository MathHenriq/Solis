"""Avisos na hora: a notificação do Windows antes do compromisso e na hora da
tarefa, e um resumo de manhã com o que é do dia.

Roda dentro do servidor (o front roda no navegador, e só o servidor está
sempre ligado enquanto o Solis é usado): a cada 30 s, confere o que vence e
mostra pelo avisar_windows.ps1. Cada aviso mostrado é anotado no banco
(tabela avisos) pela chave dele — o item e a hora do aviso —, então nada se
repete, e mudar a hora de um compromisso faz ele avisar de novo na hora nova.

As regras:
- compromisso com hora: ANTES_DO_COMPROMISSO minutos antes, o padrão das agendas;
- tarefa com hora: na hora;
- de manhã (MANHA): um aviso só com as tarefas do dia sem hora e os
  compromissos de dia inteiro — um por item encheria a tela;
- servidor ligado depois da hora: avisa o que ainda serve — o compromisso até
  começar, a tarefa até uma hora depois, o da manhã até ATE_A_NOITE;
- privado: o aviso não diz o título (aparece até na tela bloqueada), só que há
  um compromisso ou uma tarefa privada, e a hora.
"""
import asyncio
import base64
import datetime as dt
import json
import logging
import os
import subprocess
from pathlib import Path

from . import banco

log = logging.getLogger('solis.avisos')

ANTES_DO_COMPROMISSO = 10  # minutos
TOLERANCIA_TAREFA = 60  # minutos depois da hora em que ainda vale avisar
MANHA = dt.time(8, 0)
ATE_A_NOITE = dt.time(20, 0)
INTERVALO = 30  # segundos entre uma conferida e outra
SCRIPT = Path(__file__).with_name('avisar_windows.ps1')


def _hora_curta(hora: str) -> str:
    h, m = hora.split(':')
    return f'{int(h)}h{"" if m == "00" else m}'


def _junto(dia: str, hora: str) -> dt.datetime:
    return dt.datetime.combine(dt.date.fromisoformat(dia), dt.time.fromisoformat(hora))


def pendentes(agora: dt.datetime) -> list[dict]:
    """Os avisos que deviam estar na tela agora e ainda não foram mostrados:
    {chave, titulo, texto}. Não marca nada — quem mostra marca."""
    hoje = agora.date().isoformat()
    ja = banco.avisos_mostrados()
    saida = []

    for c in banco.compromissos(hoje, (agora.date() + dt.timedelta(days=1)).isoformat()):
        if not c['hora']:
            continue
        inicio = _junto(c['dia'], c['hora'])
        quando = inicio - dt.timedelta(minutes=ANTES_DO_COMPROMISSO)
        chave = f'compromisso:{c["id"]}:{inicio.isoformat(timespec="minutes")}'
        if chave in ja or not quando <= agora < inicio:
            continue
        falta = round((inicio - agora).total_seconds() / 60)
        partes = [f'Às {_hora_curta(c["hora"])}, ' + ('agora' if falta <= 1 else f'daqui a {falta} min')]
        if c['onde'] and not c['privado']:
            partes.append(c['onde'])
        saida.append({
            'chave': chave,
            'titulo': 'Compromisso privado' if c['privado'] else c['titulo'],
            'texto': ' · '.join(partes),
        })

    for t in banco.tarefas_abertas(500):
        if t['prazo'] != hoje or not t['hora']:
            continue
        hora = _junto(t['prazo'], t['hora'])
        chave = f'tarefa:{t["id"]}:{hora.isoformat(timespec="minutes")}'
        if chave in ja or not hora <= agora < hora + dt.timedelta(minutes=TOLERANCIA_TAREFA):
            continue
        saida.append({
            'chave': chave,
            'titulo': 'Tarefa privada' if t['privada'] else t['texto'],
            'texto': f'Tarefa pra agora ({_hora_curta(t["hora"])})',
        })

    chave = f'manha:{hoje}'
    if chave not in ja and MANHA <= agora.time() < ATE_A_NOITE:
        itens = [
            ('uma tarefa privada' if t['privada'] else t['texto'])
            for t in banco.tarefas_abertas(500) if t['prazo'] == hoje and not t['hora']
        ] + [
            ('um compromisso privado' if c['privado'] else c['titulo']) + ' (dia todo)'
            for c in banco.compromissos(hoje, hoje) if not c['hora']
        ]
        if itens:
            saida.append({
                'chave': chave,
                'titulo': 'Hoje',
                'texto': ' · '.join(itens[:3]) + (f' · e mais {len(itens) - 3}' if len(itens) > 3 else ''),
            })
    return saida


async def mostrar(titulo: str, texto: str, tag: str) -> bool:
    """A notificação do Windows. False se não deu (fora do Windows, ou o
    PowerShell falhou) — aí o aviso não é marcado e a próxima volta tenta."""
    if os.name != 'nt':
        log.info('aviso (sem Windows): %s — %s', titulo, texto)
        return False
    corpo = json.dumps({'titulo': titulo, 'texto': texto, 'tag': tag[-64:]}, ensure_ascii=False).encode('utf-8')
    # subprocess numa thread, e não asyncio.create_subprocess_exec: com o
    # --reload do `npm run backend`, o uvicorn no Windows roda num laço que não
    # abre processos (NotImplementedError) — e nenhum aviso saía (11/11/2026).
    # É o mesmo motivo do cerebros.py.
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT)],
            input=corpo, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.error('aviso não saiu: %s', e)
        return False
    if proc.returncode or not proc.stdout.decode('utf-8', 'replace').startswith('ok'):
        log.error('aviso não saiu: %s', proc.stderr.decode('utf-8', 'replace').strip()[:300])
        return False
    return True


def ligados() -> bool:
    return banco.ajuste('avisos') is not False and os.environ.get('SOLIS_AVISOS') != '0'


async def conferir(agora: dt.datetime | None = None) -> int:
    """Mostra o que vence agora. Devolve quantos avisos saíram."""
    if not ligados():
        return 0
    mostrados = 0
    for aviso in pendentes(agora or dt.datetime.now()):
        # A tag no Windows não pode ter mais que 64 caracteres; a chave é curta.
        if await mostrar(aviso['titulo'], aviso['texto'], base64.urlsafe_b64encode(aviso['chave'].encode()).decode()):
            banco.marcar_aviso(aviso['chave'])
            mostrados += 1
            log.info('aviso: %s', aviso['chave'])
    return mostrados


async def vigiar() -> None:
    """O laço do servidor: confere a cada INTERVALO segundos, pra sempre."""
    while True:
        try:
            await conferir()
        except Exception:
            log.exception('a conferida dos avisos falhou')
        await asyncio.sleep(INTERVALO)
