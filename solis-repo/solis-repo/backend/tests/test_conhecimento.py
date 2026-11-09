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
