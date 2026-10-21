"""O SQLite do Solis — onde as conversas e as memórias ficam guardadas.

Um arquivo só, na pasta de dados do usuário (no Windows, %APPDATA%\\Solis).
`sqlite3` é da biblioteca padrão: nenhum servidor de banco pra instalar, que é o
que local-first pede.

O esquema é criado na primeira conexão (CREATE ... IF NOT EXISTS). Quando ele
precisar mudar, entra uma migração de verdade guiada por PRAGMA user_version.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversas (
    id     INTEGER PRIMARY KEY,
    criada TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mensagens (
    id       INTEGER PRIMARY KEY,
    conversa INTEGER NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    papel    TEXT NOT NULL CHECK (papel IN ('pessoa', 'solis')),
    texto    TEXT NOT NULL,
    criada   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS mensagens_da_conversa ON mensagens (conversa, id);
CREATE TABLE IF NOT EXISTS memorias (
    id       INTEGER PRIMARY KEY,
    texto    TEXT NOT NULL,
    tema     TEXT NOT NULL,
    -- 1 quando o Matheus pediu pra guardar; 0 quando o Solis achou relevante.
    pedido   INTEGER NOT NULL DEFAULT 0,
    -- De onde veio. Apagar a conversa não apaga o que foi aprendido nela.
    conversa INTEGER REFERENCES conversas(id) ON DELETE SET NULL,
    criada   TEXT NOT NULL
);
"""


def caminho_padrao() -> Path:
    if os.environ.get('SOLIS_BANCO'):
        return Path(os.environ['SOLIS_BANCO'])
    if os.name == 'nt' and os.environ.get('APPDATA'):
        return Path(os.environ['APPDATA']) / 'Solis' / 'solis.db'
    return Path.home() / '.local' / 'share' / 'solis' / 'solis.db'


_conexao: sqlite3.Connection | None = None


def usar(caminho: Path) -> None:
    """Aponta o banco pra outro arquivo — os testes usam um temporário."""
    global _conexao
    if _conexao:
        _conexao.close()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: o FastAPI pode atender de outra thread. As
    # escritas são curtas e uma por vez; não há disputa que justifique um pool.
    _conexao = sqlite3.connect(caminho, check_same_thread=False)
    _conexao.row_factory = sqlite3.Row
    _conexao.execute('PRAGMA foreign_keys = ON')
    _conexao.executescript(ESQUEMA)


def _con() -> sqlite3.Connection:
    if _conexao is None:
        usar(caminho_padrao())
    return _conexao


def _agora() -> str:
    # UTC no banco; quem converte pra hora local é o front, que sabe o fuso.
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def nova_conversa() -> int:
    with _con() as c:
        return c.execute('INSERT INTO conversas (criada) VALUES (?)', (_agora(),)).lastrowid


def ultima_conversa() -> int | None:
    linha = _con().execute('SELECT id FROM conversas ORDER BY id DESC LIMIT 1').fetchone()
    return linha['id'] if linha else None


def existe(conversa: int) -> bool:
    return _con().execute('SELECT 1 FROM conversas WHERE id = ?', (conversa,)).fetchone() is not None


def mensagens(conversa: int) -> list[dict]:
    linhas = _con().execute(
        'SELECT papel, texto, criada FROM mensagens WHERE conversa = ? ORDER BY id', (conversa,)
    )
    return [dict(l) for l in linhas]


def adicionar(conversa: int, papel: str, texto: str) -> None:
    with _con() as c:
        c.execute(
            'INSERT INTO mensagens (conversa, papel, texto, criada) VALUES (?, ?, ?, ?)',
            (conversa, papel, texto, _agora()),
        )


def memorias() -> list[dict]:
    """Da mais nova pra mais antiga — é a ordem da tela e a do prompt."""
    linhas = _con().execute('SELECT id, texto, tema, pedido, criada FROM memorias ORDER BY id DESC')
    return [{**dict(l), 'pedido': bool(l['pedido'])} for l in linhas]


def adicionar_memoria(texto: str, tema: str, pedido: bool, conversa: int | None) -> None:
    with _con() as c:
        c.execute(
            'INSERT INTO memorias (texto, tema, pedido, conversa, criada) VALUES (?, ?, ?, ?, ?)',
            (texto, tema, int(pedido), conversa, _agora()),
        )


def apagar_memoria(memoria: int) -> bool:
    with _con() as c:
        return c.execute('DELETE FROM memorias WHERE id = ?', (memoria,)).rowcount > 0
