"""O navegador do Claude (docs/PARIDADE.md): abrir, ler, clicar e preencher
páginas, como o Claude in Chrome.

É o servidor MCP de navegador da Microsoft (@playwright/mcp, o que o Claude Code
usa), num processo só do Solis, pelo HTTP: cada resposta abre e fecha o CLI do
Claude, e o navegador precisa ficar aberto entre uma e outra, com as abas. Usa
o Chrome ou o Edge que já estão no PC (o Matheus escolhe em Configurações →
Navegador), numa janela que ele vê, com um perfil do Solis separado do de
sempre: os logins feitos nela ficam guardados ali.

O que pede o Matheus: clicar, escrever, preencher, apertar tecla, enviar
arquivo, rodar script na página (o cartão diz o quê e em qual site). Abrir e
ler página é livre, como o WebFetch. "Sempre neste site" libera as ações num
site enquanto o servidor está de pé."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from . import banco

log = logging.getLogger('solis.navegador')

SERVIDOR = 'navegador'           # mcp__navegador__browser_click
PREFIXO = f'mcp__{SERVIDOR}__'
SUBIR_MAX_S = 15.0

# Os navegadores do PC que o Playwright dirige sem baixar nada: o canal dele
# (--browser) → o nome e onde o Windows instala.
NAVEGADORES = {
    'chrome': ('Google Chrome', [r'Google\Chrome\Application\chrome.exe']),
    'msedge': ('Microsoft Edge', [r'Microsoft\Edge\Application\msedge.exe']),
}
DESLIGADO = 'desligado'

# Ler e ir pra uma página: livres. O resto age na página e pede cartão.
LIVRES = {'browser_snapshot', 'browser_find', 'browser_take_screenshot', 'browser_console_messages',
          'browser_network_requests', 'browser_network_request', 'browser_navigate', 'browser_navigate_back',
          'browser_wait_for', 'browser_tabs', 'browser_resize', 'browser_close', 'browser_hover',
          'browser_emulate_media'}
PEDEM = {'browser_click', 'browser_type', 'browser_fill_form', 'browser_select_option', 'browser_press_key',
         'browser_drag', 'browser_drop', 'browser_file_upload', 'browser_evaluate', 'browser_handle_dialog'}
# Roda código no processo do servidor (o próprio pacote chama de "unsafe"): fora.
PROIBIDAS = ['mcp__navegador__browser_run_code_unsafe']


def _programas() -> list[Path]:
    return [Path(os.environ[v]) for v in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA') if os.environ.get(v)]


def instalados() -> list[str]:
    """Os navegadores que estão no PC, na ordem de NAVEGADORES (Chrome primeiro:
    é o que a maioria usa)."""
    return [canal for canal, (_, caminhos) in NAVEGADORES.items()
            if any((base / c).is_file() for base in _programas() for c in caminhos)]


def escolhido() -> str | None:
    """O canal do navegador que o Claude usa, ou None (desligado, ou nenhum no PC)."""
    valor = banco.ajuste('navegador')
    if valor == DESLIGADO:
        return None
    tem = instalados()
    if valor in tem:
        return valor
    return tem[0] if tem else None


def estado() -> dict:
    tem = instalados()
    return {'escolhido': escolhido(), 'desligado': banco.ajuste('navegador') == DESLIGADO,
            'instalados': [{'canal': c, 'nome': NAVEGADORES[c][0]} for c in tem],
            'pronto': _cli().is_file(), 'aberto': _vivo()}


def escolher(valor: str) -> dict:
    """Muda o navegador (ou desliga). O servidor aberto com o outro fecha: a
    próxima resposta abre o novo."""
    if valor != DESLIGADO and valor not in instalados():
        raise ValueError('navegador')
    if valor != banco.ajuste('navegador'):
        banco.guardar_ajuste('navegador', valor)
        parar()
    return estado()


# — o servidor ————————————————————————————————————————————————————————————————
def _cli() -> Path:
    """O @playwright/mcp do package.json (npm install na raiz do repositório)."""
    return Path(__file__).resolve().parents[2] / 'node_modules' / '@playwright' / 'mcp' / 'cli.js'


def _dados() -> Path:
    return banco.caminho_padrao().parent / 'navegador'


def perfil(canal: str) -> Path:
    """O perfil do Solis nesse navegador: logins e abas guardados aqui, longe do de sempre."""
    return _dados() / canal


def pasta_saida() -> Path:
    """Onde o servidor deixa o que tira da página (a árvore da página, prints).
    O Claude lê dali sem cartão (agente._dentro)."""
    return _dados() / 'saida'


_trava = threading.Lock()
_processo: subprocess.Popen | None = None
_canal: str | None = None
_porta: int | None = None


def _vivo() -> bool:
    return _processo is not None and _processo.poll() is None


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _aceita(porta: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', porta)) == 0


def comando(canal: str, porta: int) -> list[str]:
    return ['node', str(_cli()), '--port', str(porta), '--host', '127.0.0.1', '--browser', canal,
            '--user-data-dir', str(perfil(canal)), '--output-dir', str(pasta_saida()),
            # Todas as conversas no mesmo navegador (um perfil só abre uma vez).
            '--shared-browser-context', '--viewport-size', '1280x800']


def servidor() -> dict | None:
    """O servidor pro Claude (mcp_servers do SDK), subindo se precisar; None se
    o navegador está desligado ou não dá pra subir (o Claude segue sem ele)."""
    global _processo, _canal, _porta
    canal = escolhido()
    if canal is None or not _cli().is_file():
        return None
    with _trava:
        if not (_vivo() and _canal == canal):
            _parar()
            porta = _porta_livre()
            pasta_saida().mkdir(parents=True, exist_ok=True)
            perfil(canal).mkdir(parents=True, exist_ok=True)
            try:
                _processo = subprocess.Popen(
                    comando(canal, porta), cwd=str(pasta_saida()), stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError:
                log.exception('o navegador não subiu')
                return None
            _canal, _porta = canal, porta
            fim = time.monotonic() + SUBIR_MAX_S
            while not _aceita(porta):
                if _processo.poll() is not None or time.monotonic() > fim:
                    log.warning('o servidor do navegador não respondeu (saiu com %s)', _processo.poll())
                    _parar()
                    return None
                time.sleep(0.1)
            log.info('navegador: %s na porta %s', canal, porta)
        return {'type': 'http', 'url': f'http://127.0.0.1:{_porta}/mcp'}


class NavegadorFalhou(Exception):
    pass


class _Dono:
    """Uma conexão do próprio Solis com o servidor, aberta o tempo todo. O
    servidor fecha o navegador quando o último cliente sai — e cada resposta do
    Claude é um cliente que sai no fim. Com o dono conectado (e tendo usado o
    navegador uma vez: o servidor só conta quem usou), as abas ficam. É também
    por ele que o botão "Abrir o navegador" abre a janela."""

    def __init__(self, url: str):
        self.url = url
        self.laco: asyncio.AbstractEventLoop | None = None
        self.sessao = None
        self.fim: asyncio.Event | None = None
        self.pronto = threading.Event()
        self.thread = threading.Thread(target=lambda: asyncio.run(self._viver()), daemon=True,
                                       name='solis-navegador')
        self.thread.start()

    async def _viver(self) -> None:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        self.laco, self.fim = asyncio.get_running_loop(), asyncio.Event()
        try:
            async with streamable_http_client(self.url) as (leitura, escrita, *_):
                async with ClientSession(leitura, escrita) as sessao:
                    await sessao.initialize()
                    self.sessao = sessao
                    self.pronto.set()
                    await self.fim.wait()
        except Exception:  # noqa: BLE001 — o servidor caiu: o próximo uso cria outro dono
            log.warning('a conexão do Solis com o navegador caiu', exc_info=True)
        finally:
            self.sessao = None
            self.pronto.set()

    def vivo(self) -> bool:
        return self.thread.is_alive() and (not self.pronto.is_set() or self.sessao is not None)

    def chamar(self, ferramenta: str, argumentos: dict, espera: float = 90.0) -> str:
        if not self.pronto.wait(SUBIR_MAX_S) or self.sessao is None or self.laco is None:
            raise NavegadorFalhou('sem conexão com o navegador')
        r = asyncio.run_coroutine_threadsafe(self.sessao.call_tool(ferramenta, argumentos), self.laco).result(espera)
        texto = '\n'.join(getattr(c, 'text', '') for c in r.content)
        if getattr(r, 'is_error', None) or getattr(r, 'isError', None):
            raise NavegadorFalhou(texto[:300])
        return texto

    def fechar(self) -> None:
        if self.laco is not None and self.fim is not None:
            with contextlib.suppress(RuntimeError):
                self.laco.call_soon_threadsafe(self.fim.set)
        self.thread.join(5)


_dono: _Dono | None = None


def _garantir_dono() -> _Dono:
    global _dono
    if _dono is None or not _dono.vivo() or _dono.url != f'http://127.0.0.1:{_porta}/mcp':
        if _dono is not None:
            _dono.fechar()
        _dono = _Dono(f'http://127.0.0.1:{_porta}/mcp')
    return _dono


def segurar() -> None:
    """O Claude acabou de usar o navegador: o dono se conecta (sem esperar), pra
    janela não fechar quando a resposta acabar."""
    def conectar():
        with _trava:
            if not _vivo():
                return
            dono = _garantir_dono()
        with contextlib.suppress(Exception):
            dono.chamar('browser_tabs', {'action': 'list'})
    threading.Thread(target=conectar, daemon=True).start()


def abrir(url: str = 'https://www.google.com') -> None:
    """Abre a janela do navegador do Solis (pra o Matheus entrar nas contas
    dele, por exemplo). Se ele tinha fechado a janela, abre de novo."""
    global _dono
    if servidor() is None:
        raise NavegadorFalhou('navegador desligado')
    for tentativa in range(2):
        with _trava:
            dono = _garantir_dono()
        try:
            dono.chamar('browser_navigate', {'url': url})
            return
        except Exception as e:  # noqa: BLE001 — a janela fechada deixa o dono sem página: outro dono
            log.info('abrir o navegador: %s', e)
            with _trava:
                dono.fechar()
                if _dono is dono:
                    _dono = None
            if tentativa:
                raise NavegadorFalhou(str(e)[:300]) from e


def _parar() -> None:
    global _processo, _canal, _porta, _dono
    if _dono is not None:
        _dono.fechar()
        _dono = None
    if _processo is not None and _processo.poll() is None:
        # O node fecha o navegador junto (o processo filho dele).
        _processo.terminate()
        try:
            _processo.wait(5)
        except subprocess.TimeoutExpired:
            _processo.kill()
    _processo, _canal, _porta = None, None, None


def parar() -> None:
    with _trava:
        _parar()


# — o cartão e as etapas ——————————————————————————————————————————————————————
def acao(nome: str) -> str | None:
    """'browser_click' de mcp__navegador__browser_click; None se não é do navegador."""
    return nome[len(PREFIXO):] if nome.startswith(PREFIXO) else None


def site(url: str | None) -> str:
    """'mercadolivre.com.br' de https://www.mercadolivre.com.br/ofertas."""
    if not url:
        return ''
    host = urlparse(url).hostname or ''
    return host.removeprefix('www.')


