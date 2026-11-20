"""Servidores MCP configuráveis (docs/PARIDADE.md): ferramentas de fora (um
servidor do Notion, do GitHub, um do Matheus) pro Claude e pro GPT do Solis.

Cada servidor diz pra quem vale, como as skills (o Matheus, 15/11/2026): pro
Claude, na configuração de usuário do Claude Code (~/.claude.json, que o Claude
do Solis já carrega: setting_sources "user"); pro GPT, na do Codex
(~/.codex/config.toml). Quem escreve são os próprios CLIs (`claude mcp
add-json/remove --scope user`, `codex mcp add/remove`): o Solis não edita os
arquivos deles à mão. Valem também no Claude Code e no Codex do terminal.

As ferramentas: o Solis conecta em cada servidor e lista o que ele oferece,
com o que só lê (a marca readOnlyHint do próprio servidor). No Claude, ler é
livre e o resto pede cartão (agente._decidir). No GPT, que roda sem ninguém pra
aprovar (codex exec), só as que leem são liberadas (`-c mcp_servers.X.tools.Y.
approval_mode="approve"`, testado no Codex 0.166 em 15/11/2026); as outras
falham e ele diz que não pôde.

As chaves (as variáveis de um servidor por comando) ficam no cofre do Solis,
não em texto aberto nos arquivos dos CLIs (o Matheus, 17/11/2026): lá vai o
lançador (lancar_mcp.py), que abre o cofre na hora de ligar o servidor.
Continua valendo no terminal, na mesma conta do Windows."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import banco, cofre
from .lancar_mcp import COFRE, NOSSAS

log = logging.getLogger('solis.servidores_mcp')

PARA = ('claude', 'codex')
NOSSOS = {'solis'}             # a memória do Solis (servidor_mcp.py): registrada pelo README, não pela tela
TESTE_MAX_S = 40.0
CACHE_S = 600
_NOME = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
_CHAVE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
LANCADOR = 'solis.lancar_mcp'
# Servidor por endereço com chave (20/11/2026): os cabeçalhos ficam no cofre; no
# Claude Code vai o `headersHelper` (este script, que abre o cofre ao conectar);
# no Codex, que só aceita a chave numa variável, a variável que o Solis põe ao
# chamar ele (`ambiente_do_codex`).
CABECALHOS = Path(__file__).resolve().parents[1] / 'cabecalhos_mcp.py'
_CABECALHO = re.compile(r'^[A-Za-z0-9-]{1,64}$')


class ServidorInvalido(Exception):
    pass


def _casa() -> Path:
    return Path.home()


def _cli(nome: str) -> list[str]:
    caminho = shutil.which(nome)
    if caminho is None:
        raise ServidorInvalido(f'o {"Claude Code" if nome == "claude" else "Codex"} não está instalado')
    return ['cmd', '/c', caminho] if caminho.lower().endswith(('.cmd', '.bat')) else [caminho]


def _rodar(cli: str, *args: str, timeout: float = 60) -> str:
    r = subprocess.run([*_cli(cli), *args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                       timeout=timeout, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0:
        raise ServidorInvalido(' '.join((r.stderr or r.stdout or 'falhou').split())[:300])
    return r.stdout


# — o cofre das variáveis ————————————————————————————————————————————————————
def _cofre() -> dict[str, dict[str, str]]:
    return dict(banco.ajuste(COFRE) or {})


def _guardar_variaveis(nome: str, env: dict[str, str]) -> None:
    c = _cofre()
    if env:
        c[nome] = {k: cofre.selar(v) for k, v in env.items()}
    elif c.pop(nome, None) is None:
        return
    banco.guardar_ajuste(COFRE, c)


def _do_cofre(nome: str) -> dict[str, str]:
    return {k: cofre.abrir(v) for k, v in (_cofre().get(nome) or {}).items()}


def _python() -> str:
    """O Python do Solis (o do .venv), o de console: o lançador conversa pela entrada e saída."""
    exe = Path(sys.executable)
    console = exe.with_name('python.exe')
    return str(console if exe.name.lower() == 'pythonw.exe' and console.exists() else exe)


def _lancado(nome: str, c: dict) -> dict:
    """Se a configuração é o lançador, o servidor de verdade: o comando dele e
    as variáveis do cofre (no lugar das do lançador)."""
    partes = c['comando']
    if len(partes) >= 5 and partes[1:3] == ['-m', LANCADOR] and partes[3] == nome:
        c = {**c, 'comando': partes[4:], 'env': _do_cofre(nome), 'cofre': True}
    return c


# — o que está configurado ————————————————————————————————————————————————————
def _do_claude() -> dict[str, dict]:
    """Os de usuário do Claude Code (~/.claude.json → mcpServers)."""
    try:
        dados = json.loads((_casa() / '.claude.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    saida = {}
    for nome, c in (dados.get('mcpServers') or {}).items():
        if c.get('url'):
            nosso = CABECALHOS.name in str(c.get('headersHelper') or '')
            saida[nome] = {'tipo': 'endereco', 'url': c['url'], 'comando': [],
                           'env': _do_cofre(nome) if nosso else {}, **({'cofre': True} if nosso else {})}
        else:
            saida[nome] = _lancado(nome, {'tipo': 'comando', 'url': '',
                                          'comando': [c.get('command', ''), *(c.get('args') or [])],
                                          'env': dict(c.get('env') or {})})
    return saida


def _interno_do_codex(t: dict) -> bool:
    """Os que o app do Codex instala pra ele mesmo (computer use, o app): do Codex, não do Matheus."""
    caminho = f'{t.get("command") or ""} {t.get("cwd") or ""}'.replace('/', '\\').lower()
    return '\\openai\\codex\\' in caminho or '\\.codex\\plugins\\' in caminho


def _do_codex() -> dict[str, dict]:
    try:
        lista = json.loads(_rodar('codex', 'mcp', 'list', '--json', timeout=30))
    except (ServidorInvalido, ValueError, OSError, subprocess.TimeoutExpired):
        return {}
    saida = {}
    for s in lista:
        t = s.get('transport') or {}
        if t.get('type') == 'stdio':
            saida[s['name']] = _lancado(s['name'], {
                'tipo': 'comando', 'url': '', 'comando': [t.get('command', ''), *(t.get('args') or [])],
                'env': dict(t.get('env') or {}), 'interno': _interno_do_codex(t), 'ligado': s.get('enabled', True)})
        else:
            nosso = t.get('bearer_token_env_var') == variavel_do_codex(s['name'])
            saida[s['name']] = {'tipo': 'endereco', 'url': t.get('url', ''), 'comando': [],
                                'env': _do_cofre(s['name']) if nosso else {}, **({'cofre': True} if nosso else {}),
                                'interno': False, 'ligado': s.get('enabled', True)}
    return saida


def _comando_legivel(partes: list[str]) -> str:
    return subprocess.list2cmdline([p for p in partes if p])


def listar() -> list[dict]:
    """`nome`, `tipo` (comando ou endereco), `comando` (a linha) ou `url`,
    `variaveis` (só os nomes), `no_cofre` (as variáveis estão no cofre do
    Solis), `para`, `origem` (seu, solis, codex), `editavel` e as
    `ferramentas` da última conferida."""
    claude, codex = _do_claude(), _do_codex()
    cache = _cache()
    saida = []
    for nome in sorted(set(claude) | set(codex), key=str.lower):
        c = claude.get(nome) or codex[nome]
        interno = bool((codex.get(nome) or {}).get('interno')) and nome not in claude
        origem = 'solis' if nome in NOSSOS else 'codex' if interno else 'seu'
        saida.append({
            'nome': nome, 'tipo': c['tipo'], 'comando': _comando_legivel(c['comando']), 'url': c['url'],
            'variaveis': sorted(c['env']), 'no_cofre': bool(c.get('cofre')), 'para': [p for p, l in (('claude', claude), ('codex', codex)) if nome in l],
            'origem': origem, 'editavel': origem == 'seu',
            'desligado_no_codex': nome in codex and not codex[nome].get('ligado', True),
            'ferramentas': cache.get(nome),
        })
    return sorted(saida, key=lambda s: ({'seu': 0, 'solis': 1, 'codex': 2}[s['origem']], s['nome'].lower()))


def ler(nome: str) -> dict | None:
    """Um dos seus inteiro, pra editar (com os valores das variáveis: é o PC dele)."""
    claude, codex = _do_claude(), _do_codex()
    c = claude.get(nome) or codex.get(nome)
    if c is None or nome in NOSSOS or (codex.get(nome) or {}).get('interno'):
        return None
    return {'nome': nome, 'tipo': c['tipo'], 'comando': _comando_legivel(c['comando']), 'url': c['url'],
            'variaveis': '\n'.join(f'{k}={v}' for k, v in c['env'].items()),
            'para': [p for p, l in (('claude', claude), ('codex', codex)) if nome in l]}


# — escrever ——————————————————————————————————————————————————————————————————
def _partes(linha: str) -> list[str]:
    """A linha de comando como o Windows divide (aspas pra caminho com espaço)."""
    partes, atual, aspas, tem = [], [], False, False
    for ch in linha.strip():
        if ch == '"':
            aspas, tem = not aspas, True
        elif ch.isspace() and not aspas:
            if atual or tem:
                partes.append(''.join(atual))
            atual, tem = [], False
        else:
            atual.append(ch)
    if aspas:
        raise ServidorInvalido('comando')
    if atual or tem:
        partes.append(''.join(atual))
    return partes


def _cabecalhos(texto: str) -> dict[str, str]:
    """Os cabeçalhos de um servidor por endereço, um por linha: `Nome=valor` ou
    `Nome: valor` (ex.: Authorization=Bearer sua-chave)."""
    saida = {}
    for linha in (texto or '').splitlines():
        if not linha.strip():
            continue
        separador = min((i for i in (linha.find('='), linha.find(':')) if i > 0), default=-1)
        nome, valor = linha[:separador].strip(), linha[separador + 1:].strip() if separador > 0 else ''
        if separador <= 0 or not _CABECALHO.match(nome) or not valor:
            raise ServidorInvalido('cabeçalhos')
        saida[nome] = valor
    return saida


def _so_bearer(cabecalhos: dict[str, str]) -> bool:
    """O Codex só aceita a chave como Authorization: Bearer, por variável."""
    return list(cabecalhos) == ['Authorization'] and cabecalhos['Authorization'].startswith('Bearer ')


def variavel_do_codex(nome: str) -> str:
    return 'SOLIS_MCP_' + re.sub(r'[^A-Z0-9]', '_', nome.upper()) + '_TOKEN'


def _ajudante_de_cabecalhos(nome: str) -> str:
    """A linha do headersHelper (o Claude Code roda num shell): o Python do Solis
    e o script que tira os cabeçalhos do cofre. Barras normais e aspas: valem
    no bash e no cmd."""
    return f'"{Path(_python()).as_posix()}" "{CABECALHOS.as_posix()}" {nome}'


def ambiente_do_codex() -> dict[str, str]:
    """As variáveis que o Codex precisa pra chave dos servidores por endereço
    (`bearer_token_env_var`): o token de cada um, do cofre, só na hora de chamar."""
    saida = {}
    for nome, valores in _cofre().items():
        cab = {k: cofre.abrir(v) for k, v in valores.items()}
        if _so_bearer(cab):
            saida[variavel_do_codex(nome)] = cab['Authorization'].removeprefix('Bearer ').strip()
    return saida


def _variaveis(texto: str) -> dict[str, str]:
    env = {}
    for linha in (texto or '').splitlines():
        if not linha.strip():
            continue
        chave, igual, valor = linha.strip().partition('=')
        if not igual or not _CHAVE.match(chave.strip()):
            raise ServidorInvalido('variáveis')
        env[chave.strip()] = valor.strip()
    return env


def _validar(nome: str, tipo: str, comando: str, url: str, variaveis: str, para: list[str]) -> tuple[list[str], dict]:
    if not _NOME.match(nome or '') or nome in NOSSOS:
        raise ServidorInvalido('nome')
    if tipo not in ('comando', 'endereco'):
        raise ServidorInvalido('tipo')
    if not para or any(p not in PARA for p in para):
        raise ServidorInvalido('pra quem')
    partes = _partes(comando) if tipo == 'comando' else []
    if tipo == 'comando' and not partes:
        raise ServidorInvalido('comando')
    if tipo == 'endereco' and not re.match(r'^https?://\S+$', url or ''):
        raise ServidorInvalido('endereço')
    env = _variaveis(variaveis) if tipo == 'comando' else _cabecalhos(variaveis)
    if tipo == 'endereco' and env and 'codex' in para and not _so_bearer(env):
        raise ServidorInvalido('no Codex, só a chave como Authorization=Bearer ...')
    return partes, env


def salvar(nome: str, tipo: str, comando: str, url: str, variaveis: str, para: list[str],
           antigo: str | None = None) -> dict:
    """Adiciona (ou muda, com `antigo`) um dos seus, pelos CLIs: tira o de antes
    de onde estava e põe em cada lugar de `para`."""
    partes, env = _validar(nome, tipo, comando, url, variaveis, para)
    existentes = {s['nome']: s for s in listar()}
    if antigo:
        if antigo not in existentes or not existentes[antigo]['editavel']:
            raise ServidorInvalido('esse servidor não existe mais')
    if nome in existentes and nome != antigo:
        raise ServidorInvalido('já existe um servidor com esse nome')
    if antigo:
        remover(antigo)
    # Com chave: as variáveis vão pro cofre, e nos CLIs fica o lançador (com só
    # o que ele precisa pra achar o Solis e o banco). Sem chave: o comando direto.
    cabecalhos = bool(env) and tipo == 'endereco'
    if env:
        _guardar_variaveis(nome, env)
    if env and tipo == 'comando':
        partes = [_python(), '-m', LANCADOR, nome, *partes]
        env = dict(zip(NOSSAS, (str(Path(__file__).resolve().parents[1]), str(banco.arquivo()))))
    if 'claude' in para:
        config = {'type': 'http', 'url': url} if tipo == 'endereco' else \
            {'type': 'stdio', 'command': partes[0], 'args': partes[1:], 'env': env}
        if cabecalhos:
            config['headersHelper'] = _ajudante_de_cabecalhos(nome)
        _rodar('claude', 'mcp', 'add-json', '--scope', 'user', nome, json.dumps(config, ensure_ascii=False))
    if 'codex' in para:
        if tipo == 'endereco':
            _rodar('codex', 'mcp', 'add', nome, '--url', url,
                   *(['--bearer-token-env-var', variavel_do_codex(nome)] if cabecalhos else []))
        else:
            _rodar('codex', 'mcp', 'add', nome, *[a for k, v in env.items() for a in ('--env', f'{k}={v}')],
                   '--', *partes)
    _esquecer(nome)
    if antigo and antigo != nome:
        _esquecer(antigo)
    return next(s for s in listar() if s['nome'] == nome)


def remover(nome: str) -> bool:
    s = next((x for x in listar() if x['nome'] == nome), None)
    if s is None or not s['editavel']:
        return False
    if 'claude' in s['para']:
        _rodar('claude', 'mcp', 'remove', '--scope', 'user', nome)
    if 'codex' in s['para']:
        _rodar('codex', 'mcp', 'remove', nome)
    _guardar_variaveis(nome, {})
    _esquecer(nome)
    return True


# — as ferramentas de cada um —————————————————————————————————————————————————
def _cache() -> dict:
    return dict(banco.ajuste('mcp_ferramentas') or {})


def _esquecer(nome: str) -> None:
    c = _cache()
    if c.pop(nome, None) is not None:
        banco.guardar_ajuste('mcp_ferramentas', c)


def _abrir(c: dict):
    if c['tipo'] == 'endereco':
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client
        # A chave do cofre nos cabeçalhos (Authorization, X-API-Key...).
        cliente = create_mcp_http_client(headers=c['env'] or None)

        async def recusou(resposta):
            # O cliente do MCP troca o erro HTTP (401, o 400 do GitHub com chave
            # errada...) por um genérico: o código e o motivo do servidor
            # ficam aqui pra tela dizer o que foi.
            if resposta.status_code >= 400 and 'recusa' not in c:
                await resposta.aread()
                c['recusa'] = (resposta.status_code, ' '.join(resposta.text.split())[:120])
        cliente.event_hooks = {**cliente.event_hooks, 'response': [*cliente.event_hooks.get('response', []), recusou]}
        return streamable_http_client(c['url'], http_client=cliente)
    from mcp.client.stdio import StdioServerParameters, stdio_client
    return stdio_client(StdioServerParameters(command=c['comando'][0], args=c['comando'][1:],
                                              env={**os.environ, **c['env']}))


async def _listar_ferramentas(c: dict) -> list[dict]:
    """As ferramentas do servidor, com a descrição e o esquema: os cérebros
    que não são o Claude usam as mesmas pelo corpo do Solis (corpo.py)."""
    from mcp import ClientSession
    async with _abrir(c) as (leitura, escrita, *_):
        async with ClientSession(leitura, escrita) as sessao:
            await sessao.initialize()
            r = await sessao.list_tools()
    return [{'nome': t.name, 'so_le': bool(t.annotations and t.annotations.read_only_hint
                                           and not t.annotations.destructive_hint),
             'descricao': (t.description or '')[:600], 'esquema': t.input_schema or {}} for t in r.tools]


# — pros outros cérebros (corpo.py) ———————————————————————————————————————————
CHAMAR_MAX_S = 60.0


def do_corpo() -> list[dict]:
    """Os servidores do Matheus que valem pros cérebros pelo corpo: os seus
    (não o da memória do Solis, que o corpo já tem), já conferidos (é a
    conferida que guarda as ferramentas). Da configuração do Claude, que é
    lida na hora; os só do Codex ficam de fora (ler a dele sobe o CLI)."""
    cache = _cache()
    saida = []
    for nome, c in sorted(_do_claude().items()):
        r = cache.get(nome) or {}
        if nome in NOSSOS or not _NOME.match(nome) or r.get('erro') or not r.get('lista'):
            continue
        if cofre.ILEGIVEL in c['env'].values():
            continue
        saida.append({'nome': nome, 'config': c, 'ferramentas': r['lista']})
    return saida


async def chamar(c: dict, ferramenta: str, argumentos: dict) -> tuple[str, bool]:
    """Roda uma ferramenta do servidor: (o texto que voltou, se deu certo).
    Abre e fecha a conexão a cada chamada, na mesma tarefa (o cliente MCP não
    deixa fechar em outra)."""
    from mcp import ClientSession

    async def rodar():
        async with _abrir(c) as (leitura, escrita, *_):
            async with ClientSession(leitura, escrita) as sessao:
                await sessao.initialize()
                return await sessao.call_tool(ferramenta, argumentos)
    try:
        r = await asyncio.wait_for(rodar(), CHAMAR_MAX_S)
    except Exception as e:  # noqa: BLE001 — o servidor caiu ou demorou: o modelo fica sabendo
        if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
            motivo = 'demorou demais pra responder'
        else:
            motivo = ' '.join(str(getattr(e, 'exceptions', [e])[0] if hasattr(e, 'exceptions') else e).split())[:200]
        return f'O servidor não respondeu: {motivo or "erro"}', False
    texto = '\n'.join(getattr(p, 'text', '') for p in r.content if getattr(p, 'text', None))
    erro = bool(getattr(r, 'is_error', None) or getattr(r, 'isError', None))
    return texto or ('(sem texto)' if not erro else 'deu erro'), not erro


def _motivo(e: BaseException, recusa: tuple[int, str] | None = None, com_chave: bool = False) -> str:
    """Por que o servidor não subiu, em uma linha pra tela: o erro de dentro dos
    grupos do anyio, a recusa da chave dita como recusa, e o motivo que o
    próprio servidor deu."""
    if recusa:
        status, texto = recusa
        if status in (401, 403):
            return (f'o servidor recusou a chave ({status}): confira os cabeçalhos' if com_chave else
                    f'o servidor pede uma chave ({status}): ponha nos cabeçalhos')
        return f'o servidor respondeu {status}' + (f': {texto}' if texto else '')
    while getattr(e, 'exceptions', None):
        e = e.exceptions[0]
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
        return 'demorou demais pra responder'
    # Erro sem texto (o endereço que não existe): o nome dele, pra não ficar
    # "Não respondeu: não respondeu" na tela.
    return ' '.join(str(e).split())[:200] or f'não conectou ({type(e).__name__})'


async def conferir(nome: str) -> dict:
    """Conecta no servidor e lista as ferramentas: {total, so_leem, lista, erro, quando}."""
    claude, codex = _do_claude(), await asyncio.to_thread(_do_codex)
    c = claude.get(nome) or codex.get(nome)
    if c is None:
        raise ServidorInvalido('esse servidor não existe')
    try:
        if cofre.ILEGIVEL in c['env'].values():
            raise ServidorInvalido('as chaves dele não abrem nesta conta do Windows')
        lista = await asyncio.wait_for(_listar_ferramentas(c), TESTE_MAX_S)
        r = {'total': len(lista), 'so_leem': sum(t['so_le'] for t in lista), 'lista': lista, 'erro': None}
    except Exception as e:  # noqa: BLE001 — o servidor não subiu: a tela diz
        motivo = _motivo(e, c.get('recusa'), bool(c['env']))
        r = {'total': 0, 'so_leem': 0, 'lista': [], 'erro': motivo or 'não respondeu'}
    r['quando'] = time.time()
    # Só servidor que está no Codex ganha o -c: um -c de servidor que ele não
    # conhece criaria uma entrada sem comando e quebraria a configuração dele.
    r['no_codex'] = nome in codex
    cache = _cache()
    cache[nome] = r
    banco.guardar_ajuste('mcp_ferramentas', cache)
    return r


def liberadas_no_codex() -> list[str]:
    """Os `-c` do `codex exec` do Solis: as ferramentas que só leem, dos
    servidores do Codex, rodam sem aprovação (o resto falha: não há quem aprove)."""
    args = []
    for nome, r in sorted(_cache().items()):
        if not _NOME.match(nome) or not r.get('no_codex'):
            continue
        for t in r.get('lista') or []:
            if t.get('so_le') and re.match(r'^[A-Za-z0-9_-]+$', t.get('nome', '')):
                # Sem aspas: o codex.cmd passa pelo cmd.exe, e o Codex aceita o
                # valor cru quando não é TOML válido.
                args += ['-c', f'mcp_servers.{nome}.tools.{t["nome"]}.approval_mode=approve']
    return args
