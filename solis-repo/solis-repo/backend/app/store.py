"""Persistência da base de conhecimento. SQLite, local, sem servidor.

O banco mora em `~/.solis/solis.db` — fora do repositório, porque é dado do
usuário e não do projeto. `SOLIS_DB` sobrescreve (é o que os testes usam pra
não encostar no banco real).

Duas tabelas e um índice:

- `documents` — um por arquivo que entrou, inclusive os que falharam. Falha é
  registro, não exceção perdida: a tela de Conhecimento precisa mostrar o
  arquivo com o erro dele, senão o usuário sobe de novo o mesmo PDF escaneado
  sem entender por que não aparece nada.
- `chunks` — os pedaços indexáveis, com `embedding` reservado pra busca
  vetorial no futuro.
- `chunks_fts` — índice FTS5 de conteúdo externo (`content='chunks'`): o texto
  não é duplicado, o índice só aponta pro rowid da tabela real. Em troca disso,
  ele NÃO se atualiza sozinho — daí os três gatilhos.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# `content_rowid='id'` amarra o índice ao rowid de `chunks`. `remove_diacritics 2`
# é o que faz "memoria" encontrar "memória" — sem isso, metade das buscas em
# português falha por acento. (O nível 2 trata os acentos fora do Latin-1, que o
# nível 1 deixa passar.)
ESQUEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    chars      INTEGER NOT NULL DEFAULT 0,
    n_chunks   INTEGER NOT NULL DEFAULT 0,
    status     TEXT    NOT NULL,
    error      TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    embedding   BLOB
);

CREATE INDEX IF NOT EXISTS ix_chunks_document ON chunks(document_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE OF text ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


def caminho_db() -> Path:
    """Onde o banco mora. Lido a cada chamada, não no import.

    Se fosse constante de módulo, trocar `SOLIS_DB` depois do import não teria
    efeito — e é exatamente o que um teste faz.
    """
    env = os.environ.get("SOLIS_DB", "").strip()
    return Path(env).expanduser() if env else Path.home() / ".solis" / "solis.db"


@contextmanager
def conexao() -> Iterator[sqlite3.Connection]:
    """Conexão com commit no sucesso e rollback na exceção.

    `PRAGMA foreign_keys = ON` vai em TODA conexão: no SQLite ele é por conexão
    e vem desligado por padrão. Esquecer aqui não dá erro nenhum — o
    `ON DELETE CASCADE` simplesmente não acontece, e os chunks do documento
    apagado ficam órfãos no índice, aparecendo em buscas de um documento que a
    interface já não lista.
    """
    caminho = caminho_db()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with conexao() as con:
        con.executescript(ESQUEMA)


# --- escrita --------------------------------------------------------------


def salvar_documento(nome: str, chars: int, chunks: list[str]) -> int:
    """Grava o documento e seus chunks numa transação só.

    Tudo ou nada de propósito: documento gravado sem os chunks seria uma linha
    na tela de Conhecimento que nunca responde nada, e chunk sem documento não
    tem nome pra citar como fonte. O `executemany` também é o que evita N idas
    ao banco num PDF de trezentas páginas.
    """
    with conexao() as con:
        cur = con.execute(
            "INSERT INTO documents (name, chars, n_chunks, status) VALUES (?, ?, ?, 'processado')",
            (nome, chars, len(chunks)),
        )
        doc_id = int(cur.lastrowid or 0)
        con.executemany(
            "INSERT INTO chunks (document_id, idx, text) VALUES (?, ?, ?)",
            [(doc_id, i, texto) for i, texto in enumerate(chunks)],
        )
        return doc_id


def registrar_falha(nome: str, mensagem: str) -> int:
    """Documento que não deu pra ler vira linha com status 'erro'."""
    with conexao() as con:
        cur = con.execute(
            "INSERT INTO documents (name, chars, n_chunks, status, error) VALUES (?, 0, 0, 'erro', ?)",
            (nome, mensagem),
        )
        return int(cur.lastrowid or 0)


def remover_documento(doc_id: int) -> bool:
    """Apaga o documento. False se ele não existia.

    Os chunks vão junto pelo CASCADE, e o gatilho AFTER DELETE tira cada um do
    índice FTS. Por isso o `PRAGMA foreign_keys` em `conexao()` não é detalhe.
    """
    with conexao() as con:
        cur = con.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return cur.rowcount > 0


# --- leitura --------------------------------------------------------------


def listar_documentos() -> list[dict[str, Any]]:
    """Todos os documentos, mais recentes primeiro."""
    with conexao() as con:
        linhas = con.execute(
            """
            SELECT id, name, chars, n_chunks, status, error, created_at
            FROM documents
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(l) for l in linhas]


def obter_documento(doc_id: int) -> dict[str, Any] | None:
    with conexao() as con:
        linha = con.execute(
            "SELECT id, name, chars, n_chunks, status, error, created_at FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        return dict(linha) if linha else None


def contar() -> dict[str, int]:
    """Totais pro subtítulo da tela de Conhecimento."""
    with conexao() as con:
        linha = con.execute(
            """
            SELECT COUNT(*) AS documentos,
                   COALESCE(SUM(n_chunks), 0) AS trechos
            FROM documents WHERE status = 'processado'
            """
        ).fetchone()
        return {"documentos": int(linha["documentos"]), "trechos": int(linha["trechos"])}


def buscar(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Os k melhores chunks para a consulta FTS5.

    `ORDER BY score` ascendente: o `bm25()` do SQLite devolve valor NEGATIVO, e
    quanto mais negativo, melhor o casamento. Ordenar decrescente aqui — o
    reflexo de quem vem de outros buscadores — devolve exatamente os piores
    resultados, e o sintoma é sutil: vem conteúdo do documento certo, só que o
    trecho errado.

    Consulta com sintaxe inválida não pode derrubar o chat. O FTS5 responde a
    isso com OperationalError, e a decisão aqui é tratar como "não achei nada":
    a conversa segue sem contexto, que é degradação aceitável, em vez de um 500
    na cara de quem só fez uma pergunta.
    """
    if not query.strip():
        return []
    try:
        with conexao() as con:
            linhas = con.execute(
                """
                SELECT c.id            AS chunk_id,
                       c.document_id   AS document_id,
                       c.idx           AS idx,
                       c.text          AS text,
                       d.name          AS document,
                       bm25(chunks_fts) AS score
                FROM chunks_fts
                JOIN chunks    c ON c.id = chunks_fts.rowid
                JOIN documents d ON d.id = c.document_id
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, k),
            ).fetchall()
            return [dict(l) for l in linhas]
    except sqlite3.OperationalError:
        return []
