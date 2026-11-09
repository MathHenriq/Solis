"""OCR: o texto das páginas escaneadas, lido em segundo plano.

Um PDF escaneado entra na hora (conhecimento.ler põe as páginas-imagem numa
fila) e as páginas são lidas aqui, uma de cada vez. Cada página lida vira
trechos como os de qualquer PDF, e a indexação pega dali.

Quem lê, escolhido medindo (09/11/2026): 3 páginas com texto conhecido
(português em Arial e Times, inglês), num PDF só de imagem, em dois níveis:
digitalização boa (200 dpi) e ruim (150 dpi, letra de 10 pt, 2° torta,
desfocada, JPEG forte). Acerto por palavra:

    leitor               boa              ruim             tempo por página
    OCR do Windows       0,98 a 1,00      0,30 a 0,80      0,6 a 0,8 s, CPU
    qwen3.5:9b (visão)   1,00             1,00             8 a 26 s, GPU
    gemma3:12b (visão)   0,99 a 1,00      (não medido)     18 a 40 s, GPU

O OCR do Windows é ótimo na digitalização boa e desaba na ruim ("acompanhamento"
vira "accynpanhamento"; o contrato em Times sai quase todo ilegível). Também não
dá pra saber, sem o texto certo, quando ele errou: o sinal barato medido
(palavra com caractere estranho) dava 0,9 % numa página com 21 % de erro. Por
isso o modelo de visão lê tudo, e o OCR do Windows é a reserva: quando o modelo
de visão não está instalado, ou quando ele se perde e repete até o limite.

O Ollama fora não é motivo pra cair pro Windows: a página ficaria lida pior pra
sempre, e sem o Ollama não há vetor mesmo. A fila espera, como a indexação.
"""
import asyncio
import base64
import io
import logging
import os
import subprocess
from pathlib import Path

from . import banco, busca, conhecimento, ollama

log = logging.getLogger('solis.ocr')

MODELO_VISAO = os.environ.get('SOLIS_MODELO_VISAO', 'qwen3.5:9b')
# Resolução de cada leitor, medida: o modelo de visão leu tudo a 150 dpi (e
# mais pixel é mais token de imagem, mais lento); o Windows foi melhor a 300 na
# digitalização ruim (0,79 contra 0,70 a 150) e passa a errar mais a 400.
DPI_VISAO = 150
DPI_WINDOWS = 300
INSTRUCAO = (
    'Transcreva exatamente todo o texto desta imagem, na ordem de leitura, sem comentar nada. '
    'Se não houver texto, responda só: [sem texto]'
)
SEM_TEXTO = '[sem texto]'
SCRIPT = Path(__file__).with_name('ocr_windows.ps1')
TEMPO_WINDOWS = 60


class SemLeitor(Exception):
    """Nem o modelo de visão nem o OCR do Windows conseguem ler."""


# O que a tela mostra quando a fila não anda: None (andando ou vazia),
# 'ollama' (fora) ou 'ocr' (nada lê neste computador).
parado: str | None = None


def renderizar(pdf, pagina: int, dpi: int) -> bytes:
    """A página (1 = primeira) como PNG em tons de cinza."""
    imagem = pdf[pagina - 1].render(scale=dpi / 72, grayscale=True).to_pil()
    saida = io.BytesIO()
    imagem.save(saida, 'PNG')
    return saida.getvalue()


