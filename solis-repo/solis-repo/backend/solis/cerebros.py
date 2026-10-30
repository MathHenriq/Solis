"""Cérebros externos: Claude Code e Codex, chamados pelo CLI oficial.

Usam a assinatura do Matheus, não API paga: o Solis roda o mesmo comando que
ele rodaria no terminal, logado na conta dele. Nunca extrair o login pra chamar
a API por fora — viola os termos e quebra a cada atualização dos CLIs.

Os dois rodam sem ferramentas, só conversa: o Solis já entrega o contexto
pronto no prompt. A pasta de trabalho é uma pasta vazia do próprio Solis, pra
que nenhum dos dois leia ou mexa em projeto nenhum por engano.

Flags conferidas:
- Claude Code 2.1: verificadas rodando o CLI (`-p`, `--system-prompt-file`,
  `--tools ""`, stream-json com `--include-partial-messages`).
- Codex: pela documentação (`exec --json`, `--sandbox read-only`,
  `--skip-git-repo-check`, prompt pela entrada padrão). PROVISÓRIO até rodar
  no notebook: o CLI não está instalado onde isto foi escrito.
"""
import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path

from . import banco

log = logging.getLogger('solis.cerebros')

NOMES = {'local': 'Modelo local', 'claude': 'Claude', 'codex': 'Codex'}

# Quanto esperar a primeira palavra. O CLI tem que subir e o modelo tem que
# começar a responder; depois disso o texto flui.
PRIMEIRO_PEDACO_S = 90

# Cérebro que falhou (cota, login, fora do ar) fica de lado por um tempo, pra o
# Solis não pagar a espera do erro em toda mensagem. O Claude diz quando a cota
# renova; o Codex não documenta isso, então vale o padrão.
PAUSA_PADRAO_S = 30 * 60
_fora_ate: dict[str, float] = {}


class CerebroFalhou(Exception):
    """Não saiu nenhuma palavra: CLI ausente, sem login, cota esgotada ou erro."""


def instalado(nome: str) -> bool:
    return shutil.which(nome) is not None


def disponivel(nome: str) -> bool:
    return instalado(nome) and time.time() >= _fora_ate.get(nome, 0)


def pausar(nome: str, ate: float | None = None) -> None:
    _fora_ate[nome] = ate or time.time() + PAUSA_PADRAO_S


def _pasta() -> Path:
    pasta = banco.caminho_padrao().parent / 'cerebros'
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _comando(executavel: str, *args: str) -> list[str]:
    """No Windows, o npm instala os CLIs como `.cmd`, que não roda direto como
    processo: precisa do cmd.exe. Os argumentos aqui são só flags e caminhos —
    o prompt vai pela entrada padrão justamente pra nunca passar pelo cmd."""
    caminho = shutil.which(executavel)
    if caminho is None:
        raise CerebroFalhou(f'{executavel} não está instalado')
    if caminho.lower().endswith(('.cmd', '.bat')):
        return ['cmd', '/c', caminho, *args]
    return [caminho, *args]


async def _linhas(comando: list[str], entrada: str) -> AsyncIterator[str]:
    """As linhas da saída do processo, conforme saem.

    Popen numa thread, e não asyncio.create_subprocess_exec: no Windows o uvicorn
    pode rodar num loop de eventos sem suporte a subprocesso, e o erro só
    apareceria no notebook. A thread lê e entrega cada linha ao loop."""
    loop = asyncio.get_running_loop()
    fila: asyncio.Queue[str | None] = asyncio.Queue()
    proc = subprocess.Popen(
        comando,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=_pasta(),
        text=True,
        encoding='utf-8',
        errors='replace',
    )

    erros: list[str] = []

    def ler():
        try:
            proc.stdin.write(entrada)
            proc.stdin.close()
            for linha in proc.stdout:
                loop.call_soon_threadsafe(fila.put_nowait, linha)
        except OSError:
            pass  # o processo morreu antes de ler a entrada; o código de saída conta
        finally:
            loop.call_soon_threadsafe(fila.put_nowait, None)

    def drenar():
        # stderr lido à parte: se ninguém o lesse e ele enchesse o buffer do
        # pipe, o processo travaria esperando, e o stdout nunca terminaria.
        for linha in proc.stderr:
            erros.append(linha)
            del erros[:-20]

    threading.Thread(target=ler, daemon=True).start()
    threading.Thread(target=drenar, daemon=True).start()
    try:
        while (linha := await fila.get()) is not None:
            yield linha
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        if proc.returncode:
            log.info('%s saiu com %s: %s', comando[0], proc.returncode, ''.join(erros)[-500:])


