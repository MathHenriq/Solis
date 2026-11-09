"""O SQLite do Solis — onde as conversas e as memórias ficam guardadas.

Um arquivo só, na pasta de dados do usuário (no Windows, %APPDATA%\\Solis).
`sqlite3` é da biblioteca padrão: nenhum servidor de banco pra instalar, que é o
que local-first pede.

O esquema base é criado na primeira conexão (CREATE ... IF NOT EXISTS). O que
mudou depois entra por MIGRACOES, guiadas por PRAGMA user_version: um banco que
já existe no notebook não ganha coluna nova com IF NOT EXISTS.
"""
import json
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from . import cofre

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

# Cada item leva o banco da versão i pra i+1. Só se acrescenta no fim; nunca se
# edita uma migração que já rodou na máquina de alguém.
MIGRACOES = [
    # 1 — modo privado e busca por significado.
    """
    -- Privada nunca sai da máquina: só modelo local a vê.
    ALTER TABLE memorias ADD COLUMN privada INTEGER NOT NULL DEFAULT 0;
    -- Embedding de uma memória ou mensagem, em float32. `tipo` diz de qual
    -- tabela é o `ref`; não dá pra ter chave estrangeira pra duas tabelas,
    -- então quem apaga a origem apaga o vetor junto (ver apagar_memoria).
    CREATE TABLE vetores (
        tipo  TEXT NOT NULL CHECK (tipo IN ('memoria', 'mensagem')),
        ref   INTEGER NOT NULL,
        vetor BLOB NOT NULL,
        PRIMARY KEY (tipo, ref)
    );
    """,
    # 2 — memória que muda e conversa longa.
    """
    -- "Saí da Syngenta" não apaga "Trabalha na Syngenta": marca a antiga como
    -- substituída pela nova. Sai do prompt e da tela, mas continua no banco —
    -- se o modelo errou a substituição, nada se perdeu.
    ALTER TABLE memorias ADD COLUMN substituida_por INTEGER REFERENCES memorias(id);
    -- Resumo das mensagens antigas da conversa, até a mensagem `resumo_ate`.
    ALTER TABLE conversas ADD COLUMN resumo TEXT;
    ALTER TABLE conversas ADD COLUMN resumo_ate INTEGER NOT NULL DEFAULT 0;
    """,
    # 3 — cérebros externos e importação.
    """
    -- Mensagem dita em sigilo, ou de onde saiu uma memória privada. Não vai pra
    -- modelo de nuvem, nem como histórico nem como trecho.
    ALTER TABLE mensagens ADD COLUMN privada INTEGER NOT NULL DEFAULT 0;
    -- Quem respondeu: 'local', 'claude', 'codex'. Nulo nas falas da pessoa e nas
    -- respostas de antes desta coluna.
    ALTER TABLE mensagens ADD COLUMN cerebro TEXT;
    -- De onde veio a conversa: 'solis', ou 'chatgpt' e 'claude' quando importada.
    ALTER TABLE conversas ADD COLUMN origem TEXT NOT NULL DEFAULT 'solis';
    ALTER TABLE conversas ADD COLUMN titulo TEXT;
    -- Id da conversa no serviço de origem: importar de novo não duplica.
    ALTER TABLE conversas ADD COLUMN externo TEXT;
    CREATE UNIQUE INDEX conversas_externas ON conversas (externo) WHERE externo IS NOT NULL;
    -- Conversa importada da qual o Solis já tirou as memórias. Extrair de anos
    -- de histórico leva horas; isto deixa parar e continuar de onde parou.
    ALTER TABLE conversas ADD COLUMN aprendida INTEGER NOT NULL DEFAULT 0;
    """,
    # 4 — etapas da resposta.
    """
    -- O que o Solis fez pra chegar na resposta, com o tempo de cada etapa (JSON,
    -- a lista de eventos do stream sem o texto). A tela mostra "5 etapas · 3,2 s"
    -- também nas respostas de antes de reabrir o app.
    ALTER TABLE mensagens ADD COLUMN etapas TEXT;
    """,
    # 5 — busca textual nas memórias.
    """
    -- Índice de texto das memórias pra busca da tela de Memória: sem diferença
    -- de acento ("memoria" acha "memória") e por prefixo. Conteúdo externo: o
    -- texto mora só em `memorias`, e os gatilhos mantêm o índice junto.
    -- ATENÇÃO quando a memória privada for criptografada: este índice guarda o
    -- texto legível, e a privada vai ter que sair dele.
    CREATE VIRTUAL TABLE memorias_fts USING fts5(
        texto, tema, content='memorias', content_rowid='id',
        tokenize='unicode61 remove_diacritics 2'
    );
    CREATE TRIGGER memorias_fts_inclui AFTER INSERT ON memorias BEGIN
        INSERT INTO memorias_fts(rowid, texto, tema) VALUES (new.id, new.texto, new.tema);
    END;
    CREATE TRIGGER memorias_fts_apaga AFTER DELETE ON memorias BEGIN
        INSERT INTO memorias_fts(memorias_fts, rowid, texto, tema) VALUES ('delete', old.id, old.texto, old.tema);
    END;
    CREATE TRIGGER memorias_fts_muda AFTER UPDATE OF texto, tema ON memorias BEGIN
        INSERT INTO memorias_fts(memorias_fts, rowid, texto, tema) VALUES ('delete', old.id, old.texto, old.tema);
        INSERT INTO memorias_fts(rowid, texto, tema) VALUES (new.id, new.texto, new.tema);
    END;
    -- As memórias de antes desta versão entram no índice agora.
    INSERT INTO memorias_fts(memorias_fts) VALUES ('rebuild');
    """,
    # 6 — o índice de busca sem as memórias privadas.
    """
    -- A memória privada passa a ficar criptografada (solis/cofre.py), e o
    -- índice da 5 guardava o texto legível de todas. Ele vira um índice com
    -- conteúdo próprio, só das que não são privadas; as privadas são buscadas
    -- abrindo uma a uma (buscar_memorias), que são poucas.
    DROP TRIGGER memorias_fts_inclui;
    DROP TRIGGER memorias_fts_apaga;
    DROP TRIGGER memorias_fts_muda;
    DROP TABLE memorias_fts;
    CREATE VIRTUAL TABLE memorias_fts USING fts5(texto, tema, tokenize='unicode61 remove_diacritics 2');
    CREATE TRIGGER memorias_fts_inclui AFTER INSERT ON memorias WHEN new.privada = 0 BEGIN
        INSERT INTO memorias_fts(rowid, texto, tema) VALUES (new.id, new.texto, new.tema);
    END;
    CREATE TRIGGER memorias_fts_apaga AFTER DELETE ON memorias BEGIN
        DELETE FROM memorias_fts WHERE rowid = old.id;
    END;
    CREATE TRIGGER memorias_fts_muda AFTER UPDATE OF texto, tema, privada ON memorias BEGIN
        DELETE FROM memorias_fts WHERE rowid = old.id;
        INSERT INTO memorias_fts(rowid, texto, tema) SELECT new.id, new.texto, new.tema WHERE new.privada = 0;
    END;
    INSERT INTO memorias_fts(rowid, texto, tema) SELECT id, texto, tema FROM memorias WHERE privada = 0;
    """,
    # 7 — ajustes escolhidos pela tela (a ordem dos cérebros, por enquanto).
    """
    -- Chave e valor em JSON: cada ajuste novo não pede migração própria. Fica
    -- no banco e não num arquivo à parte porque o banco já é o que se copia
    -- pra levar o Solis pra outra máquina.
    CREATE TABLE ajustes (
        chave TEXT PRIMARY KEY,
        valor TEXT NOT NULL
    );
    """,
    # 8 — Conhecimento: os arquivos que o Matheus entrega pro Solis ler.
    """
    -- Só o texto extraído fica, cortado em trechos; o arquivo original não é
    -- copiado. O hash impede o mesmo arquivo de entrar duas vezes. Fonte
    -- privada tem o nome e os trechos selados pelo cofre e fica fora do
    -- índice de busca, como a memória privada.
    CREATE TABLE documentos (
        id      INTEGER PRIMARY KEY,
        nome    TEXT NOT NULL,
        tipo    TEXT NOT NULL CHECK (tipo IN ('pdf', 'nota')),
        paginas INTEGER,
        bytes   INTEGER NOT NULL,
        hash    TEXT NOT NULL UNIQUE,
        privado INTEGER NOT NULL DEFAULT 0,
        criado  TEXT NOT NULL
    );
    -- O vetor fica no próprio trecho: a tabela vetores só aceita memória e
    -- mensagem (CHECK), e mudar um CHECK no SQLite é recriar a tabela.
    CREATE TABLE trechos (
        id        INTEGER PRIMARY KEY,
        documento INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
        ordem     INTEGER NOT NULL,
        pagina    INTEGER,
        texto     TEXT NOT NULL,
        vetor     BLOB
    );
    CREATE INDEX trechos_do_documento ON trechos (documento, ordem);
    CREATE VIRTUAL TABLE trechos_fts USING fts5(texto, tokenize='unicode61 remove_diacritics 2');
    CREATE TRIGGER trechos_fts_inclui AFTER INSERT ON trechos
    WHEN (SELECT privado FROM documentos WHERE id = new.documento) = 0 BEGIN
        INSERT INTO trechos_fts(rowid, texto) VALUES (new.id, new.texto);
    END;
    CREATE TRIGGER trechos_fts_apaga AFTER DELETE ON trechos BEGIN
        DELETE FROM trechos_fts WHERE rowid = old.id;
    END;
    """,
    # 9 — Conhecimento: página web (tipo 'web' e o endereço).
    """
    -- Mudar o CHECK do tipo no SQLite é recriar a tabela. Os trechos vão
    -- junto (a chave estrangeira aponta pra documentos), com os MESMOS ids:
    -- o índice trechos_fts usa o id como rowid e os vetores estão nos
    -- próprios trechos, então nada precisa ser reindexado. Os gatilhos saem
    -- antes do DROP pra não mexerem no índice no meio da troca.
    CREATE TABLE documentos_9 (
        id      INTEGER PRIMARY KEY,
        nome    TEXT NOT NULL,
        tipo    TEXT NOT NULL CHECK (tipo IN ('pdf', 'nota', 'web')),
        paginas INTEGER,
        bytes   INTEGER NOT NULL,
        hash    TEXT NOT NULL UNIQUE,
        privado INTEGER NOT NULL DEFAULT 0,
        criado  TEXT NOT NULL,
        url     TEXT
    );
    INSERT INTO documentos_9 (id, nome, tipo, paginas, bytes, hash, privado, criado)
        SELECT id, nome, tipo, paginas, bytes, hash, privado, criado FROM documentos;
    CREATE TABLE trechos_9 (
        id        INTEGER PRIMARY KEY,
        documento INTEGER NOT NULL REFERENCES documentos_9(id) ON DELETE CASCADE,
        ordem     INTEGER NOT NULL,
        pagina    INTEGER,
        texto     TEXT NOT NULL,
        vetor     BLOB
    );
    INSERT INTO trechos_9 (id, documento, ordem, pagina, texto, vetor)
        SELECT id, documento, ordem, pagina, texto, vetor FROM trechos;
    DROP TRIGGER trechos_fts_inclui;
    DROP TRIGGER trechos_fts_apaga;
    DROP TABLE trechos;
    DROP TABLE documentos;
    -- O RENAME também reescreve a referência de trechos_9 pra "documentos".
    ALTER TABLE documentos_9 RENAME TO documentos;
    ALTER TABLE trechos_9 RENAME TO trechos;
    CREATE INDEX trechos_do_documento ON trechos (documento, ordem);
    CREATE TRIGGER trechos_fts_inclui AFTER INSERT ON trechos
    WHEN (SELECT privado FROM documentos WHERE id = new.documento) = 0 BEGIN
        INSERT INTO trechos_fts(rowid, texto) VALUES (new.id, new.texto);
    END;
    CREATE TRIGGER trechos_fts_apaga AFTER DELETE ON trechos BEGIN
        DELETE FROM trechos_fts WHERE rowid = old.id;
    END;
    """,
]


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
    # WAL: o servidor MCP (outro processo) lê o mesmo arquivo enquanto o
    # servidor do Solis escreve, sem um travar o outro.
    _conexao.execute('PRAGMA journal_mode = WAL')
    # O SQLite não apaga o que é sobrescrito: o texto antigo sobra no espaço
    # livre das páginas. Com isto ele é zerado — sem isso, o segredo selado
    # depois de descoberto (ver _limpar_rastros) continuava legível no arquivo.
    _conexao.execute('PRAGMA secure_delete = ON')
    _conexao.executescript(ESQUEMA)
    _migrar(_conexao)
    _selar_o_que_falta(_conexao)


