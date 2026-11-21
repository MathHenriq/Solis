"""Login (OAuth) nos servidores MCP por endereço (docs/PARIDADE.md, 20/11/2026).

Muitos servidores na internet (o do GitHub, o do Notion, o do Linear...) não
usam uma chave fixa: pedem que a pessoa entre pela página deles. O Solis faz
esse login uma vez, com o Matheus, e guarda o token no cofre (DPAPI):

1. Entrar (`comecar`): a biblioteca `mcp` descobre o servidor de login, cadastra
   o Solis como cliente e monta o endereço da página de login (com PKCE). O
   Matheus entra no navegador, e o serviço volta pro próprio servidor do Solis
   (`/mcp/oauth/volta`), que entrega o código (`voltou`). O token vai pro cofre.
2. Usar (`token`): na hora de conectar, o Solis devolve o token, renovado
   sozinho quando vence (o refresh_token) — sem abrir janela no meio de uma
   resposta. Todos usam o mesmo login: os cérebros de API pelo corpo, o Claude
   Code pelo `headersHelper` (lancar_mcp.cabecalhos) e o Codex pela variável
   (servidores_mcp.ambiente_do_codex). O token nunca vai pros arquivos dos CLIs.

Se a renovação falha (o login venceu de vez), `token` levanta PrecisaEntrar e
a tela mostra "Entrar" de novo.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from urllib.parse import parse_qs, urlsplit

import httpx

from . import banco, cofre

log = logging.getLogger('solis.mcp_oauth')

COFRE = 'mcp_oauth'
VOLTA = '/mcp/oauth/volta'
ENTRAR_MAX_S = 600.0     # quanto tempo o login no navegador pode levar
RENOVAR_ANTES_S = 60     # renova o token um minuto antes de vencer


class PrecisaEntrar(Exception):
    """O servidor pede login e o Solis não tem um token que sirva."""


# — o cofre ———————————————————————————————————————————————————————————————————
def _todos() -> dict[str, str]:
    return dict(banco.ajuste(COFRE) or {})


def _ler(nome: str) -> dict | None:
    selado = _todos().get(nome)
    if not selado:
        return None
    aberto = cofre.abrir(selado)
    if aberto == cofre.ILEGIVEL:
        return None
    try:
        return json.loads(aberto)
    except ValueError:
        return None


def _guardar(nome: str, dados: dict | None) -> None:
    todos = _todos()
    if dados is None:
        if todos.pop(nome, None) is None:
            return
    else:
        todos[nome] = cofre.selar(json.dumps(dados))
    banco.guardar_ajuste(COFRE, todos)


def tem(nome: str) -> bool:
    return nome in _todos()


def nomes() -> list[str]:
    return sorted(_todos())


def esquecer(nome: str) -> None:
    _guardar(nome, None)


def tirar(nome: str) -> dict | None:
    """Tira o login de um servidor (pra pôr de volta com `por`, ao salvar de novo)."""
    dados = _ler(nome)
    esquecer(nome)
    return dados


def por(nome: str, dados: dict | None) -> None:
    if dados:
        _guardar(nome, dados)


def do_endereco(dados: dict | None, url: str) -> bool:
    """O login guardado é deste endereço (mudou o endereço, o token não serve mais)."""
    return bool(dados) and dados.get('url') == url


# — usar: o token, renovado quando vence ——————————————————————————————————————
def token(nome: str, transporte: httpx.BaseTransport | None = None) -> str | None:
    """O access_token do servidor (None se ele não usa login). Renova sozinho
    pelo refresh_token; PrecisaEntrar se não deu. Síncrono (o headersHelper e o
    ambiente do Codex não estão num laço); num laço, numa thread."""
    dados = _ler(nome)
    if dados is None:
        if tem(nome):
            raise PrecisaEntrar(f'o login do servidor "{nome}" não abre nesta conta do Windows')
        return None
    vence = dados.get('vence')
    if vence is None or time.time() < vence - RENOVAR_ANTES_S:
        return dados['tokens']['access_token']
    if not dados['tokens'].get('refresh_token') or not dados.get('token_endpoint'):
        raise PrecisaEntrar(f'o login do servidor "{nome}" venceu: entre de novo')
    novo = _renovar(dados, transporte)
    dados['tokens'] = {**dados['tokens'], **novo}
    dados['vence'] = time.time() + novo['expires_in'] if novo.get('expires_in') else None
    _guardar(nome, dados)
    return dados['tokens']['access_token']


def _renovar(dados: dict, transporte) -> dict:
    cliente = dados.get('cliente') or {}
    corpo = {'grant_type': 'refresh_token', 'refresh_token': dados['tokens']['refresh_token'],
             'client_id': cliente.get('client_id', '')}
    if dados.get('resource'):
        corpo['resource'] = dados['resource']
    auth = None
    segredo = cliente.get('client_secret')
    if segredo:
        if cliente.get('token_endpoint_auth_method') == 'client_secret_basic':
            auth = httpx.BasicAuth(cliente['client_id'], segredo)
        else:
            corpo['client_secret'] = segredo
    try:
        with httpx.Client(timeout=30, transport=transporte) as c:
            r = c.post(dados['token_endpoint'], data=corpo, auth=auth)
    except httpx.HTTPError as e:
        raise PrecisaEntrar(f'não consegui renovar o login ({e.__class__.__name__})') from e
    if r.status_code != 200:
        raise PrecisaEntrar('o login venceu e o servidor não renovou: entre de novo')
    novo = r.json()
    if not novo.get('access_token'):
        raise PrecisaEntrar('o servidor renovou sem devolver o token: entre de novo')
    return novo


# — entrar: o login no navegador ——————————————————————————————————————————————
class _Guarda:
    """O TokenStorage da biblioteca `mcp`, em memória até o login terminar."""

    def __init__(self):
        self.tokens = None
        self.cliente = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens) -> None:
        self.tokens = tokens

    async def get_client_info(self):
        return self.cliente

    async def set_client_info(self, cliente) -> None:
        self.cliente = cliente


# nome → {'estado': 'esperando' | 'pronto' | 'erro', 'erro', 'state', 'codigo' (Future), 'tarefa'}
_entradas: dict[str, dict] = {}


def situacao(nome: str) -> dict:
    e = _entradas.get(nome)
    if e is None:
        return {'estado': 'pronto' if tem(nome) else 'nenhum', 'erro': None}
    return {'estado': e['estado'], 'erro': e.get('erro')}


async def comecar(nome: str, url: str, volta: str, ao_terminar=None) -> str:
    """Começa o login: devolve o endereço da página de login, pro Matheus abrir.
    O resto (esperar a volta, trocar o código, guardar) segue numa tarefa.
    `ao_terminar(nome)`: chamado depois de guardar (pôr o ajudante nos CLIs)."""
    from mcp import ClientSession
    from mcp.client.auth import OAuthClientProvider
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client
    from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata

    anterior = _entradas.get(nome)
    if anterior and anterior.get('tarefa') and not anterior['tarefa'].done():
        anterior['tarefa'].cancel()
    laco = asyncio.get_running_loop()
    endereco: asyncio.Future = laco.create_future()
    codigo: asyncio.Future = laco.create_future()
    entrada = {'estado': 'esperando', 'erro': None, 'state': None, 'codigo': codigo}
    _entradas[nome] = entrada
    guarda = _Guarda()

    async def mostrar(url_login: str) -> None:
        entrada['state'] = (parse_qs(urlsplit(url_login).query).get('state') or [None])[0]
        if not endereco.done():
            endereco.set_result(url_login)

    async def esperar() -> AuthorizationCodeResult:
        return await asyncio.wait_for(codigo, ENTRAR_MAX_S)

    provedor = OAuthClientProvider(
        server_url=url,
        client_metadata=OAuthClientMetadata(
            client_name='Solis', redirect_uris=[volta], grant_types=['authorization_code', 'refresh_token'],
            response_types=['code']),
        storage=guarda, redirect_handler=mostrar, callback_handler=esperar)

    async def rodar() -> None:
        try:
            cliente = create_mcp_http_client(auth=provedor)
            async with cliente, streamable_http_client(url, http_client=cliente) as (leitura, escrita, *_):
                async with ClientSession(leitura, escrita) as sessao:
                    await sessao.initialize()
            if guarda.tokens is None:
                # Conectou sem pedir login: o servidor não usa OAuth.
                raise PrecisaEntrar('esse servidor não pediu login (ele não usa OAuth)')
            ctx = provedor.context
            tokens = guarda.tokens.model_dump(mode='json', exclude_none=True)
            dados = {
                'url': url, 'tokens': tokens,
                'vence': time.time() + tokens['expires_in'] if tokens.get('expires_in') else None,
                'cliente': guarda.cliente.model_dump(mode='json', exclude_none=True) if guarda.cliente else {},
                'token_endpoint': str(ctx.oauth_metadata.token_endpoint) if ctx.oauth_metadata else None,
                'resource': ctx.get_resource_url() if ctx.should_include_resource_param(ctx.protocol_version) else None,
            }
            if not dados['token_endpoint']:
                dados['token_endpoint'] = ctx.get_authorization_base_url(url).rstrip('/') + '/token'
            _guardar(nome, dados)
            # "Pronto" só depois que os CLIs já usam o login (ao_terminar põe o
            # ajudante nos arquivos deles): antes, a tela dizia pronto e o Claude
            # Code ainda conectava sem o login por um instante.
            if ao_terminar is not None:
                await asyncio.to_thread(ao_terminar, nome)
            entrada['estado'] = 'pronto'
        except asyncio.CancelledError:
            entrada.update(estado='erro', erro='o login foi recomeçado')
            raise
        except Exception as e:  # noqa: BLE001 — a tela diz o motivo
            while getattr(e, 'exceptions', None):
                e = e.exceptions[0]
            if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
                motivo = 'o login demorou demais (passou de 10 minutos)'
            elif isinstance(e, PrecisaEntrar):
                motivo = str(e)
            else:
                motivo = f'o servidor não deixou entrar ({str(e) or e.__class__.__name__})'
            log.warning('mcp_oauth: o login em "%s" não terminou: %s', nome, motivo)
            entrada.update(estado='erro', erro=' '.join(motivo.split())[:200])
            if not endereco.done():
                endereco.set_exception(PrecisaEntrar(entrada['erro']))

    entrada['tarefa'] = laco.create_task(rodar())
    try:
        return await asyncio.wait_for(asyncio.shield(endereco), 30)
    except (asyncio.TimeoutError, TimeoutError) as e:
        raise PrecisaEntrar('o servidor não mostrou a página de login') from e


def voltou(state: str | None, code: str | None, erro: str | None = None) -> str | None:
    """A volta do navegador (/mcp/oauth/volta): entrega o código pro login
    que está esperando. Devolve o nome do servidor (ou None se nenhum esperava)."""
    from mcp.shared.auth import AuthorizationCodeResult
    for nome, e in _entradas.items():
        if e['estado'] == 'esperando' and e.get('state') == state and not e['codigo'].done():
            if erro or not code:
                e['codigo'].set_exception(PrecisaEntrar(f'o serviço recusou o login ({erro or "sem código"})'))
            else:
                e['codigo'].set_result(AuthorizationCodeResult(code=code, state=state))
            return nome
    return None
