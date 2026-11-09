"""PDF escaneado: as páginas-imagem entram numa fila, o OCR lê em segundo plano,
e cada página lida vira trechos como os de qualquer PDF."""
import asyncio
import io
import json
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from solis import banco, busca, cofre, conhecimento, main, ocr, ollama

from test_conhecimento import pdf_com, vetor

WINDOWS_DE_VERDADE = ocr.windows  # antes do conftest trocar pelo falso


def imagem_com(texto: str) -> Image.Image:
    img = Image.new('L', (1240, 1754), 255)
    try:
        fonte = ImageFont.truetype('arial.ttf', 40)
    except OSError:
        fonte = ImageFont.load_default(size=40)
    ImageDraw.Draw(img).text((120, 200), texto, font=fonte, fill=0)
    return img


def escaneado(*paginas: str) -> bytes:
    """Um PDF só de imagem, como sai de um scanner."""
    primeira, *resto = [imagem_com(t).convert('RGB') for t in paginas]
    saida = io.BytesIO()
    primeira.save(saida, 'PDF', save_all=True, append_images=resto, resolution=150)
    return saida.getvalue()


def misto() -> bytes:
    """Página 1 com texto, página 2 escaneada."""
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    w.add_page(PdfReader(io.BytesIO(pdf_com('Tauri sobe o servidor'))).pages[0])
    w.add_page(PdfReader(io.BytesIO(escaneado('contrato de aluguel'))).pages[0])
    saida = io.BytesIO()
    w.write(saida)
    return saida.getvalue()


@pytest.fixture
def visao_falsa(monkeypatch):
    """O modelo de visão "lê" devolvendo o tamanho da imagem — o bastante pra
    saber que a página certa foi renderizada e mandada."""
    lidas = []

    async def instalados():
        return {ocr.MODELO_VISAO, 'embeddinggemma:latest'}

    async def ler(modelo, png, instrucao):
        lidas.append(Image.open(io.BytesIO(png)).size)
        return f'texto lido da página {len(lidas)} sobre sqlite', False

    async def embeddings(modelo, textos):
        return [vetor(t) for t in textos]
    monkeypatch.setattr(ollama, 'instalados', instalados)
    monkeypatch.setattr(ollama, 'ler_imagem', ler)
    monkeypatch.setattr(ollama, 'embeddings', embeddings)
    return lidas


def test_pagina_escaneada_vai_pra_fila_e_a_com_texto_le_direto():
    tipo, paginas, trechos, fila = conhecimento.ler('misto.pdf', misto())
    assert (tipo, paginas) == ('pdf', 2)
    assert trechos == [(1, 'Tauri sobe o servidor')]
    assert fila == [2]
    assert conhecimento.ler('scan.pdf', escaneado('a', 'b'))[2:] == ([], [1, 2])


def test_pdf_escaneado_entra_na_hora_e_e_lido_em_segundo_plano(visao_falsa):
    cliente = TestClient(main.app)
    doc = cliente.post('/conhecimento?nome=scan.pdf', content=escaneado('um', 'dois')).json()['documento']
    assert (doc['escaneadas'], doc['lidas'], doc['trechos']) == (2, 0, 0)

    # O upload já pôs a leitura pra rodar em segundo plano (o TestClient roda as
    # tarefas de fundo logo depois da resposta): não sobra nada na fila.
    assert asyncio.run(ocr.ler_pendentes()) == 0
    # A página foi renderizada a 150 dpi: A4 de 8,27 polegadas = 1240 px.
    assert all(w in (1240, 1241) for w, _ in visao_falsa) and len(visao_falsa) == 2
    d = cliente.get('/conhecimento').json()['documentos'][0]
    assert (d['escaneadas'], d['lidas'], d['trechos']) == (2, 2, 2)
    assert [t['pagina'] for t in banco.trechos_por_id([1, 2])] == [1, 2]
    # O original sai do banco com a última página.
    assert banco._con().execute('SELECT original, faltam FROM documentos').fetchone()[:] == (None, None)
    assert banco.escaneado_pendente() is None


