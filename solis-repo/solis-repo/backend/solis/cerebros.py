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
- Codex: integradas pela documentação (`exec --json`, `--sandbox read-only`,
  `--skip-git-repo-check`, prompt pela entrada padrão) e conferidas rodando o
  CLI no notebook em 1º/11/2026 (resposta pelo Solis, tempos medidos).
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
from .etapas import MUDA

log = logging.getLogger('solis.cerebros')

NOMES = {
    'local': 'Modelo local',
    'claude': 'Claude',
    'codex': 'Codex',
    # Por API, no plano grátis (solis/apis.py).
    'groq': 'Groq',
    'gemini': 'Gemini',
    'mistral': 'Mistral',
    'openrouter': 'OpenRouter',
}
CLIS = ('claude', 'codex')
# O Claude pelo Agent SDK, com ferramentas (agente.py). 0 volta ao CLI só de conversa.
USAR_AGENTE = __import__('os').environ.get('SOLIS_CLAUDE_AGENTE', '1') != '0'

# Quanto esperar o CLI dar sinal de vida. Não há um prazo pra primeira palavra,
# e sim dois, porque as duas demoras têm causas diferentes (medido no notebook,
# 1º/11/2026, ver docs/ESCOPO.md):
#
# - Subir: do processo à primeira linha. Medido de 0,35 a 1,2 s, e 8,7 s no
#   Codex frio (ele sobe os servidores MCP antes de escrever qualquer coisa). É
#   aqui que um CLI trava — o MCP node_repl do Codex aceita até 120 s pra subir,
#   uma atualização no primeiro uso, um pedido de login. 20 s cobrem o Codex
#   frio com folga e cortam o travado: antes, um cérebro travado custava 90 s
#   até cair pro próximo.
# - Silêncio: o maior intervalo entre duas linhas depois disso. O Claude escreve
#   o tempo todo, inclusive pensando (medido: no máximo 3,9 s calado). O Codex
#   não manda pedaços: fica calado enquanto gera e entrega a resposta inteira
#   (8,5 s pra 500 palavras) — por isso o limite dele é maior.
PRIMEIRA_LINHA_S = 20
SILENCIO_S = {'claude': 20, 'codex': 60}

# Cérebro que falhou (cota, login, fora do ar) fica de lado por um tempo, pra o
# Solis não pagar a espera do erro em toda mensagem. O Claude diz quando a cota
# renova; o Codex não documenta isso, então vale o padrão.
PAUSA_PADRAO_S = 30 * 60
_fora_ate: dict[str, float] = {}
_motivo_pausa: dict[str, str] = {}


class CerebroFalhou(Exception):
    """Não saiu nenhuma palavra: CLI ausente, sem login, cota esgotada ou erro."""


def instalado(nome: str) -> bool:
    """CLI: o executável existe. API: há uma chave guardada."""
    if nome in CLIS:
        return shutil.which(nome) is not None
    from . import apis  # aqui dentro: apis importa este módulo
    return apis.tem_chave(nome)


def disponivel(nome: str) -> bool:
    return instalado(nome) and time.time() >= _fora_ate.get(nome, 0)


def pausar(nome: str, ate: float | None = None, motivo: str = '') -> None:
    _fora_ate[nome] = ate or time.time() + PAUSA_PADRAO_S
    _motivo_pausa[nome] = motivo


def pausa(nome: str) -> dict | None:
    """Até quando (epoch, em s) e por quê o cérebro está de lado — a tela de
    Configurações mostra, pra que ele não pareça sumido sem razão."""
    ate = _fora_ate.get(nome, 0)
    if time.time() >= ate:
        return None
    return {'ate': ate, 'motivo': _motivo_pausa.get(nome, '')}


def retomar(nome: str) -> None:
    """O Matheus resolveu (renovou a cota, fez login) e não quer esperar a pausa."""
    _fora_ate.pop(nome, None)
    _motivo_pausa.pop(nome, None)


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


