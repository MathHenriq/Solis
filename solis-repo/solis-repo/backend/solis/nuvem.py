"""O Solis como servidor: o cérebro na nuvem (26/11/2026).

No PC, o servidor do Solis só escuta 127.0.0.1 e não pede senha: quem fala com
ele é a janela do app, no mesmo computador. Num servidor alugado ele fica na
internet (ou numa rede privada, como a Tailscale), e aí cada pedido precisa
provar que vem do Matheus. Com SOLIS_SERVIDOR=1:

- toda rota pede o token, menos /saude (pra quem confere se o servidor está de
  pé). O token vai no cabeçalho `Authorization: Bearer ...`, no cookie
  `solis_token` ou, só no WebSocket (o navegador não deixa pôr cabeçalho
  nele), em `?token=...`. Sem token, 401; WebSocket sem token é fechado (1008);
- o token vem de SOLIS_TOKEN; sem ele, o Solis cria um forte na primeira
  subida e guarda num arquivo só do usuário (permissão 600), ao lado do banco.
  O log diz onde está o arquivo, nunca o token;
- token fraco (menos de MINIMO caracteres) não sobe: melhor parar do que ficar
  aberto pra quem adivinhar;
- o que só existe no PC não liga na subida: o Ollama e a leitura de páginas
  escaneadas (o OCR do Windows).

Por trás de um proxy na mesma máquina (o túnel da Cloudflare, o `tailscale
serve`), todo pedido chega de 127.0.0.1 — por isso o servidor nunca confia no
endereço de quem pede, só no token.
"""
import hmac
import logging
import os
import secrets
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs

from starlette.responses import JSONResponse
from starlette.websockets import WebSocketClose

from . import banco

log = logging.getLogger('solis.nuvem')

MINIMO = 24  # caracteres de um token aceito
LIVRES = {'/saude'}
COOKIE = 'solis_token'


class TokenFraco(RuntimeError):
    pass


def ligado() -> bool:
    return os.environ.get('SOLIS_SERVIDOR') == '1'


def arquivo_do_token() -> Path:
    return banco.caminho_padrao().parent / 'token'


_token: str | None = None


def token() -> str:
    """O token do servidor: SOLIS_TOKEN, senão o do arquivo (criado na primeira vez)."""
    global _token
    if os.environ.get('SOLIS_TOKEN'):
        valor = os.environ['SOLIS_TOKEN'].strip()
    elif _token:
        return _token
    else:
        caminho = arquivo_do_token()
        try:
            valor = caminho.read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            valor = secrets.token_urlsafe(32)
            try:
                fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return token()
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(valor + '\n')
            log.warning('token do servidor criado em %s (leia o arquivo pra entrar)', caminho)
        _token = valor
    if len(valor) < MINIMO:
        raise TokenFraco(f'o token do servidor tem {len(valor)} caracteres; o mínimo é {MINIMO}')
    return valor


def esquecer() -> None:
    """Pra quem troca o token (e pros testes)."""
    global _token
    _token = None


def conferir_na_subida() -> None:
    """Na subida em modo servidor: sem token forte, não sobe."""
    if ligado():
        token()
        log.info('Solis como servidor: todo pedido precisa do token (menos /saude)')


def _do_pedido(scope) -> str | None:
    cabecalhos = {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope.get('headers', [])}
    autorizacao = cabecalhos.get('authorization', '')
    if autorizacao.lower().startswith('bearer '):
        return autorizacao[7:].strip()
    if 'cookie' in cabecalhos:
        try:
            biscoito = SimpleCookie(cabecalhos['cookie'])
        except CookieError:
            biscoito = {}
        if COOKIE in biscoito:
            return biscoito[COOKIE].value
    if scope['type'] == 'websocket':
        valores = parse_qs(scope.get('query_string', b'').decode('latin-1')).get('token')
        if valores:
            return valores[0]
    return None


def autorizado(scope) -> bool:
    dado = _do_pedido(scope)
    return bool(dado) and hmac.compare_digest(dado.encode(), token().encode())


class Porteiro:
    """Middleware ASGI (pega HTTP e WebSocket, que o @app.middleware('http') não pega)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope['type'] not in ('http', 'websocket')
            or not ligado()
            or scope.get('path') in LIVRES
            # O "pode?" do navegador (CORS) não leva credencial; quem responde é o CORS.
            or (scope['type'] == 'http' and scope.get('method') == 'OPTIONS')
            or autorizado(scope)
        ):
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            return await WebSocketClose(code=1008)(scope, receive, send)
        return await JSONResponse({'erro': 'sem_token'}, status_code=401)(scope, receive, send)