def _migrar(c: sqlite3.Connection) -> None:
    versao = c.execute('PRAGMA user_version').fetchone()[0]
    for numero, sql in enumerate(MIGRACOES[versao:], start=versao + 1):
        # executescript faz COMMIT antes de rodar, então a migração e a versão
        # vão juntas num script só: ou as duas ficam, ou nenhuma.
        c.executescript(f'BEGIN; {sql} PRAGMA user_version = {numero}; COMMIT;')


def _selar_o_que_falta(c: sqlite3.Connection) -> None:
    """Sela o que é privado e ainda está legível: o que veio de antes do cofre,
    e o que ficou pra trás se o servidor caiu no meio. Roda toda vez que o
    banco abre; o que já está selado é pulado, então custa uma consulta."""
    if not cofre.DISPONIVEL:
        return
    falta = f"NOT LIKE '{cofre.PREFIXO}%'"
    with c:
        for l in c.execute(f'SELECT id, texto FROM memorias WHERE privada = 1 AND texto {falta}').fetchall():
            c.execute('UPDATE memorias SET texto = ? WHERE id = ?', (cofre.selar(l['texto']), l['id']))
        conversas = [l['conversa'] for l in c.execute('SELECT DISTINCT conversa FROM mensagens WHERE privada = 1')]
    for conversa in conversas:
        _selar_conversa(c, conversa)
    _limpar_rastros(c)