async def claude(sistema: str, prompt: str) -> AsyncIterator[str]:
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8', dir=_pasta()) as f:
        f.write(sistema)
    try:
        comando = _comando(
            'claude', '-p',
            '--system-prompt-file', f.name,
            '--tools', '',
            # Só o MCP que o Solis passar (nenhum): os servidores MCP do Matheus
            # demorariam pra subir e não servem pra esta conversa.
            '--strict-mcp-config',
            '--no-session-persistence',
            '--output-format', 'stream-json', '--include-partial-messages', '--verbose',
        )
        async for linha in _linhas(comando, prompt):
            try:
                evento = json.loads(linha)
            except json.JSONDecodeError:
                continue
            tipo = evento.get('type')
            if tipo == 'stream_event':
                delta = evento.get('event', {}).get('delta', {})
                if delta.get('type') == 'text_delta' and delta.get('text'):
                    yield delta['text']
            elif tipo == 'rate_limit_event':
                # Não documentado: lido com cuidado. Status diferente de
                # "allowed" é cota acabando; o resetsAt diz quando volta.
                info = evento.get('rate_limit_info', {})
                if info.get('status') not in (None, 'allowed'):
                    pausar('claude', info.get('resetsAt'))
            elif tipo == 'result' and evento.get('is_error'):
                raise CerebroFalhou(str(evento.get('result', ''))[:200])
    finally:
        Path(f.name).unlink(missing_ok=True)


async def codex(sistema: str, prompt: str) -> AsyncIterator[str]:
    # O exec não documenta prompt de sistema: as instruções vão no começo do
    # próprio prompt. O texto chega de uma vez, sem pedaços — o Codex não manda
    # deltas; vale a última agent_message do turno.
    comando = _comando('codex', 'exec', '--json', '--skip-git-repo-check', '--sandbox', 'read-only', '-')
    ultima = None
    async for linha in _linhas(comando, f'{sistema}\n\n{prompt}'):
        try:
            evento = json.loads(linha)
        except json.JSONDecodeError:
            continue
        tipo = evento.get('type')
        item = evento.get('item', {})
        if tipo == 'item.completed' and item.get('type') == 'agent_message':
            ultima = item.get('text')
        elif tipo in ('turn.failed', 'error'):
            raise CerebroFalhou(json.dumps(evento)[:200])
    if ultima:
        yield ultima


EXECUTORES = {'claude': claude, 'codex': codex}


async def abrir(nome: str, sistema: str, prompt: str) -> AsyncIterator[str]:
    """Começa a resposta e só devolve depois da primeira palavra.

    É aqui que a falha aparece — CLI sem login, cota acabada, erro — enquanto
    ainda dá pra tentar o próximo cérebro. Depois que o texto começa a ir pra
    tela, não dá mais pra trocar de quem responde."""
    fluxo = EXECUTORES[nome](sistema, prompt)
    try:
        primeiro = await asyncio.wait_for(anext(fluxo), PRIMEIRO_PEDACO_S)
    except StopAsyncIteration:
        await fluxo.aclose()
        pausar(nome)
        raise CerebroFalhou(f'{nome} não respondeu nada')
    except (CerebroFalhou, OSError, asyncio.TimeoutError) as e:
        await fluxo.aclose()
        pausar(nome)
        raise CerebroFalhou(f'{nome}: {e}') from e

    async def resto():
        yield primeiro
        try:
            async for pedaco in fluxo:
                yield pedaco
        except CerebroFalhou:
            pass  # corte no meio: fica o que chegou, como no modelo local
    return resto()