async def windows(png: bytes) -> str:
    if os.name != 'nt':
        raise SemLeitor('o OCR de reserva é o do Windows')
    try:
        proc = await asyncio.create_subprocess_exec(
            'powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        saida, erro = await asyncio.wait_for(proc.communicate(base64.b64encode(png)), TEMPO_WINDOWS)
    except (OSError, asyncio.TimeoutError) as e:
        raise SemLeitor(f'o OCR do Windows não rodou: {e}') from e
    if proc.returncode:
        raise SemLeitor(f'o OCR do Windows falhou: {erro.decode("utf-8", "replace").strip()[:200]}')
    return saida.decode('utf-8', 'replace')


async def _tem_visao() -> bool:
    """O modelo de visão está instalado? OllamaIndisponivel passa pra cima."""
    nomes = await ollama.instalados()
    return MODELO_VISAO in nomes or f'{MODELO_VISAO}:latest' in nomes


async def ler_pagina(pdf, pagina: int, visao: bool) -> tuple[str, str]:
    """(texto, quem leu). OllamaIndisponivel passa pra cima: a fila espera."""
    if visao:
        png = await asyncio.to_thread(renderizar, pdf, pagina, DPI_VISAO)
        try:
            texto, cortado = await ollama.ler_imagem(MODELO_VISAO, png, INSTRUCAO)
        except ollama.ModeloInexistente:
            cortado, texto = True, ''
        if not cortado:
            return ('' if texto.strip() == SEM_TEXTO else texto), MODELO_VISAO
        # Bateu no limite de saída: o modelo entrou em repetição. O Windows
        # não inventa — no pior caso lê mal.
        log.warning('o %s não terminou a página %d; lendo pelo Windows', MODELO_VISAO, pagina)
    png = await asyncio.to_thread(renderizar, pdf, pagina, DPI_WINDOWS)
    return await windows(png), 'windows'


async def ler_pendentes() -> int:
    """Lê as páginas escaneadas que faltam. Devolve quantas leu."""
    global parado
    import pypdfium2 as pdfium

    lidas = 0
    while (doc := banco.escaneado_pendente()) is not None:
        try:
            visao = await _tem_visao()
        except ollama.OllamaIndisponivel:
            parado = 'ollama'
            log.info('Ollama fora; %d páginas escaneadas ficam pra depois', len(doc['faltam']))
            return lidas
        try:
            pdf = await asyncio.to_thread(pdfium.PdfDocument, doc['original'])
        except pdfium.PdfiumError as e:
            # A pypdf abriu, o PDFium não: as páginas saem da fila sem texto,
            # senão a fila tentaria este documento pra sempre.
            log.error('documento %d: o PDFium não abriu o PDF (%s)', doc['id'], e)
            for pagina in doc['faltam']:
                banco.guardar_pagina_lida(doc['id'], pagina, [])
            continue
        try:
            for pagina in doc['faltam']:
                try:
                    texto, leitor = await ler_pagina(pdf, pagina, visao)
                except ollama.OllamaIndisponivel:
                    parado = 'ollama'
                    return lidas
                except SemLeitor as e:
                    parado = 'ocr'
                    log.error('página %d do documento %d sem leitor: %s', pagina, doc['id'], e)
                    return lidas
                trechos = conhecimento.cortar(conhecimento._limpo(texto))
                if not banco.guardar_pagina_lida(doc['id'], pagina, trechos):
                    break  # removido no meio da leitura
                parado = None
                lidas += 1
                log.info('documento %d, página %d: %d trechos (%s)', doc['id'], pagina, len(trechos), leitor)
        finally:
            pdf.close()
    return lidas


_lendo = asyncio.Lock()


async def ler_se_livre() -> int:
    """ler_pendentes, a menos que já esteja rodando (a tela pede a cada 1,5 s).
    Indexa só no fim: enquanto o OCR lê, os trechos de arquivo esperam (lendo())."""
    if _lendo.locked():
        return 0
    async with _lendo:
        lidas = await ler_pendentes()
    if lidas:
        await busca.indexar_se_livre()
    return lidas


def lendo() -> bool:
    """O OCR está lendo agora. Indexar ao mesmo tempo deixa o OCR 2,5× mais
    lento (16 s contra 6 a 7 s por página, medido): o modelo de embeddings e o de
    visão disputam a GPU a cada página. Por isso busca.indexar_pendentes deixa
    os trechos de arquivo pra depois enquanto isto for verdade."""
    return _lendo.locked()
