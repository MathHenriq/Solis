"""Conhecimento: os arquivos que o Matheus entrega pro Solis ler.

Cada arquivo vira texto, o texto é cortado em trechos, e cada trecho vira um
vetor (busca.indexar_pendentes) — o mesmo caminho das memórias. Na hora de
responder, os trechos mais ligados à mensagem entram no pedido com o nome do
arquivo e a página.

Formatos: PDF (pela pypdf, Python puro), texto (.md, .txt) e página web (pela
trafilatura, que tira só o conteúdo principal — sem menu, rodapé e anúncio; o
parser HTML da biblioteca padrão traria tudo junto). PDF escaneado não tem
texto — é imagem — e sem OCR não há o que ler: é recusado com esse motivo, em
vez de entrar vazio.

O arquivo original não é copiado: fica onde está. O Solis guarda o texto
extraído, que é o que ele usa.
"""
import hashlib
import io
import re
from pathlib import PurePath
from urllib.parse import unquote, urlsplit

import httpx

from . import banco

TEXTO = {'.md', '.markdown', '.txt'}
PDF = {'.pdf'}
TAMANHO_MAX = 50 * 1024 * 1024
PAGINA_MAX = 15 * 1024 * 1024
TIMEOUT_PAGINA = httpx.Timeout(20.0, connect=8.0)
# Nome genérico de cliente: nada que identifique o Matheus vai pro site.
NAVEGADOR = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Solis/0.1'

# Trechos de ~200 palavras, com 40 de sobra entre um e o próximo: uma ideia que
# cai na emenda continua inteira em algum dos dois. ~200 palavras cabem com
# folga no nomic-embed-text e são o bastante pra ter sentido sozinhas.
PALAVRAS = 200
SOBRA = 40


class NaoLeu(Exception):
    """O arquivo não pôde virar texto. A mensagem diz por quê, pra tela."""


def tipo_de(nome: str) -> str | None:
    ext = PurePath(nome).suffix.lower()
    return 'pdf' if ext in PDF else 'nota' if ext in TEXTO else None


def _limpo(texto: str) -> str:
    # Hifenização de fim de linha do PDF ("informa-\nção") e espaços em sobra.
    texto = re.sub(r'(\w)-\n(\w)', r'\1\2', texto)
    return ' '.join(texto.split())


def _paginas_pdf(dados: bytes) -> list[str]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        leitor = PdfReader(io.BytesIO(dados))
        if leitor.is_encrypted:
            try:
                leitor.decrypt('')  # muitos PDFs "protegidos" abrem sem senha
            except Exception:
                raise NaoLeu('o PDF tem senha') from None
        return [p.extract_text() or '' for p in leitor.pages]
    except NaoLeu:
        raise
    except (PdfReadError, ValueError, KeyError, OSError) as e:
        raise NaoLeu('o PDF está corrompido ou não é um PDF') from e


def _texto(dados: bytes) -> str:
    for codificacao in ('utf-8-sig', 'cp1252'):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise NaoLeu('o texto não está em UTF-8 nem em Windows-1252')


def cortar(texto: str) -> list[str]:
    palavras = texto.split()
    if len(palavras) <= PALAVRAS:
        return [' '.join(palavras)] if palavras else []
    passo = PALAVRAS - SOBRA
    return [' '.join(palavras[i : i + PALAVRAS]) for i in range(0, len(palavras) - SOBRA, passo)]


def ler(nome: str, dados: bytes) -> tuple[str, int | None, list[tuple[int | None, str]]]:
    """(tipo, páginas, trechos como (página, texto)). NaoLeu se não deu."""
    tipo = tipo_de(nome)
    if tipo is None:
        raise NaoLeu('o Solis lê PDF, .md e .txt')
    if len(dados) > TAMANHO_MAX:
        raise NaoLeu('o arquivo passa de 50 MB')
    if tipo == 'pdf':
        paginas = _paginas_pdf(dados)
        trechos = [(n, t) for n, pagina in enumerate(paginas, 1) for t in cortar(_limpo(pagina))]
        if not trechos:
            raise NaoLeu('o PDF não tem texto (parece escaneado; ler imagem ainda não dá)')
        return tipo, len(paginas), trechos
    trechos = [(None, t) for t in cortar(_limpo(_texto(dados)))]
    if not trechos:
        raise NaoLeu('o arquivo está vazio')
    return tipo, None, trechos