def pagina_do_resultado(texto: str) -> str | None:
    """A página em que o navegador está, do que a ferramenta devolveu ("- Page URL: ...")."""
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha.startswith('- Page URL:'):
            return linha.removeprefix('- Page URL:').strip() or None
    return None


def _elemento(entrada: dict, chave: str = 'element') -> str:
    return str(entrada.get(chave) or 'um elemento da página').strip()


def resumo(nome: str, entrada: dict) -> str:
    """A frase do cartão, sem o site ("Clicar em botão Enviar")."""
    a = acao(nome) or nome
    if a == 'browser_click':
        return f'{"Clicar duas vezes" if entrada.get("doubleClick") else "Clicar"} em {_elemento(entrada)}'
    if a == 'browser_type':
        return f'Escrever em {_elemento(entrada)}' + (' e enviar' if entrada.get('submit') else '')
    if a == 'browser_fill_form':
        n = len(entrada.get('fields') or [])
        return f'Preencher {n} campo{"s" if n != 1 else ""} do formulário'
    if a == 'browser_select_option':
        valores = ', '.join(str(v) for v in entrada.get('values') or [])
        return f'Escolher {valores} em {_elemento(entrada)}'
    if a == 'browser_press_key':
        return f'Apertar a tecla {entrada.get("key", "")}'
    if a == 'browser_drag':
        return f'Arrastar {_elemento(entrada, "startElement")} até {_elemento(entrada, "endElement")}'
    if a in ('browser_drop', 'browser_file_upload'):
        n = len(entrada.get('paths') or [])
        return f'Enviar {n} arquivo{"s" if n != 1 else ""} pra página' if n else 'Cancelar o envio de arquivo'
    if a == 'browser_evaluate':
        return 'Rodar um script na página'
    if a == 'browser_handle_dialog':
        return 'Aceitar o aviso da página' if entrada.get('accept') else 'Recusar o aviso da página'
    return f'Usar o navegador: {a}'