def test_misto_le_so_a_pagina_escaneada(visao_falsa):
    conhecimento.adicionar('misto.pdf', misto())
    asyncio.run(ocr.ler_pendentes())
    assert len(visao_falsa) == 1
    linhas = banco._con().execute('SELECT ordem, pagina FROM trechos ORDER BY ordem').fetchall()
    assert [tuple(l) for l in linhas] == [(0, 1), (1, 2)]


def test_ollama_fora_a_fila_espera_sem_cair_pro_windows(monkeypatch):
    usou_windows = []

    async def windows(png):
        usou_windows.append(1)
        return 'lido mal'
    monkeypatch.setattr(ocr, 'windows', windows)
    conhecimento.adicionar('scan.pdf', escaneado('um'))
    assert asyncio.run(ocr.ler_pendentes()) == 0  # conftest: Ollama fora
    assert ocr.parado == 'ollama' and not usou_windows
    cliente = TestClient(main.app)
    d = cliente.get('/conhecimento').json()['documentos'][0]
    assert (d['lidas'], d['leitura_parada']) == (0, 'ollama')


def test_sem_modelo_de_visao_le_pelo_windows(monkeypatch):
    async def instalados():
        return {'llama3.2:3b'}

    async def windows(png):
        assert Image.open(io.BytesIO(png)).size[0] in (2480, 2481)  # 300 dpi (o PDFium arredonda pra cima)
        return 'Contrato de\nlocação'
    monkeypatch.setattr(ollama, 'instalados', instalados)
    monkeypatch.setattr(ocr, 'windows', windows)
    conhecimento.adicionar('scan.pdf', escaneado('um'))
    assert asyncio.run(ocr.ler_pendentes()) == 1
    assert banco.trechos_por_id([1])[0]['texto'] == 'Contrato de locação'


def test_modelo_que_repete_ate_o_limite_cai_pro_windows(monkeypatch, visao_falsa):
    async def repete(modelo, png, instrucao):
        return 'contrato ' * 4096, True

    async def windows(png):
        return 'contrato de aluguel'
    monkeypatch.setattr(ollama, 'ler_imagem', repete)
    monkeypatch.setattr(ocr, 'windows', windows)
    conhecimento.adicionar('scan.pdf', escaneado('um'))
    asyncio.run(ocr.ler_pendentes())
    assert banco.trechos_por_id([1])[0]['texto'] == 'contrato de aluguel'


def test_pagina_sem_texto_nao_vira_trecho(monkeypatch, visao_falsa):
    async def vazia(modelo, png, instrucao):
        return ' [sem texto] ', False
    monkeypatch.setattr(ollama, 'ler_imagem', vazia)
    conhecimento.adicionar('scan.pdf', escaneado('um'))
    assert asyncio.run(ocr.ler_pendentes()) == 1
    d = banco.documentos()[0]
    assert (d['lidas'], d['trechos']) == (1, 0)


def test_privado_tem_o_original_e_o_texto_lido_selados(visao_falsa, tmp_path):
    doc = conhecimento.adicionar('exame.pdf', escaneado('exame'), privado=True)
    original = banco._con().execute('SELECT original FROM documentos').fetchone()[0]
    if cofre.DISPONIVEL:
        assert cofre.selado(original)
    asyncio.run(ocr.ler_pendentes())
    texto = banco._con().execute('SELECT texto FROM trechos').fetchone()[0]
    if cofre.DISPONIVEL:
        assert cofre.selado(texto)
    assert banco._con().execute('SELECT COUNT(*) FROM trechos_fts').fetchone()[0] == 0
    assert banco.trechos_por_id([1])[0]['documento'] == doc


def test_mudar_pra_privado_no_meio_sela_o_que_ainda_vai_ser_lido(visao_falsa):
    doc = conhecimento.adicionar('scan.pdf', escaneado('um', 'dois'))
    original = asyncio.run(_ler_uma_e_marcar(doc))
    if cofre.DISPONIVEL:
        assert cofre.selado(original)
    textos = [l[0] for l in banco._con().execute('SELECT texto FROM trechos ORDER BY ordem')]
    if cofre.DISPONIVEL:
        assert all(cofre.selado(t) for t in textos)