def _limpar_rastros(c: sqlite3.Connection) -> None:
    """Passa o -wal pro banco e o esvazia. As versões antigas das páginas — com
    o texto de antes de ser selado — ficam no -wal até ele ser reaproveitado;
    truncar tira de lá. (O que o disco guarda por baixo do arquivo, depois de
    apagado, já é com o Windows.)"""
    c.execute('PRAGMA wal_checkpoint(TRUNCATE)')


def _selar_conversa(c: sqlite3.Connection, conversa: int) -> None:
    """Numa conversa com algo privado, sela o texto das mensagens privadas e
    tudo que pode repetir o segredo: o título, o resumo e as etapas guardadas
    com as respostas (o chip de memória guardada leva o texto dela)."""
    with c:
        for l in c.execute('SELECT id, texto FROM mensagens WHERE conversa = ? AND privada = 1', (conversa,)).fetchall():
            c.execute('UPDATE mensagens SET texto = ? WHERE id = ?', (cofre.selar(l['texto']), l['id']))
        for l in c.execute('SELECT id, etapas FROM mensagens WHERE conversa = ? AND etapas IS NOT NULL', (conversa,)).fetchall():
            c.execute('UPDATE mensagens SET etapas = ? WHERE id = ?', (cofre.selar(l['etapas']), l['id']))
        l = c.execute('SELECT titulo, resumo FROM conversas WHERE id = ?', (conversa,)).fetchone()
        if l:
            c.execute(
                'UPDATE conversas SET titulo = ?, resumo = ? WHERE id = ?',
                (cofre.selar(l['titulo']), cofre.selar(l['resumo']), conversa),
            )


