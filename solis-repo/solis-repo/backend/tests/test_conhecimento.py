"""Conhecimento: arquivos viram trechos, trechos viram vetores, e os mais ligados
à mensagem entram no pedido — com o privado fora da nuvem."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from solis import banco, busca, cofre, conhecimento, main, ollama, roteador

ASSUNTOS = ['tauri', 'sqlite', 'receita', 'exame']


def vetor(texto: str) -> list[float]:
    t = texto.lower()
    return [float(t.count(a)) for a in ASSUNTOS] + [0.1]


@pytest.fixture
def embeddings_falsos(monkeypatch):
    async def falso(modelo, textos):
        return [vetor(t) for t in textos]
    monkeypatch.setattr(ollama, 'embeddings', falso)


def pdf_com(*paginas: str) -> bytes:
    """Um PDF de verdade, mínimo, com uma linha de texto por página — escrito à
    mão pra o teste não depender de gerador nenhum."""
    objetos = ['<< /Type /Catalog /Pages 2 0 R >>', None, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    filhos = []
    for texto in paginas:
        conteudo = f'BT /F1 12 Tf 72 720 Td ({texto}) Tj ET'.encode('latin-1')
        objetos.append(f'<< /Length {len(conteudo)} >>\nstream\n'.encode('latin-1') + conteudo + b'\nendstream')
        n_conteudo = len(objetos)
        objetos.append(
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
            f'/Resources << /Font << /F1 3 0 R >> >> /Contents {n_conteudo} 0 R >>'
        )
        filhos.append(f'{len(objetos)} 0 R')
    objetos[1] = f'<< /Type /Pages /Kids [{" ".join(filhos)}] /Count {len(filhos)} >>'
    saida, posicoes = bytearray(b'%PDF-1.4\n'), []
    for i, obj in enumerate(objetos, 1):
        posicoes.append(len(saida))
        corpo = obj if isinstance(obj, bytes) else obj.encode('latin-1')
        saida += f'{i} 0 obj\n'.encode() + corpo + b'\nendobj\n'
    xref = len(saida)
    saida += f'xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n'.encode()
    saida += b''.join(f'{p:010d} 00000 n \n'.encode() for p in posicoes)
    saida += f'trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return bytes(saida)


# --- ler e cortar ------------------------------------------------------------

def test_corta_em_janelas_com_sobra():
    palavras = [f'p{i}' for i in range(450)]
    trechos = conhecimento.cortar(' '.join(palavras))
    assert [len(t.split()) for t in trechos] == [200, 200, 130]
    # A emenda aparece nos dois: as 40 últimas de um são as 40 primeiras do próximo.
    assert trechos[0].split()[-40:] == trechos[1].split()[:40]
    assert conhecimento.cortar('curto demais') == ['curto demais']
    assert conhecimento.cortar('   ') == []


def test_le_pdf_com_a_pagina_de_cada_trecho():
    tipo, paginas, trechos = conhecimento.ler('guia.pdf', pdf_com('Tauri sobe o servidor', 'SQLite guarda tudo'))
    assert (tipo, paginas) == ('pdf', 2)
    assert trechos == [(1, 'Tauri sobe o servidor'), (2, 'SQLite guarda tudo')]


def test_pdf_sem_texto_e_recusado_dizendo_por_que():
    from pypdf import PdfWriter
    import io
    w = PdfWriter()
    w.add_blank_page(612, 792)
    buf = io.BytesIO()
    w.write(buf)
    with pytest.raises(conhecimento.NaoLeu, match='escaneado'):
        conhecimento.ler('scan.pdf', buf.getvalue())
    with pytest.raises(conhecimento.NaoLeu, match='corrompido'):
        conhecimento.ler('falso.pdf', b'isto nao e pdf')


def test_le_texto_em_utf8_e_em_windows_1252():
    assert conhecimento.ler('a.md', '# Receita\n\nAçúcar'.encode('utf-8'))[2] == [(None, '# Receita Açúcar')]
    assert conhecimento.ler('b.txt', 'Feijão'.encode('cp1252'))[2] == [(None, 'Feijão')]
    with pytest.raises(conhecimento.NaoLeu, match='PDF, .md e .txt'):
        conhecimento.ler('planilha.xlsx', b'x')
    with pytest.raises(conhecimento.NaoLeu, match='vazio'):
        conhecimento.ler('vazio.txt', b'  \n ')


# --- rotas -------------------------------------------------------------------

def test_adicionar_listar_e_nao_duplicar(embeddings_falsos):
    cliente = TestClient(main.app)
    r = cliente.post('/conhecimento?nome=Guia%20do%20Tauri.pdf', content=pdf_com('Tauri e Rust', 'Tauri no Windows'))
    doc = r.json()['documento']
    assert (doc['nome'], doc['tipo'], doc['paginas'], doc['trechos'], doc['privado']) == ('Guia do Tauri.pdf', 'pdf', 2, 2, False)
    # O vetor sai em segundo plano (no TestClient, logo depois da resposta).
    assert cliente.get('/conhecimento').json()['documentos'][0]['indexados'] == 2

    r = cliente.post('/conhecimento?nome=outro%20nome.pdf', content=pdf_com('Tauri e Rust', 'Tauri no Windows'))
    assert (r.status_code, r.json()) == (409, {'erro': 'ja_existe', 'documento': doc['id']})

    r = cliente.post('/conhecimento?nome=foto.png', content=b'\x89PNG')
    assert (r.status_code, r.json()['erro']) == (400, 'nao_leu')


def test_varios_arquivos_ao_mesmo_tempo_entram_todos_inteiros():
    """Seis de uma vez (o "Adicionar fonte" com vários arquivos): antes, cada
    um escrevia no banco de uma thread e as transações se embaralhavam."""
    import httpx

    async def manda():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://t') as c:
            return await asyncio.gather(*(
                c.post('/conhecimento', params={'nome': f'doc{i}.pdf'}, content=pdf_com(*[f'documento {i} pagina {p}' for p in range(1, 6)]))
                for i in range(6)
            ))
    respostas = asyncio.run(manda())
    assert [r.status_code for r in respostas] == [200] * 6
    assert sorted((d['nome'], d['trechos']) for d in banco.documentos()) == [(f'doc{i}.pdf', 5) for i in range(6)]


def test_busca_pelo_texto_e_pelo_nome_sem_acento():
    cliente = TestClient(main.app)
    cliente.post('/conhecimento?nome=Anotações.md', content='O índice FTS5 do SQLite'.encode())
    cliente.post('/conhecimento?nome=receitas.txt', content=b'bolo de cenoura')
    nomes = lambda q: [d['nome'] for d in cliente.get('/conhecimento', params={'q': q}).json()['documentos']]
    assert nomes('indic sqli') == ['Anotações.md']
    assert nomes('anotacoes') == ['Anotações.md']
    assert nomes('cenoura') == ['receitas.txt']
    assert nomes('') == ['receitas.txt', 'Anotações.md']


def test_apagar_tira_os_trechos_e_o_indice():
    cliente = TestClient(main.app)
    doc = cliente.post('/conhecimento?nome=a.txt', content=b'texto unico zebra').json()['documento']
    assert cliente.delete(f'/conhecimento/{doc["id"]}').json() == {'ok': True}
    assert cliente.get('/conhecimento', params={'q': 'zebra'}).json()['documentos'] == []
    assert banco._con().execute('SELECT COUNT(*) FROM trechos').fetchone()[0] == 0
    assert cliente.delete(f'/conhecimento/{doc["id"]}').status_code == 404


# --- o que vai no pedido -----------------------------------------------------

def test_trecho_do_arquivo_entra_no_pedido_com_nome_e_pagina(embeddings_falsos):
    cliente = TestClient(main.app)
    cliente.post('/conhecimento?nome=Tauri.pdf', content=pdf_com('nada aqui', 'o tauri empacota com msi'))
    cliente.post('/conhecimento?nome=bolo.txt', content=b'receita de bolo')
    memorias, trechos = asyncio.run(busca.contexto('como o tauri empacota?', 0))
    arquivos = [t for t in trechos if t.get('arquivo')]
    assert [(a['nome'], a['pagina']) for a in arquivos] == [('Tauri.pdf', 2)]
    texto = ollama.contexto(memorias, trechos)
    assert '[Tauri.pdf, pág. 2] o tauri empacota com msi' in texto
    assert 'Trechos de conversas antigas' not in texto  # não há conversa, só arquivo


def test_fonte_privada_selada_fora_do_indice_e_da_nuvem(embeddings_falsos, tmp_path):
    cliente = TestClient(main.app)
    doc = cliente.post('/conhecimento?nome=exame-sangue.pdf&privado=true', content=pdf_com('exame de sangue normal')).json()['documento']
    assert doc['privado'] and doc['nome'] == 'exame-sangue.pdf'
    if cofre.DISPONIVEL:
        banco._con().execute('PRAGMA wal_checkpoint(TRUNCATE)')
        bruto = (tmp_path / 'solis.db').read_bytes()
        assert b'exame-sangue' not in bruto and b'de sangue normal' not in bruto
    # O texto não é buscável; o nome é.
    assert cliente.get('/conhecimento', params={'q': 'normal'}).json()['documentos'] == []
    assert len(cliente.get('/conhecimento', params={'q': 'exame'}).json()['documentos']) == 1
    # Vai pro modelo local, nunca pra nuvem.
    memorias, trechos = asyncio.run(busca.contexto('meu exame', 0))
    assert any(t.get('arquivo') for t in trechos)
    nuvem = roteador.prompt_nuvem(memorias, [t for t in trechos if not t['privada']], None, [{'papel': 'pessoa', 'texto': 'x', 'privada': False}], 'x')
    assert 'sangue' not in nuvem

    # Deixar de ser privada devolve ao índice.
    r = cliente.patch(f'/conhecimento/{doc["id"]}', json={'privado': False})
    assert r.json()['documento']['privado'] is False
    assert len(cliente.get('/conhecimento', params={'q': 'normal'}).json()['documentos']) == 1
    cliente.patch(f'/conhecimento/{doc["id"]}', json={'privado': True})
    assert cliente.get('/conhecimento', params={'q': 'normal'}).json()['documentos'] == []


# --- página web --------------------------------------------------------------

import httpx  # noqa: E402

PAGINA = '''<html><head><title>Arquitetura de sistemas locais ¶</title></head><body>
<nav><a href="/">Início</a> <a href="/blog">Blog</a> Menu que não importa</nav>
<article><h1>Arquitetura de sistemas locais</h1>
<p>Um sistema local-first guarda os dados no aparelho da pessoa e sincroniza quando dá.
O tauri empacota o app e sobe o servidor local junto, sem nada exposto na rede.</p>
<p>O banco SQLite fica num arquivo só, e a busca de texto usa o FTS5 com remove_diacritics.</p>
</article><footer>© 2026 Todos os direitos reservados · Política de cookies</footer></body></html>'''


def site(rotas: dict):
    def responde(req):
        corpo = rotas.get(str(req.url))
        if corpo is None:
            return httpx.Response(404)
        tipo, dados = corpo
        return httpx.Response(200, headers={'content-type': tipo}, content=dados)
    return httpx.MockTransport(responde)


def adicionar_pagina(url, rotas, privado=False):
    async def faz():
        final, tipo, dados = await conhecimento.baixar(url, site(rotas))
        nome, lido = conhecimento.preparar_pagina(final, tipo, dados)
        return conhecimento.guardar(nome, lido, privado)
    return asyncio.run(faz())


def test_pagina_entra_so_com_o_conteudo_principal(embeddings_falsos):
    rotas = {'https://exemplo.dev/arquitetura': ('text/html; charset=utf-8', PAGINA.encode())}
    # Colado sem o https:// também vale.
    adicionar_pagina('exemplo.dev/arquitetura', rotas)
    [d] = banco.documentos()
    assert (d['nome'], d['tipo'], d['url']) == ('Arquitetura de sistemas locais', 'web', 'https://exemplo.dev/arquitetura')
    texto = ' '.join(t['texto'] for t in banco.trechos_por_id([r[0] for r in banco._con().execute('SELECT id FROM trechos')]))
    assert 'local-first' in texto and 'FTS5' in texto
    assert 'Menu que não importa' not in texto and 'Política de cookies' not in texto

    # A mesma página de novo não entra.
    with pytest.raises(banco.Duplicado):
        adicionar_pagina('https://exemplo.dev/arquitetura', rotas)

    # Na resposta, a fonte vai com o endereço.
    asyncio.run(busca.indexar_pendentes())
    _, trechos = asyncio.run(busca.contexto('o tauri e o sqlite no sistema local', 0))
    assert '[Arquitetura de sistemas locais, https://exemplo.dev/arquitetura]' in ollama.contexto([], trechos)


def test_endereco_de_pdf_entra_como_pdf():
    rotas = {'https://exemplo.dev/docs/Guia%20Tauri.pdf': ('application/pdf', pdf_com('tauri pagina um', 'tauri pagina dois'))}
    adicionar_pagina('https://exemplo.dev/docs/Guia%20Tauri.pdf', rotas)
    [d] = banco.documentos()
    assert (d['nome'], d['tipo'], d['paginas']) == ('Guia Tauri.pdf', 'pdf', 2)


@pytest.mark.parametrize('url, rotas, motivo', [
    ('ftp://x', {}, 'precisa ser de uma página'),
    ('https://exemplo.dev/sumiu', {}, 'respondeu 404'),
    ('https://exemplo.dev/foto.png', {'https://exemplo.dev/foto.png': ('image/png', b'\x89PNG')}, 'nem um PDF'),
    ('https://exemplo.dev/js', {'https://exemplo.dev/js': ('text/html', b'<html><body><div id="app"></div><script>x()</script></body></html>')}, 'JavaScript'),
])
def test_pagina_recusada_diz_por_que(url, rotas, motivo):
    with pytest.raises(conhecimento.NaoLeu, match=motivo):
        adicionar_pagina(url, rotas)
    assert banco.documentos() == []


def test_rota_da_pagina(monkeypatch):
    async def baixa(url, transporte=None):
        conhecimento._endereco(url)  # a mesma validação do de verdade
        return 'https://exemplo.dev/arquitetura', 'text/html', PAGINA.encode()
    monkeypatch.setattr(conhecimento, 'baixar', baixa)
    cliente = TestClient(main.app)
    r = cliente.post('/conhecimento/pagina', json={'url': 'https://exemplo.dev/arquitetura', 'privado': True})
    d = r.json()['documento']
    assert (d['tipo'], d['url'], d['privado']) == ('web', 'https://exemplo.dev/arquitetura', True)
    if cofre.DISPONIVEL:  # o endereço de uma página privada também fica selado
        assert cofre.selado(banco._con().execute('SELECT url FROM documentos').fetchone()[0])
    assert cliente.post('/conhecimento/pagina', json={'url': 'x'}).json()['erro'] == 'nao_leu'
    assert cliente.post('/conhecimento/pagina', json={'url': 'https://exemplo.dev/arquitetura'}).status_code == 409


def test_migracao_9_preserva_arquivos_indice_e_vetores(tmp_path):
    """Recriar documentos e trechos (pra aceitar 'web') não pode perder nada."""
    import sqlite3
    caminho = tmp_path / 'v8.db'
    c = sqlite3.connect(caminho)
    c.executescript(banco.ESQUEMA)
    for i, sql in enumerate(banco.MIGRACOES[:8], start=1):
        c.executescript(f'BEGIN; {sql} PRAGMA user_version = {i}; COMMIT;')
    c.execute("INSERT INTO documentos (id, nome, tipo, paginas, bytes, hash, privado, criado) VALUES (7, 'a.pdf', 'pdf', 1, 10, 'h', 0, 'x')")
    c.execute("INSERT INTO trechos (id, documento, ordem, pagina, texto, vetor) VALUES (42, 7, 0, 1, 'zebra listrada', X'00')")
    c.commit()
    c.close()

    banco.usar(caminho)
    assert banco._con().execute('PRAGMA user_version').fetchone()[0] == len(banco.MIGRACOES)
    [d] = banco.documentos()
    assert (d['id'], d['nome'], d['trechos'], d['indexados'], d['url']) == (7, 'a.pdf', 1, 1, None)
    assert [x['nome'] for x in banco.buscar_documentos('zebra')] == ['a.pdf']  # o índice continua
    destino = {l['table'] for l in banco._con().execute('PRAGMA foreign_key_list(trechos)')}
    assert destino == {'documentos'}
    assert banco.apagar_documento(7) and banco._con().execute('SELECT COUNT(*) FROM trechos_fts').fetchone()[0] == 0
