"""Um servidor MCP com login OAuth de verdade (o da biblioteca `mcp`), pros
testes do mcp_oauth: cadastro do cliente, PKCE, código, token e renovação. A
página de login aprova sozinha (devolve o código na hora). Roda na máquina,
numa porta livre, numa thread."""
import secrets
import socket
import threading
import time

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, RefreshToken, construct_redirect_uri)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions


class Provedor:
    """Tudo em memória. `dura`: quantos segundos vale o access_token."""

    def __init__(self, dura: int = 3600):
        self.dura = dura
        self.clientes, self.codigos, self.acessos, self.renovacoes = {}, {}, {}, {}
        self.emitidos = 0
        self.renovados = 0

    async def get_client(self, client_id):
        return self.clientes.get(client_id)

    async def register_client(self, client_info):
        self.clientes[client_info.client_id] = client_info

    async def authorize(self, client, params):
        codigo = secrets.token_urlsafe(24)
        self.codigos[codigo] = AuthorizationCode(
            code=codigo, scopes=params.scopes or [], expires_at=time.time() + 300, client_id=client.client_id,
            code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly, resource=params.resource)
        return construct_redirect_uri(str(params.redirect_uri), code=codigo, state=params.state)

    async def load_authorization_code(self, client, authorization_code):
        return self.codigos.get(authorization_code)

    def _emitir(self, client_id, scopes, resource):
        from mcp.shared.auth import OAuthToken
        acesso, renova = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        self.acessos[acesso] = AccessToken(token=acesso, client_id=client_id, scopes=scopes,
                                           expires_at=int(time.time()) + self.dura, resource=resource)
        self.renovacoes[renova] = RefreshToken(token=renova, client_id=client_id, scopes=scopes, resource=resource)
        self.emitidos += 1
        return OAuthToken(access_token=acesso, token_type='Bearer', expires_in=self.dura,
                          refresh_token=renova, scope=' '.join(scopes) or None)

    async def exchange_authorization_code(self, client, authorization_code):
        self.codigos.pop(authorization_code.code, None)
        return self._emitir(client.client_id, authorization_code.scopes, authorization_code.resource)

    async def load_refresh_token(self, client, refresh_token):
        return self.renovacoes.get(refresh_token)

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        self.renovacoes.pop(refresh_token.token, None)
        self.renovados += 1
        return self._emitir(client.client_id, scopes or refresh_token.scopes, refresh_token.resource)

    async def load_access_token(self, token):
        a = self.acessos.get(token)
        if a is None or (a.expires_at and a.expires_at < time.time()):
            return None
        return a

    async def revoke_token(self, token):
        pass


class ServidorComLogin:
    """Sobe o servidor (`with ServidorComLogin() as s: s.url`)."""

    def __init__(self, dura: int = 3600):
        self.provedor = Provedor(dura)

    def __enter__(self):
        import uvicorn
        from mcp.server.mcpserver import MCPServer

        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            self.porta = s.getsockname()[1]
        base = f'http://127.0.0.1:{self.porta}'
        self.url = base + '/mcp'
        srv = MCPServer('com-login', auth_server_provider=self.provedor, auth=AuthSettings(
            issuer_url=base, resource_server_url=self.url, validate_token_resource=False,
            client_registration_options=ClientRegistrationOptions(enabled=True)))

        @srv.tool()
        def eco(texto: str) -> str:
            return texto

        self.servidor = uvicorn.Server(uvicorn.Config(srv.streamable_http_app(), host='127.0.0.1', port=self.porta,
                                                      log_level='error'))
        self.fio = threading.Thread(target=self.servidor.run, daemon=True)
        self.fio.start()
        while not self.servidor.started:
            time.sleep(0.05)
        return self

    def __exit__(self, *_):
        self.servidor.should_exit = True
        self.fio.join(10)