def detalhe(nome: str, entrada: dict) -> str:
    """O que vai, inteiro, embaixo do cartão: o texto a escrever, os campos, o script."""
    a = acao(nome)
    if a == 'browser_type':
        return str(entrada.get('text') or '')
    if a == 'browser_fill_form':
        return '\n'.join(f'{c.get("name", "campo")}: {c.get("value", "")}' for c in entrada.get('fields') or [])
    if a in ('browser_drop', 'browser_file_upload'):
        return '\n'.join(str(p) for p in entrada.get('paths') or [])
    if a == 'browser_evaluate':
        return str(entrada.get('function') or '')
    if a == 'browser_handle_dialog' and entrada.get('promptText'):
        return str(entrada['promptText'])
    return ''


FEITO = {'Clicar': 'Cliquei', 'Escrever': 'Escrevi', 'Preencher': 'Preenchi', 'Escolher': 'Escolhi',
         'Apertar': 'Apertei', 'Arrastar': 'Arrastei', 'Enviar': 'Enviei', 'Cancelar': 'Cancelei',
         'Rodar': 'Rodei', 'Aceitar': 'Aceitei', 'Recusar': 'Recusei'}


def alvo(nome: str, entrada: dict, pagina: str | None) -> str:
    """O que a etapa mostra ao lado do nome: a página aberta, o elemento clicado."""
    a = acao(nome)
    if a in ('browser_navigate',):
        return str(entrada.get('url') or '')
    if a == 'browser_tabs' and entrada.get('url'):
        return str(entrada['url'])
    if a in PEDEM:
        # No passado, como as outras etapas: "Cliquei em botão Enviar".
        primeira, _, resto = resumo(nome, entrada).partition(' ')
        return f'{FEITO.get(primeira, primeira)} {resto}'.strip()
    if a == 'browser_find':
        return str(entrada.get('text') or entrada.get('regex') or '')
    return site(pagina)