def preparar(nome: str, dados: bytes) -> dict:
    """A parte lenta (ler o PDF), sem tocar no banco — pode rodar numa thread.

    O banco NÃO pode ser escrito daqui: a conexão é uma só, e escrever de
    várias threads ao mesmo tempo embaralha as transações (visto ao mandar
    seis arquivos juntos: "cannot commit - no transaction is active", e
    documento guardado sem os trechos)."""
    tipo, paginas, trechos = ler(nome, dados)
    return {'tipo': tipo, 'paginas': paginas, 'trechos': trechos,
            'tamanho': len(dados), 'hash': hashlib.sha256(dados).hexdigest()}


def guardar(nome: str, lido: dict, privado: bool = False) -> int:
    """A parte do banco — na mesma thread de todo o resto do servidor."""
    return banco.adicionar_documento(
        nome, lido['tipo'], lido['paginas'], lido['tamanho'], lido['hash'], lido['trechos'], privado,
        url=lido.get('url'),
    )


def adicionar(nome: str, dados: bytes, privado: bool = False) -> int:
    """Lê e guarda. Devolve o id. NaoLeu ou banco.Duplicado se não entrou."""
    return guardar(nome, preparar(nome, dados), privado)


# — Página web ————————————————————————————————————————————————————————————————

def _endereco(url: str) -> str:
    url = url.strip()
    if not re.match(r'^https?://', url, re.I):
        # "fastapi.tiangolo.com/tutorial" colado sem o https:// é o mais comum.
        if re.match(r'^[\w-]+(\.[\w-]+)+(/|$)', url):
            url = 'https://' + url
        else:
            raise NaoLeu('o endereço precisa ser de uma página (https://...)')
    return url


async def baixar(url: str, transporte: httpx.AsyncBaseTransport | None = None) -> tuple[str, str, bytes]:
    """(endereço final, tipo do conteúdo, corpo). NaoLeu se não deu."""
    url = _endereco(url)
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT_PAGINA, follow_redirects=True, transport=transporte, headers={'User-Agent': NAVEGADOR}
        ) as c:
            async with c.stream('GET', url) as r:
                if r.status_code >= 400:
                    raise NaoLeu(f'o site respondeu {r.status_code}' + (' (precisa de login?)' if r.status_code in (401, 403) else ''))
                corpo = bytearray()
                async for parte in r.aiter_bytes():
                    corpo += parte
                    if len(corpo) > PAGINA_MAX:
                        raise NaoLeu('a página passa de 15 MB')
                return str(r.url), r.headers.get('content-type', ''), bytes(corpo)
    except httpx.HTTPError as e:
        raise NaoLeu('não consegui abrir o endereço (sem internet, ou o site está fora)') from e


def _titulo(texto: str | None) -> str | None:
    # "Background Tasks¶": o ¶ e o # são âncoras de documentação, não título.
    texto = ' '.join((texto or '').split()).strip(' ¶#|-–—')
    return texto[:200] or None


def preparar_pagina(url: str, tipo_conteudo: str, corpo: bytes) -> tuple[str, dict]:
    """(nome, preparado) — o mesmo `preparado` de preparar(). Roda numa thread."""
    caminho = urlsplit(url)
    if 'pdf' in tipo_conteudo or caminho.path.lower().endswith('.pdf'):
        nome = unquote(PurePath(caminho.path).name) or caminho.netloc
        lido = preparar(nome if nome.lower().endswith('.pdf') else f'{nome}.pdf', corpo)
        return nome, lido
    if 'html' not in tipo_conteudo and 'text/plain' not in tipo_conteudo:
        raise NaoLeu('o endereço não é uma página nem um PDF')

    import trafilatura

    html = corpo.decode('utf-8', errors='replace')
    texto = trafilatura.extract(html, url=url, include_comments=False, include_tables=True, favor_recall=True)
    trechos = [(None, t) for t in cortar(_limpo(texto or ''))]
    if not trechos:
        raise NaoLeu('não achei texto na página (pode pedir login ou ser montada por JavaScript)')
    meta = trafilatura.extract_metadata(html, default_url=url)
    nome = _titulo(meta.title if meta else None) or f'{caminho.netloc}{caminho.path}'.rstrip('/')
    return nome, {
        'tipo': 'web', 'paginas': None, 'trechos': trechos, 'tamanho': len(corpo),
        # O endereço é a identidade da página (o conteúdo muda com o tempo):
        # a mesma página não entra duas vezes.
        'hash': hashlib.sha256(f'url:{url}'.encode()).hexdigest(), 'url': url,
    }