async def _ler_uma_e_marcar(doc):
    pendente = banco.escaneado_pendente()
    banco.guardar_pagina_lida(doc, pendente['faltam'][0], ['primeira'])
    banco.marcar_documento_privado(doc, True)
    original = banco._con().execute('SELECT original FROM documentos').fetchone()[0]
    await ocr.ler_pendentes()
    return original


def test_removido_no_meio_da_leitura_para_sem_erro(monkeypatch, visao_falsa):
    doc = conhecimento.adicionar('scan.pdf', escaneado('um', 'dois'))

    async def le_e_some(modelo, png, instrucao):
        banco.apagar_documento(doc)
        return 'texto', False
    monkeypatch.setattr(ollama, 'ler_imagem', le_e_some)
    assert asyncio.run(ocr.ler_pendentes()) == 0
    assert banco.documentos() == [] and banco._con().execute('SELECT COUNT(*) FROM trechos').fetchone()[0] == 0


def test_leitura_nao_roda_duas_ao_mesmo_tempo(monkeypatch, visao_falsa):
    async def devagar(modelo, png, instrucao):
        await asyncio.sleep(0.05)
        return 'texto', False
    monkeypatch.setattr(ollama, 'ler_imagem', devagar)
    conhecimento.adicionar('scan.pdf', escaneado('um'))

    async def duas():
        return await asyncio.gather(ocr.ler_se_livre(), ocr.ler_se_livre())
    assert sorted(asyncio.run(duas())) == [0, 1]


def test_original_ilegivel_sai_da_fila():
    conhecimento.adicionar('scan.pdf', escaneado('um'))
    banco._con().execute("UPDATE documentos SET original = 'cofre:v1:quebrado'")
    banco._con().commit()
    assert banco.escaneado_pendente() is None
    assert banco.documentos()[0]['lidas'] == 1


def test_migracao_10_mantem_os_documentos(tmp_path):
    caminho = tmp_path / 'velho.db'
    banco.usar(caminho)
    conhecimento.adicionar('a.txt', b'tauri e sqlite')
    c = banco._con()
    for coluna in ('escaneadas', 'faltam', 'original'):
        c.execute(f'ALTER TABLE documentos DROP COLUMN {coluna}')
    c.execute('PRAGMA user_version = 9')
    c.commit()
    banco.usar(caminho)
    d = banco.documentos()[0]
    assert (d['nome'], d['escaneadas'], d['lidas'], d['trechos']) == ('a.txt', 0, 0, 1)


@pytest.mark.skipif(os.name != 'nt', reason='o OCR de reserva é o do Windows')
def test_ocr_do_windows_de_verdade():
    saida = io.BytesIO()
    imagem_com('Contrato de locação residencial').save(saida, 'PNG')
    try:
        texto = asyncio.run(WINDOWS_DE_VERDADE(saida.getvalue()))
    except ocr.SemLeitor as e:
        pytest.skip(f'sem OCR neste Windows: {e}')
    assert 'Contrato de locação residencial' in ' '.join(texto.split())


def test_fila_guarda_as_paginas_em_json():
    conhecimento.adicionar('scan.pdf', escaneado('a', 'b', 'c'))
    assert json.loads(banco._con().execute('SELECT faltam FROM documentos').fetchone()[0]) == [1, 2, 3]


def test_indexa_so_depois_de_ler_tudo(monkeypatch, visao_falsa):
    """Indexar entre as páginas deixava o OCR 2,5× mais lento (GPU disputada)."""
    vetores_durante = []

    async def ler(modelo, png, instrucao):
        await busca.indexar_se_livre()  # a tela pede isto a cada 1,5 s
        vetores_durante.append(banco._con().execute('SELECT COUNT(vetor) FROM trechos').fetchone()[0])
        return 'texto sobre sqlite', False
    monkeypatch.setattr(ollama, 'ler_imagem', ler)
    conhecimento.adicionar('scan.pdf', escaneado('um', 'dois'))
    assert asyncio.run(ocr.ler_se_livre()) == 2
    assert vetores_durante == [0, 0]
    d = banco.documentos()[0]
    assert d['indexados'] == d['trechos'] == 2
