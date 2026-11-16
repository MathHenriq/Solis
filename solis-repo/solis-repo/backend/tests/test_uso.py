"""O uso da cota do Claude (docs/PARIDADE.md): as linhas do /usage do CLI viram
as barras de Configurações → Uso."""
import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from solis import main, uso

TEXTO = """You are currently using your subscription to power your Claude Code usage

Current session: 74% used · resets Nov 16, 12:29am (America/Sao_Paulo)
Current week (all models): 60% used · resets Nov 18, 1:59pm (America/Sao_Paulo)
Current week (Fable): 0% used · resets Nov 18, 1:59pm (America/Sao_Paulo)

What's contributing to your usage?
Last 24h · 587 requests · 28 sessions
"""


def test_le_as_linhas():
    cotas = uso.ler_texto(TEXTO, datetime(2026, 11, 15, 21, 0))
    assert cotas == [
        {'tipo': 'sessao', 'rotulo': 'Sessão atual', 'usado': 74, 'volta': '2026-11-16T00:29'},
        {'tipo': 'semana', 'rotulo': 'Semana, todos os modelos', 'usado': 60, 'volta': '2026-11-18T13:59'},
        {'tipo': 'semana-fable', 'rotulo': 'Semana, só o Fable', 'usado': 0, 'volta': '2026-11-18T13:59'},
    ]


def test_virada_do_ano_e_sem_hora():
    assert uso.ler_texto('Current session: 5% used · resets Jan 2, 3am (X)',
                         datetime(2026, 12, 31, 22, 0))[0]['volta'] == '2027-01-02T03:00'
    assert uso.ler_texto('Current session: 5% used', datetime(2026, 12, 31))[0]['volta'] is None
    assert uso.ler_texto('outro formato') == []


def test_rota(monkeypatch):
    async def perguntar():
        return {'plano': 'Claude Pro', 'texto': TEXTO}
    monkeypatch.setattr(uso, '_perguntar', perguntar)
    monkeypatch.setattr(uso, '_cache', {'quando': 0.0, 'dados': None})
    r = TestClient(main.app).get('/uso').json()
    assert r['plano'] == 'Claude Pro' and [c['usado'] for c in r['cotas']] == [74, 60, 0]

    async def mudou():
        return {'plano': 'Claude Pro', 'texto': 'Session usage: lots'}
    monkeypatch.setattr(uso, '_perguntar', mudou)
    r = TestClient(main.app).get('/uso?atualizar=true')
    assert r.status_code == 502 and r.json()['erro'] == 'nao_deu'
    # Dentro do minuto, sem atualizar: o guardado.
    monkeypatch.setattr(uso, '_cache', {'quando': 9e18, 'dados': {'plano': None, 'cotas': [], 'quando': 'x'}})
    assert TestClient(main.app).get('/uso').json()['quando'] == 'x'
