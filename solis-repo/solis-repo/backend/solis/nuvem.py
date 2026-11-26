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

O celular (o corpo que não instala nada): o servidor entrega a própria tela do
Solis (o front construído, `npm run build` → dist/) no endereço dele. Quem abre
sem o cookie vai pra /entrar, cola o token uma vez, e o cookie fica no aparelho
(um ano, HttpOnly: o JavaScript da página não lê). Daí pra frente a tela fala
com o servidor pelo mesmo endereço, com o cookie indo sozinho, até nos
WebSockets da voz.
"""
import hmac
import logging
import os
import secrets
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs

from starlette.responses import JSONResponse, RedirectResponse
from starlette.websockets import WebSocketClose

from . import banco

log = logging.getLogger('solis.nuvem')

MINIMO = 24  # caracteres de um token aceito
LIVRES = {'/saude', '/entrar'}
COOKIE = 'solis_token'
COOKIE_DURA = 365 * 24 * 3600


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


def confere(dado: str | None) -> bool:
    return bool(dado) and hmac.compare_digest(dado.encode(), token().encode())


def autorizado(scope) -> bool:
    return confere(_do_pedido(scope))


def _quer_pagina(scope) -> bool:
    """O navegador abrindo uma página (e não a tela pedindo dados): vai pro /entrar."""
    if scope['type'] != 'http' or scope.get('method') != 'GET':
        return False
    for k, v in scope.get('headers', []):
        if k.lower() == b'accept':
            return b'text/html' in v
    return False


def pasta_do_front() -> Path:
    """O front construído (`npm run build`): SOLIS_FRONT, senão o dist/ do repositório."""
    if os.environ.get('SOLIS_FRONT'):
        return Path(os.environ['SOLIS_FRONT'])
    return Path(__file__).resolve().parents[2] / 'dist'


def arquivo_do_front(caminho: str) -> Path | None:
    """O arquivo pedido, só de dentro do dist/ (nada de ../); caminho sem
    extensão é rota da tela → index.html. None: não existe (ou não foi construído)."""
    pasta = pasta_do_front().resolve()
    indice = pasta / 'index.html'
    if not indice.is_file():
        return None
    alvo = (pasta / caminho).resolve()
    if alvo != pasta and pasta not in alvo.parents:
        return None
    if alvo.is_file():
        return alvo
    return indice if '.' not in Path(caminho).name else None


def https(cabecalhos, esquema: str) -> bool:
    """O pedido veio por https (direto, ou pelo túnel/proxy que avisa no cabeçalho)."""
    return esquema == 'https' or cabecalhos.get('x-forwarded-proto', '').split(',')[0].strip() == 'https'


PAGINA_ENTRAR = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Entrar no Solis</title>
<style>
  :root {{ color-scheme: light dark; --fundo: #f6f5f1; --texto: #1f1e1c; --borda: #d8d5cc; --botao: #1f1e1c; --botao-texto: #f6f5f1; --erro: #b3261e; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fundo: #1c1b19; --texto: #ece9e2; --borda: #3a3833; --botao: #ece9e2; --botao-texto: #1c1b19; --erro: #f2b8b5; }} }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--fundo); color: var(--texto);
         font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  form {{ width: min(360px, calc(100vw - 32px)); display: grid; gap: 12px; }}
  h1 {{ font-size: 22px; font-weight: 600; margin: 0; }}
  p {{ margin: 0; opacity: .75; font-size: 14px; }}
  input {{ font: inherit; padding: 12px; border: 1px solid var(--borda); border-radius: 10px; background: transparent; color: inherit; }}
  button {{ font: inherit; padding: 12px; border: 0; border-radius: 10px; background: var(--botao); color: var(--botao-texto); cursor: pointer; }}
  .erro {{ color: var(--erro); opacity: 1; }}
</style></head>
<body><form method="post" action="/entrar">
  <h1>Solis</h1>
  <p>Cole a senha do servidor (o token). Ela fica guardada neste aparelho.</p>
  {erro}
  <input name="token" type="password" autocomplete="current-password" required autofocus aria-label="Senha do servidor">
  <button type="submit">Entrar</button>
</form></body></html>"""


def pagina_entrar(errou: bool = False) -> str:
    erro = '<p class="erro" role="alert">Essa senha não é a do servidor.</p>' if errou else ''
    return PAGINA_ENTRAR.format(erro=erro)


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
        if _quer_pagina(scope):
            return await RedirectResponse('/entrar', status_code=303)(scope, receive, send)
        return await JSONResponse({'erro': 'sem_token'}, status_code=401)(scope, receive, send)
