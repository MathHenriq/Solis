"""Os cabeçalhos (a chave) de um servidor MCP por endereço, do cofre do Solis.

É o `headersHelper` que o Solis põe no ~/.claude.json no lugar da chave: o
Claude Code roda `python cabecalhos_mcp.py <nome>` num shell ao conectar e usa
o JSON que sair (solis/lancar_mcp.py, `cabecalhos`). Um arquivo solto, fora do
pacote, pra rodar sem o PYTHONPATH (o shell do helper não deixa pôr variável
de um jeito que valha no bash e no cmd).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solis.lancar_mcp import cabecalhos  # noqa: E402

if __name__ == '__main__':
    sys.exit(cabecalhos(sys.argv[1]) if len(sys.argv) == 2 else 2)