async def _linhas(comando: list[str], entrada: str, etapas=MUDA, cerebro: str = '') -> AsyncIterator[str]:
    """As linhas da saída do processo, conforme saem.

    Marca duas etapas, porque é entre elas que o CLI gasta o tempo de subir:
    `processo` (o processo existe) e `primeira_linha` (ele já escreveu algo).
    CLI que não escreve a primeira linha em PRIMEIRA_LINHA_S, ou fica calado
    mais que o SILENCIO_S dele, é dado como travado: o processo é morto e a
    falha sobe — antes da primeira palavra, o próximo cérebro tenta.

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
    etapas.marcar('processo', cerebro=cerebro)

    erros: list[str] = []

    def entregar(linha: str | None) -> None:
        try:
            loop.call_soon_threadsafe(fila.put_nowait, linha)
        except RuntimeError:
            pass  # o loop já fechou: ninguém mais espera estas linhas

    def ler():
        try:
            proc.stdin.write(entrada)
            proc.stdin.close()
            for linha in proc.stdout:
                entregar(linha)
        except OSError:
            pass  # o processo morreu antes de ler a entrada; o código de saída conta
        finally:
            entregar(None)

    def drenar():
        # stderr lido à parte: se ninguém o lesse e ele enchesse o buffer do
        # pipe, o processo travaria esperando, e o stdout nunca terminaria.
        for linha in proc.stderr:
            erros.append(linha)
            del erros[:-20]

    threading.Thread(target=ler, daemon=True).start()
    threading.Thread(target=drenar, daemon=True).start()
    try:
        primeira = True
        while True:
            limite = PRIMEIRA_LINHA_S if primeira else SILENCIO_S.get(cerebro, max(SILENCIO_S.values()))
            try:
                linha = await asyncio.wait_for(fila.get(), limite)
            except asyncio.TimeoutError:
                raise CerebroFalhou(
                    f'não escreveu nada em {limite} s' if primeira else f'ficou {limite} s calado'
                ) from None
            if linha is None:
                break
            if primeira:
                etapas.marcar('primeira_linha', cerebro=cerebro)
                primeira = False
            yield linha
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        if proc.returncode:
            log.info('%s saiu com %s: %s', comando[0], proc.returncode, ''.join(erros)[-500:])


async def claude(sistema: str, prompt: str, etapas=MUDA, sessao: dict | None = None) -> AsyncIterator[str]:
    """O Claude com ferramentas, pelo Claude Agent SDK (agente.py) — o primeiro
    marco da VISAO. Sem o SDK instalado (ou com SOLIS_CLAUDE_AGENTE=0), o CLI
    só de conversa, como antes."""
    try:
        if not USAR_AGENTE:
            raise ImportError('desligado')
        from . import agente
    except ImportError:
        async for pedaco in claude_sem_ferramentas(sistema, prompt, etapas):
            yield pedaco
        return
    # `sessao` (roteador.sessao_claude): a conversa, a sessão dela e o pedido
    # curto que a continua. Retomar que falha antes da primeira palavra (a
    # sessão sumiu do disco, por exemplo) vira uma sessão nova com o pedido
    # inteiro — o histórico vai no texto, como antes.
    guardar = None
    if sessao:
        def guardar(id_: str, conversa: int = sessao['conversa']) -> None:
            banco.guardar_sessao_claude(conversa, id_)
    if sessao and sessao.get('id') and sessao.get('prompt'):
        saiu = False
        try:
            async for pedaco in agente.claude(sistema, sessao['prompt'], etapas, retomar=sessao['id'], ao_sessao=guardar):
                saiu = True
                yield pedaco
            return
        except agente.AgenteFalhou as e:
            if saiu:
                raise CerebroFalhou(str(e)) from e
            log.warning('a sessão %s do Claude não continuou (%s); começando outra', sessao['id'], e)
            banco.esquecer_sessao_claude(sessao['conversa'])
    try:
        async for pedaco in agente.claude(sistema, prompt, etapas, ao_sessao=guardar):
            yield pedaco
    except agente.AgenteFalhou as e:
        raise CerebroFalhou(str(e)) from e


async def claude_sem_ferramentas(sistema: str, prompt: str, etapas=MUDA) -> AsyncIterator[str]:
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8', dir=_pasta()) as f:
        f.write(sistema)
    linhas = None
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
        pensou = False
        linhas = _linhas(comando, prompt, etapas, 'claude')
        async for linha in linhas:
            try:
                evento = json.loads(linha)
            except json.JSONDecodeError:
                continue
            tipo = evento.get('type')
            if tipo == 'stream_event':
                if evento.get('event', {}).get('type') == 'message_stop':
                    # Fim da resposta. Sem ferramentas há uma mensagem só, e o
                    # CLI ainda leva de 2 a 3,9 s pra mandar o `result` e sair
                    # (medido) — tempo que a tela passava esperando à toa.
                    return
                delta = evento.get('event', {}).get('delta', {})
                if delta.get('type') == 'text_delta' and delta.get('text'):
                    yield delta['text']
                elif delta.get('type') == 'thinking_delta' and not pensou:
                    # O raciocínio não vai pra tela, só o fato de que está pensando.
                    etapas.marcar('pensando', cerebro='claude')
                    pensou = True
            elif tipo == 'rate_limit_event':
                # Não documentado: lido com cuidado. Status diferente de
                # "allowed" é cota acabando; o resetsAt diz quando volta.
                info = evento.get('rate_limit_info', {})
                if info.get('status') not in (None, 'allowed'):
                    pausar('claude', info.get('resetsAt'), 'a cota acabou')
            elif tipo == 'result' and evento.get('is_error'):
                raise CerebroFalhou(str(evento.get('result', ''))[:200])
    finally:
        # Fechar explicitamente: sair do laço no fim da mensagem deixaria o
        # _linhas aberto, e o processo só seria morto pelo coletor de lixo.
        if linhas is not None:
            await linhas.aclose()
        Path(f.name).unlink(missing_ok=True)


async def codex(sistema: str, prompt: str, etapas=MUDA) -> AsyncIterator[str]:
    # O exec não documenta prompt de sistema: as instruções vão no começo do
    # próprio prompt. O texto chega de uma vez, sem pedaços — o Codex não manda
    # deltas; vale a última agent_message do turno.
    comando = _comando('codex', 'exec', '--json', '--skip-git-repo-check', '--sandbox', 'read-only', '-')
    ultima = None
    async for linha in _linhas(comando, f'{sistema}\n\n{prompt}', etapas, 'codex'):
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


async def abrir(nome: str, sistema: str, prompt: str, etapas=MUDA, sessao: dict | None = None) -> AsyncIterator[str]:
    """Começa a resposta e só devolve depois da primeira palavra.

    É aqui que a falha aparece — CLI sem login, cota acabada, erro — enquanto
    ainda dá pra tentar o próximo cérebro. Depois que o texto começa a ir pra
    tela, não dá mais pra trocar de quem responde."""
    if nome in EXECUTORES:
        # Só o Claude tem sessão; os outros recebem o histórico no pedido.
        extra = {'sessao': sessao} if sessao and nome == 'claude' else {}
        fluxo = EXECUTORES[nome](sistema, prompt, etapas, **extra)
    else:
        from . import apis
        fluxo = apis.responder(nome, sistema, prompt, etapas)
    try:
        # Sem prazo aqui: quem decide que o CLI travou é o _linhas, pela
        # primeira linha e pelo silêncio — uma resposta longa que está saindo
        # não pode ser cortada por demorar.
        primeiro = await anext(fluxo)
    except StopAsyncIteration:
        await fluxo.aclose()
        pausar(nome, motivo='não respondeu nada')
        raise CerebroFalhou('não respondeu nada')
    except (CerebroFalhou, OSError) as e:
        await fluxo.aclose()
        # Quem já se pausou com a hora certa (a cota do Claude, o retry-after
        # de uma API) não tem a pausa trocada pelo padrão de 30 min.
        if pausa(nome) is None:
            pausar(nome, motivo=str(e) or type(e).__name__)
        raise CerebroFalhou(str(e) or type(e).__name__) from e
    etapas.marcar('primeira_palavra', cerebro=nome)

    async def resto():
        # Um corte no meio (o CLI calado depois de começar) sobe até a rota, que
        # guarda o que chegou e marca a resposta como cortada.
        yield primeiro
        async for pedaco in fluxo:
            yield pedaco
    return resto()