def _con() -> sqlite3.Connection:
    if _conexao is None:
        usar(caminho_padrao())
    return _conexao


def ajuste(chave: str):
    """O valor guardado, ou None se nunca foi escolhido pela tela."""
    l = _con().execute('SELECT valor FROM ajustes WHERE chave = ?', (chave,)).fetchone()
    return json.loads(l['valor']) if l else None


def guardar_ajuste(chave: str, valor) -> None:
    with _con() as c:
        c.execute(
            'INSERT INTO ajustes (chave, valor) VALUES (?, ?) '
            'ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor',
            (chave, json.dumps(valor)),
        )


def apagar_ajuste(chave: str) -> None:
    with _con() as c:
        c.execute('DELETE FROM ajustes WHERE chave = ?', (chave,))


def _agora() -> str:
    # UTC no banco; quem converte pra hora local é o front, que sabe o fuso.
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def nova_conversa(origem: str = 'solis', titulo: str | None = None, externo: str | None = None,
                  criada: str | None = None) -> int:
    with _con() as c:
        return c.execute(
            'INSERT INTO conversas (criada, origem, titulo, externo) VALUES (?, ?, ?, ?)',
            (criada or _agora(), origem, titulo, externo),
        ).lastrowid


def conversa_externa(externo: str) -> int | None:
    linha = _con().execute('SELECT id FROM conversas WHERE externo = ?', (externo,)).fetchone()
    return linha['id'] if linha else None


def ultima_conversa() -> int | None:
    # Conversa importada não é "a última": o app reabre a última do próprio Solis.
    # E "última" é a da mensagem mais recente, não a criada por último: com a
    # lista de conversas dá pra voltar a uma antiga e continuar nela.
    linha = _con().execute(
        "SELECT c.id FROM conversas c WHERE c.origem = 'solis' "
        'ORDER BY COALESCE((SELECT MAX(m.id) FROM mensagens m WHERE m.conversa = c.id), 0) DESC, c.id DESC '
        'LIMIT 1'
    ).fetchone()
    return linha['id'] if linha else None


# Título de conversa sem título: a primeira fala, numa linha só, até aqui.
TITULO_MAX = 80


def conversas(busca: str = '', limite: int = 200) -> list[dict]:
    """As conversas do Solis com alguma mensagem, da mais recente pra mais
    antiga — a lista do painel. As importadas ficam de fora: são arquivo, e
    voltam pela busca na memória. `busca` procura no título e no texto das
    mensagens, sem diferença de maiúscula (só nas letras sem acento — é o LIKE
    do SQLite). O que está selado (conversa com algo privado) não é achado
    pelo texto, só pelo título — que também fica selado nessas."""
    filtro, args = '', []
    if busca.strip():
        # "!" escapa os curingas do LIKE: buscar "50%" acha "50%", não tudo.
        padrao = '%' + busca.strip().replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        filtro = (
            "AND (c.titulo LIKE ? ESCAPE '!' OR EXISTS "
            "(SELECT 1 FROM mensagens x WHERE x.conversa = c.id AND x.texto LIKE ? ESCAPE '!'))"
        )
        args = [padrao, padrao]
    linhas = _con().execute(
        'SELECT c.id, c.titulo, MAX(m.criada) AS atualizada, '
        "(SELECT texto FROM mensagens p WHERE p.conversa = c.id AND p.papel = 'pessoa' ORDER BY p.id LIMIT 1) AS primeira "
        "FROM conversas c JOIN mensagens m ON m.conversa = c.id WHERE c.origem = 'solis' "
        f'{filtro} GROUP BY c.id ORDER BY MAX(m.id) DESC LIMIT ?',
        [*args, limite],
    )
    return [
        {
            'id': l['id'],
            'titulo': cofre.abrir(l['titulo']) or _titulo(cofre.abrir(l['primeira']) or ''),
            'atualizada': l['atualizada'],
        }
        for l in linhas
    ]


