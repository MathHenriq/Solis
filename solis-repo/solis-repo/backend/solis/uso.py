"""O uso da cota do Claude na tela (docs/PARIDADE.md), como Configurações → Uso
no Claude Desktop: quanto da sessão (a janela de 5 horas) e da semana já foi,
e quando volta.

Quem sabe é o CLI do Claude: o comando /usage dele responde sem chamar o
modelo (não gasta cota) com as linhas "Current session: 74% used · resets Nov
16, 12:29am (America/Sao_Paulo)". O Solis pede numa sessão própria, lê essas
linhas e guarda um minuto. Se o CLI mudar o texto, a tela diz que não deu pra
ler, e o texto cru fica no log."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
from datetime import datetime

log = logging.getLogger('solis.uso')

CACHE_S = 60
# "Current session: 74% used · resets Nov 16, 12:29am (America/Sao_Paulo)"
_LINHA = re.compile(r'^\s*Current (session|week \((?P<qual>[^)]+)\)):\s*(?P<pct>\d+(?:\.\d+)?)% used'
                    r'(?:\s*\S\s*resets (?P<volta>[^(\n]+?)\s*(?:\([^)]*\))?)?\s*$', re.M)
_cache: dict = {'quando': 0.0, 'dados': None}


class UsoIndisponivel(Exception):
    pass


def _quando(texto: str | None, agora: datetime) -> str | None:
    """'Nov 16, 12:29am' → '2026-11-16T00:29' (o ano: o deste ou o que vem)."""
    if not texto:
        return None
    for formato in ('%b %d, %I:%M%p', '%b %d, %I%p', '%b %d'):
        try:
            # Com o ano no texto (sem ele o Python 3.15 recusa a data).
            d = datetime.strptime(f'{texto.strip()} {agora.year}', f'{formato} %Y')
        except ValueError:
            continue
        if (agora - d).days > 1:  # "Jan 2" visto em 31/12: é o ano que vem
            d = d.replace(year=agora.year + 1)
        return d.isoformat(timespec='minutes')
    return None


def ler_texto(texto: str, agora: datetime | None = None) -> list[dict]:
    """As cotas do texto do /usage: [{tipo, rotulo, usado (0-100), volta}]."""
    agora = agora or datetime.now()
    cotas = []
    for m in _LINHA.finditer(texto or ''):
        qual = m.group('qual')
        if qual is None:
            tipo, rotulo = 'sessao', 'Sessão atual'
        elif qual.lower().startswith('all'):
            tipo, rotulo = 'semana', 'Semana, todos os modelos'
        else:
            tipo, rotulo = f'semana-{qual.lower()}', f'Semana, só o {qual}'
        cotas.append({'tipo': tipo, 'rotulo': rotulo, 'usado': round(float(m.group('pct'))),
                      'volta': _quando(m.group('volta'), agora)})
    return cotas


async def _perguntar() -> dict:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage

    from .agente import _pasta_trabalho
    opcoes = ClaudeAgentOptions(cwd=str(_pasta_trabalho()), setting_sources=[], max_turns=1)
    texto, plano = '', None
    async with ClaudeSDKClient(options=opcoes) as cliente:
        info = await cliente.get_server_info() or {}
        plano = (info.get('account') or {}).get('subscriptionType')
        await cliente.query('/usage')
        async for m in cliente.receive_response():
            if isinstance(m, ResultMessage):
                texto = str(m.result or '')
    return {'plano': plano, 'texto': texto}


async def ler(atualizar: bool = False) -> dict:
    """{'plano': 'Claude Pro', 'cotas': [...], 'quando': iso}. Guardado um minuto."""
    if not atualizar and _cache['dados'] and time.time() - _cache['quando'] < CACHE_S:
        return _cache['dados']
    laco = asyncio.get_running_loop()
    pronto: asyncio.Future = laco.create_future()

    def na_thread():
        # O SDK precisa de subprocesso: no Windows, um laço Proactor próprio
        # (o do servidor pode não ter), como o dos conectores.
        proprio = asyncio.ProactorEventLoop() if os.name == 'nt' else asyncio.new_event_loop()
        try:
            r = proprio.run_until_complete(_perguntar())
            laco.call_soon_threadsafe(pronto.set_result, r)
        except Exception as e:  # noqa: BLE001
            log.exception('não consegui ler o uso do Claude')
            laco.call_soon_threadsafe(pronto.set_exception, UsoIndisponivel(str(e)[:300]))
        finally:
            proprio.close()

    threading.Thread(target=na_thread, name='solis-uso', daemon=True).start()
    r = await pronto
    cotas = ler_texto(r['texto'])
    if not cotas:
        log.warning('o /usage veio num formato que o Solis não entende: %r', r['texto'][:500])
        raise UsoIndisponivel('formato')
    dados = {'plano': r['plano'], 'cotas': cotas, 'quando': datetime.now().isoformat(timespec='seconds')}
    _cache.update(quando=time.time(), dados=dados)
    return dados
