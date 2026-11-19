"""Um servidor MCP de teste (stdio): uma ferramenta que só lê e uma que escreve
num arquivo (o caminho vem do ambiente). Usado por tests/test_corpo_mcp.py."""
import os

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

servidor = MCPServer('teste')


@servidor.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False))
def ver_saldo(conta: str) -> str:
    """Mostra o saldo de uma conta de teste."""
    return f'Saldo da conta {conta}: R$ 1.234,56'


@servidor.tool()
def anotar(texto: str) -> str:
    """Anota um texto no caderno de teste."""
    with open(os.environ['CADERNO'], 'a', encoding='utf-8') as f:
        f.write(texto + '\n')
    return 'Anotado.'


servidor.run('stdio')