def _titulo(texto: str) -> str:
    """A primeira fala vira título: numa linha só e cortada no fim de uma
    palavra. As reticências ficam com a tela, que corta pela largura."""
    linha = ' '.join(texto.split())
    if len(linha) <= TITULO_MAX:
        return linha
    return linha[:TITULO_MAX].rsplit(' ', 1)[0]


def existe(conversa: int) -> bool:
    return _con().execute('SELECT 1 FROM conversas WHERE id = ?', (conversa,)).fetchone() is not None


def mensagens(conversa: int, depois_de: int = 0) -> list[dict]:
    linhas = _con().execute(
        'SELECT id, papel, texto, criada, privada, cerebro, etapas FROM mensagens '
        'WHERE conversa = ? AND id > ? ORDER BY id',
        (conversa, depois_de),
    )
    return [
        {
            **dict(l),
            'texto': cofre.abrir(l['texto']),
            'privada': bool(l['privada']),
            'etapas': _etapas(cofre.abrir(l['etapas'])),
        }
        for l in linhas
    ]


def _etapas(valor: str | None) -> list[dict] | None:
    if not valor:
        return None
    try:
        return json.loads(valor)
    except json.JSONDecodeError:
        return None  # selado e ilegível neste computador


def guardar_etapas(mensagem: int, etapas: list[dict]) -> None:
    valor = json.dumps(etapas, ensure_ascii=False)
    conversa = _con().execute('SELECT conversa FROM mensagens WHERE id = ?', (mensagem,)).fetchone()
    if conversa and tem_privada(conversa['conversa']):
        valor = cofre.selar(valor)
    with _con() as c:
        c.execute('UPDATE mensagens SET etapas = ? WHERE id = ?', (valor, mensagem))


def tem_privada(conversa: int) -> bool:
    return _con().execute(
        'SELECT 1 FROM mensagens WHERE conversa = ? AND privada = 1 LIMIT 1', (conversa,)
    ).fetchone() is not None


def marcar_privada(mensagem: int) -> None:
    """A mensagem e a resposta logo depois dela: o que o Solis respondeu a algo
    dito em sigilo costuma repetir o que foi dito."""
    with _con() as c:
        c.execute(
            'UPDATE mensagens SET privada = 1 WHERE id = ? OR id = ('
            '  SELECT MIN(id) FROM mensagens WHERE id > ? AND conversa = '
            '  (SELECT conversa FROM mensagens WHERE id = ?))',
            (mensagem, mensagem, mensagem),
        )
        conversa = c.execute('SELECT conversa FROM mensagens WHERE id = ?', (mensagem,)).fetchone()
    # O que já foi escrito em claro nesta conversa (o título dado antes do
    # aprendizado descobrir o sigilo, por exemplo) é selado agora.
    if conversa:
        _selar_conversa(_con(), conversa['conversa'])
        _limpar_rastros(_con())


def resumo(conversa: int) -> tuple[str | None, int]:
    """(resumo, id da última mensagem que ele cobre). Sem resumo: (None, 0)."""
    linha = _con().execute('SELECT resumo, resumo_ate FROM conversas WHERE id = ?', (conversa,)).fetchone()
    return (cofre.abrir(linha['resumo']), linha['resumo_ate']) if linha else (None, 0)


def titulo(conversa: int) -> str | None:
    linha = _con().execute('SELECT titulo FROM conversas WHERE id = ?', (conversa,)).fetchone()
    return cofre.abrir(linha['titulo']) if linha else None


def _talvez_selar(conversa: int, texto: str | None) -> str | None:
    """Título e resumo de conversa com algo privado podem repetir o segredo."""
    return cofre.selar(texto) if tem_privada(conversa) else texto


def guardar_titulo(conversa: int, titulo: str) -> None:
    with _con() as c:
        c.execute('UPDATE conversas SET titulo = ? WHERE id = ?', (_talvez_selar(conversa, titulo), conversa))


def guardar_resumo(conversa: int, texto: str, ate: int) -> None:
    with _con() as c:
        c.execute(
            'UPDATE conversas SET resumo = ?, resumo_ate = ? WHERE id = ?',
            (_talvez_selar(conversa, texto), ate, conversa),
        )


