"""O lançador dos servidores MCP com chave (decisão do Matheus, 17/11/2026).

As variáveis de um servidor (as chaves de API) ficam no cofre do Solis
(ajustes.mcp_variaveis, seladas pela DPAPI: cofre.py), não em texto aberto no
~/.claude.json e no ~/.codex/config.toml. Lá vai só isto:

    python -m solis.lancar_mcp <nome> <comando do servidor...>

Quem liga o servidor (o Claude do Solis, o Claude Code ou o Codex do terminal)
roda o lançador; ele abre as chaves no cofre e liga o servidor de verdade com
elas, passando a entrada e a saída direto (é por elas que o MCP conversa).
Funciona na conta do Windows do Matheus, com o Solis instalado; não precisa do
Solis aberto. Em outra conta ou outro computador as chaves não abrem, e ele diz.
"""
import os
import shutil
import sqlite3
import subprocess
import sys

from . import cofre
from .banco import caminho_padrao

COFRE = 'mcp_variaveis'
# As do próprio lançador (achar o Solis e o banco): não passam pro servidor.
NOSSAS = ('PYTHONPATH', 'SOLIS_BANCO')


def variaveis(nome: str) -> dict[str, str] | None:
    """As variáveis abertas do servidor, ou None se o cofre não tem nenhuma dele."""
    import json
    con = sqlite3.connect(caminho_padrao())
    try:
        linha = con.execute('SELECT valor FROM ajustes WHERE chave = ?', (COFRE,)).fetchone()
    except sqlite3.Error:
        linha = None
    finally:
        con.close()
    seladas = (json.loads(linha[0]) if linha else {}).get(nome)
    if seladas is None:
        return None
    return {k: cofre.abrir(v) for k, v in seladas.items()}


def _amarrar_os_filhos() -> None:
    """Windows: o lançador entra num "job" que mata tudo o que ele ligou quando
    ele acaba. Sem isso, quem desliga o lançador (o Claude Code fechando) deixa
    o servidor (e o node que o npx abre) rodando à toa."""
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes

    class _Basico(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD)]

    class _Estendido(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', _Basico), ('IoInfo', ctypes.c_uint64 * 6),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    k = ctypes.windll.kernel32
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k.CreateJobObjectW(None, None)
    if not job:
        return
    info = _Estendido()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):  # 9: ExtendedLimitInformation
        # O handle do job fica aberto até o lançador acabar (de propósito).
        k.AssignProcessToJobObject(job, k.GetCurrentProcess())


def ambiente(nome: str, base: dict[str, str]) -> dict[str, str] | str:
    """O ambiente do servidor (o de quem ligou, sem as nossas, mais as chaves),
    ou o motivo de não ligar."""
    abertas = variaveis(nome)
    if abertas is None:
        return f'o cofre do Solis não tem as variáveis do servidor "{nome}": salve ele de novo pela tela'
    if cofre.ILEGIVEL in abertas.values():
        return f'as chaves do servidor "{nome}" não abrem nesta conta do Windows (o cofre é desta conta)'
    env = {k: v for k, v in base.items() if k not in NOSSAS}
    env.update(abertas)
    return env


def cabecalhos(nome: str) -> int:
    """Pro servidor por endereço (20/11/2026): os cabeçalhos (a chave) do cofre,
    em JSON na saída — o `headersHelper` do Claude Code roda isto ao conectar e
    usa o que sair. A chave não fica no ~/.claude.json."""
    import json

    from . import mcp_oauth
    abertas = variaveis(nome) or {}
    if cofre.ILEGIVEL in abertas.values():
        print(f'Solis: os cabeçalhos do servidor "{nome}" não abrem (o cofre é desta conta do Windows)',
              file=sys.stderr)
        return 1
    # O login (mcp_oauth, 20/11/2026): o token, renovado se venceu.
    try:
        token = mcp_oauth.token(nome)
    except mcp_oauth.PrecisaEntrar as e:
        print(f'Solis: {e} (pela tela do Solis: Configurações → Servidores MCP → Entrar)', file=sys.stderr)
        return 1
    if token:
        abertas['Authorization'] = f'Bearer {token}'
    if not abertas:
        print(f'Solis: o cofre não tem a chave nem o login do servidor "{nome}"', file=sys.stderr)
        return 1
    print(json.dumps(abertas))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == '--cabecalhos':
        return cabecalhos(argv[1])
    if len(argv) < 2:
        print('uso: python -m solis.lancar_mcp <nome> <comando...>', file=sys.stderr)
        return 2
    nome, comando = argv[0], argv[1:]
    env = ambiente(nome, dict(os.environ))
    if isinstance(env, str):
        print(f'Solis: {env}', file=sys.stderr)
        return 1
    # "npx" no Windows é npx.cmd: o Popen não acha sozinho com o PATH novo.
    comando[0] = shutil.which(comando[0], path=env.get('PATH')) or comando[0]
    _amarrar_os_filhos()
    try:
        return subprocess.run(comando, env=env).returncode
    except FileNotFoundError:
        print(f'Solis: não achei "{comando[0]}" neste computador', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