def adicionar(conversa: int, papel: str, texto: str, privada: bool = False, cerebro: str | None = None,
              criada: str | None = None) -> int:
    with _con() as c:
        return c.execute(
            'INSERT INTO mensagens (conversa, papel, texto, criada, privada, cerebro) VALUES (?, ?, ?, ?, ?, ?)',
            (conversa, papel, cofre.selar(texto) if privada else texto, criada or _agora(), int(privada), cerebro),
        ).lastrowid


def memorias() -> list[dict]:
    """As que valem — as substituídas ficam de fora. Da mais nova pra mais
    antiga, que é a ordem da tela e a do prompt."""
    linhas = _con().execute(
        'SELECT id, texto, tema, pedido, privada, criada FROM memorias '
        'WHERE substituida_por IS NULL ORDER BY id DESC'
    )
    return [_memoria(l) for l in linhas]


def _memoria(l: sqlite3.Row) -> dict:
    return {**dict(l), 'texto': cofre.abrir(l['texto']), 'pedido': bool(l['pedido']), 'privada': bool(l['privada'])}


def _sem_acento(texto: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', texto.lower()) if not unicodedata.combining(c))


def buscar_memorias(busca: str, limite: int = 200) -> list[dict]:
    """As memórias que valem com todas as palavras da busca, por prefixo e sem
    diferença de acento, da mais ligada à busca pra menos (bm25). Busca sem
    palavra nenhuma devolve todas, como memorias().

    As privadas não estão no índice (estão seladas): são abertas e conferidas
    aqui, com a mesma regra, e vêm depois das do índice."""
    palavras = re.findall(r'\w+', busca)
    if not palavras:
        return memorias()
    # Cada palavra entre aspas (o que o FTS5 lê como operador vira texto) e com
    # * no fim: "synge" acha "Syngenta". Separadas por espaço = todas precisam.
    consulta = ' '.join(f'"{p}"*' for p in palavras)
    linhas = _con().execute(
        'SELECT m.id, m.texto, m.tema, m.pedido, m.privada, m.criada '
        'FROM memorias_fts JOIN memorias m ON m.id = memorias_fts.rowid '
        'WHERE memorias_fts MATCH ? AND m.substituida_por IS NULL '
        'ORDER BY bm25(memorias_fts) LIMIT ?',
        (consulta, limite),
    )
    publicas = [_memoria(l) for l in linhas]
    procuradas = [_sem_acento(p) for p in palavras]
    privadas = []
    for m in (m for m in memorias() if m['privada']):
        tem = re.findall(r'\w+', _sem_acento(f'{m["texto"]} {m["tema"]}'))
        if all(any(t.startswith(p) for t in tem) for p in procuradas):
            privadas.append(m)
    return (publicas + privadas)[:limite]


def adicionar_memoria(
    texto: str, tema: str, pedido: bool, conversa: int | None, privada: bool = False, substitui: int | None = None
) -> int:
    with _con() as c:
        nova = c.execute(
            'INSERT INTO memorias (texto, tema, pedido, privada, conversa, criada) VALUES (?, ?, ?, ?, ?, ?)',
            (cofre.selar(texto) if privada else texto, tema, int(pedido), int(privada), conversa, _agora()),
        ).lastrowid
        if substitui is not None:
            c.execute(
                'UPDATE memorias SET substituida_por = ? WHERE id = ? AND substituida_por IS NULL',
                (nova, substitui),
            )
        return nova


def corrigir_memoria(memoria: int, texto: str) -> dict | None:
    """Troca o texto de uma memória que vale (o Matheus corrigindo pela tela).
    Privada continua selada. O vetor velho sai — ele descrevia o texto antigo
    — e a memória volta pra fila da busca por significado. O índice de busca
    textual acompanha sozinho (gatilho). None se a memória não existe ou já
    foi substituída."""
    with _con() as c:
        linha = c.execute(
            'SELECT privada FROM memorias WHERE id = ? AND substituida_por IS NULL', (memoria,)
        ).fetchone()
        if not linha:
            return None
        c.execute(
            'UPDATE memorias SET texto = ? WHERE id = ?',
            (cofre.selar(texto) if linha['privada'] else texto, memoria),
        )
        c.execute("DELETE FROM vetores WHERE tipo = 'memoria' AND ref = ?", (memoria,))
    if linha['privada']:
        _limpar_rastros(_con())  # o texto antigo não pode sobrar no -wal
    return next((m for m in memorias() if m['id'] == memoria), None)


def apagar_memoria(memoria: int) -> bool:
    """Esquece uma memória. Se ela tinha substituído outra ("Trabalha na Vale"
    no lugar de "Trabalha na Syngenta"), a antiga volta a valer: era a verdade
    antes dela. Sem isto, a antiga apontava pra uma memória que não existe mais
    e o banco recusava apagar (visto num teste, 08/11/2026)."""
    with _con() as c:
        c.execute(
            'UPDATE memorias SET substituida_por = (SELECT substituida_por FROM memorias WHERE id = ?) '
            'WHERE substituida_por = ?',
            (memoria, memoria),
        )
        c.execute("DELETE FROM vetores WHERE tipo = 'memoria' AND ref = ?", (memoria,))
        return c.execute('DELETE FROM memorias WHERE id = ?', (memoria,)).rowcount > 0


# — Vetores (busca por significado) —————————————————————————————————————————————

_ORIGEM = {'memoria': 'memorias', 'mensagem': 'mensagens'}


def sem_vetor(tipo: str, limite: int) -> list[dict]:
    """O que ainda não foi indexado. Mensagem vazia (resposta cortada no
    primeiro pedaço) não tem o que indexar."""
    tabela = _ORIGEM[tipo]
    linhas = _con().execute(
        f"SELECT o.id, o.texto FROM {tabela} o "
        f"LEFT JOIN vetores v ON v.tipo = ? AND v.ref = o.id "
        f"WHERE v.ref IS NULL AND o.texto != '' ORDER BY o.id LIMIT ?",
        (tipo, limite),
    )
    return [{**dict(l), 'texto': cofre.abrir(l['texto'])} for l in linhas]


def guardar_vetores(tipo: str, pares: list[tuple[int, bytes]]) -> None:
    with _con() as c:
        c.executemany(
            'INSERT OR REPLACE INTO vetores (tipo, ref, vetor) VALUES (?, ?, ?)',
            [(tipo, ref, vetor) for ref, vetor in pares],
        )


def vetores(tipo: str) -> list[tuple[int, bytes]]:
    return [(l['ref'], l['vetor']) for l in _con().execute('SELECT ref, vetor FROM vetores WHERE tipo = ?', (tipo,))]


def mensagens_por_id(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    marcas = ','.join('?' * len(ids))
    linhas = _con().execute(
        f'SELECT m.id, m.conversa, m.papel, m.texto, m.criada, m.privada, c.origem '
        f'FROM mensagens m JOIN conversas c ON c.id = m.conversa WHERE m.id IN ({marcas})',
        ids,
    )
    return [{**dict(l), 'texto': cofre.abrir(l['texto'])} for l in linhas]


def importadas_por_aprender() -> list[dict]:
    linhas = _con().execute(
        "SELECT id, origem, titulo, criada FROM conversas WHERE origem != 'solis' AND aprendida = 0 ORDER BY id"
    )
    return [dict(l) for l in linhas]


def marcar_aprendida(conversa: int) -> None:
    with _con() as c:
        c.execute('UPDATE conversas SET aprendida = 1 WHERE id = ?', (conversa,))


# — Conhecimento (os arquivos do Matheus) ————————————————————————————————————————

class Duplicado(Exception):
    """O mesmo arquivo (mesmo conteúdo) já está no Conhecimento."""

    def __init__(self, documento: int):
        super().__init__(documento)
        self.documento = documento


def adicionar_documento(
    nome: str, tipo: str, paginas: int | None, tamanho: int, hash_: str,
    trechos: list[tuple[int | None, str]], privado: bool = False, url: str | None = None,
) -> int:
    """Guarda o documento e os trechos (página, texto), ainda sem vetor."""
    existente = _con().execute('SELECT id FROM documentos WHERE hash = ?', (hash_,)).fetchone()
    if existente:
        raise Duplicado(existente['id'])
    selar = cofre.selar if privado else (lambda t: t)
    with _con() as c:
        doc = c.execute(
            'INSERT INTO documentos (nome, tipo, paginas, bytes, hash, privado, criado, url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (selar(nome), tipo, paginas, tamanho, hash_, int(privado), _agora(), selar(url) if url else None),
        ).lastrowid
        c.executemany(
            'INSERT INTO trechos (documento, ordem, pagina, texto) VALUES (?, ?, ?, ?)',
            [(doc, i, pagina, selar(texto)) for i, (pagina, texto) in enumerate(trechos)],
        )
    return doc


def documentos() -> list[dict]:
    """Do mais novo pro mais antigo, com quantos trechos têm e quantos já
    viraram vetor — a diferença é o "Indexando…" da tela."""
    linhas = _con().execute(
        'SELECT d.id, d.nome, d.tipo, d.paginas, d.bytes, d.privado, d.criado, d.url, '
        'COUNT(t.id) AS trechos, COUNT(t.vetor) AS indexados '
        'FROM documentos d LEFT JOIN trechos t ON t.documento = d.id '
        'GROUP BY d.id ORDER BY d.criado DESC, d.id DESC'
    )
    return [
        {**dict(l), 'nome': cofre.abrir(l['nome']), 'url': cofre.abrir(l['url']), 'privado': bool(l['privado'])}
        for l in linhas
    ]


def buscar_documentos(busca: str) -> list[dict]:
    """Os documentos cujo nome ou texto tem todas as palavras da busca (por
    prefixo, sem acento). O texto das privadas não está no índice: nelas vale
    só o nome."""
    palavras = re.findall(r'\w+', busca)
    todos = documentos()
    if not palavras:
        return todos
    consulta = ' '.join(f'"{p}"*' for p in palavras)
    pelo_texto = {
        l['documento']
        for l in _con().execute(
            'SELECT DISTINCT t.documento FROM trechos_fts JOIN trechos t ON t.id = trechos_fts.rowid '
            'WHERE trechos_fts MATCH ?',
            (consulta,),
        )
    }
    procuradas = [_sem_acento(p) for p in palavras]

    def no_nome(d):
        tem = re.findall(r'\w+', _sem_acento(d['nome']))
        return all(any(t.startswith(p) for t in tem) for p in procuradas)

    return [d for d in todos if d['id'] in pelo_texto or no_nome(d)]


def apagar_documento(documento: int) -> bool:
    with _con() as c:
        privado = c.execute('SELECT privado FROM documentos WHERE id = ?', (documento,)).fetchone()
        if privado is None:
            return False
        # Os trechos antes, à mão: o gatilho que tira do índice roda em cada um.
        c.execute('DELETE FROM trechos WHERE documento = ?', (documento,))
        c.execute('DELETE FROM documentos WHERE id = ?', (documento,))
    if privado['privado']:
        _limpar_rastros(_con())
    return True


def marcar_documento_privado(documento: int, privado: bool) -> bool:
    """Sela (ou abre) o nome e os trechos e tira (ou põe) o texto no índice."""
    l = _con().execute('SELECT nome, url, privado FROM documentos WHERE id = ?', (documento,)).fetchone()
    if l is None:
        return False
    if bool(l['privado']) == privado:
        return True
    trechos = _con().execute('SELECT id, texto FROM trechos WHERE documento = ?', (documento,)).fetchall()
    with _con() as c:
        if privado:
            c.execute(
                'UPDATE documentos SET privado = 1, nome = ?, url = ? WHERE id = ?',
                (cofre.selar(l['nome']), cofre.selar(l['url']), documento),
            )
            c.executemany('UPDATE trechos SET texto = ? WHERE id = ?', [(cofre.selar(t['texto']), t['id']) for t in trechos])
            c.executemany('DELETE FROM trechos_fts WHERE rowid = ?', [(t['id'],) for t in trechos])
        else:
            c.execute(
                'UPDATE documentos SET privado = 0, nome = ?, url = ? WHERE id = ?',
                (cofre.abrir(l['nome']), cofre.abrir(l['url']), documento),
            )
            abertos = [(t['id'], cofre.abrir(t['texto'])) for t in trechos]
            c.executemany('UPDATE trechos SET texto = ? WHERE id = ?', [(texto, i) for i, texto in abertos])
            c.executemany('INSERT INTO trechos_fts(rowid, texto) VALUES (?, ?)', abertos)
    if privado:
        _limpar_rastros(_con())
    return True


def trechos_sem_vetor(limite: int) -> list[dict]:
    linhas = _con().execute('SELECT id, texto FROM trechos WHERE vetor IS NULL ORDER BY id LIMIT ?', (limite,))
    return [{'id': l['id'], 'texto': cofre.abrir(l['texto'])} for l in linhas]


def guardar_vetores_trechos(pares: list[tuple[int, bytes]]) -> None:
    with _con() as c:
        c.executemany('UPDATE trechos SET vetor = ? WHERE id = ?', [(v, i) for i, v in pares])


def vetores_trechos() -> list[tuple[int, bytes]]:
    return [(l['id'], l['vetor']) for l in _con().execute('SELECT id, vetor FROM trechos WHERE vetor IS NOT NULL')]


def trechos_por_id(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    marcas = ','.join('?' * len(ids))
    linhas = _con().execute(
        f'SELECT t.id, t.documento, t.pagina, t.texto, d.nome, d.tipo, d.privado, d.url '
        f'FROM trechos t JOIN documentos d ON d.id = t.documento WHERE t.id IN ({marcas})',
        ids,
    )
    return [
        {**dict(l), 'texto': cofre.abrir(l['texto']), 'nome': cofre.abrir(l['nome']), 'url': cofre.abrir(l['url']),
         'privado': bool(l['privado'])}
        for l in linhas
    ]


def tem_vetores() -> bool:
    c = _con()
    return bool(
        c.execute('SELECT 1 FROM vetores LIMIT 1').fetchone()
        or c.execute('SELECT 1 FROM trechos WHERE vetor IS NOT NULL LIMIT 1').fetchone()
    )


def apagar_vetores() -> None:
    """Todos os vetores, de memória, mensagem e trecho — pra serem refeitos por
    outro modelo de embeddings. Nenhum texto é tocado."""
    with _con() as c:
        c.execute('DELETE FROM vetores')
        c.execute('UPDATE trechos SET vetor = NULL')
