"""Ler uma página da internet pelo corpo do Solis (corpo.py): a ferramenta
WebFetch, o mesmo nome da do Claude. O Solis baixa a página e devolve só o
texto principal (a trafilatura, como no Conhecimento), sem abrir janela e bem
mais leve que o retrato do navegador (o grátis da Groq: 8 mil tokens por
minuto). É o "ler" da pesquisa longa nos outros cérebros. Um endereço de
busca (Google, Bing, DuckDuckGo) vira a lista dos resultados, pela busca do
DuckDuckGo sem JavaScript (`buscar`): é o "buscar" de quem não tem o navegador.

Só endereço público: localhost e a rede de casa (127.x, 10.x, 192.168.x,
172.16–31.x, o ::1...) são recusados, antes e depois dos redirecionamentos —
senão um cérebro na nuvem leria o próprio servidor do Solis (as memórias, as
conversas) e levaria pra fora. O texto vai cercado e sem as ordens escondidas
(corpo.cercar, injecao.py), como o das páginas do navegador."""
from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
from urllib.parse import parse_qs, quote_plus, urlsplit

import httpx

from . import conhecimento

TEXTO_MAX = 10_000   # caracteres da página que vão pro modelo (o resto, cortado com aviso)
# Pela voz (21/11/2026): com a página inteira, cada leitura comia quase metade do
# minuto grátis da Groq, e a pergunta falada levava 16 a 49 s. A resposta falada
# é uma ou duas frases: o começo da página basta.
TEXTO_MAX_VOZ = 3_500


class NaoLeu(Exception):
    pass


def _publico(host: str) -> bool:
    """O host só aponta pra endereços públicos (nada de localhost nem rede de casa)."""
    if not host:
        return False
    try:
        ips = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return True  # sem resolver: o download falha sozinho, com a mensagem dele
    for ip in ips:
        endereco = ipaddress.ip_address(ip.split('%')[0])
        if (endereco.is_private or endereco.is_loopback or endereco.is_link_local or endereco.is_reserved
                or endereco.is_multicast or endereco.is_unspecified):
            return False
    return True


# A busca (20/11/2026, medido): o modelo que quer "a cotação do dólar hoje"
# lê https://www.google.com/search?q=..., e o Google sem JavaScript devolve só
# "Clique aqui se o redirecionamento não iniciar". O Solis faz a mesma busca
# no DuckDuckGo sem JavaScript e devolve a lista dos resultados.
BUSCA = 'https://html.duckduckgo.com/html/?q='
RESULTADOS_MAX = 8
_BUSCADORES = ('google.', 'bing.com', 'duckduckgo.com')


def termos_da_busca(url: str) -> str | None:
    """O que se buscou, se o endereço é uma página de resultados (Google, Bing, DuckDuckGo)."""
    try:
        partes = urlsplit(url if '://' in url else 'https://' + url)
    except ValueError:
        return None
    host = (partes.hostname or '').lower()
    if not any(b in host for b in _BUSCADORES) or not partes.path.rstrip('/').endswith(('/search', '/html')):
        return None
    termos = parse_qs(partes.query).get('q', [''])[0].strip()
    return termos or None


def _resultados(html: bytes) -> list[tuple[str, str, str]]:
    """(título, endereço, trecho) de cada resultado da página do DuckDuckGo."""
    import lxml.html
    # Em texto antes: sem o charset na página, o lxml lê os bytes como latin-1 ("DÃ³lar").
    pagina = lxml.html.fromstring(html.decode('utf-8', errors='replace'))
    saida = []
    for r in pagina.xpath('//div[contains(@class, "result__body")]'):
        link = r.xpath('.//a[contains(@class, "result__a")]')
        if not link:
            continue
        destino = link[0].get('href') or ''
        # O link passa pelo DuckDuckGo (//duckduckgo.com/l/?uddg=<o de verdade>).
        destino = parse_qs(urlsplit(destino).query).get('uddg', [destino])[0]
        if not destino.startswith('http'):
            continue
        trecho = r.xpath('.//*[contains(@class, "result__snippet")]')
        saida.append((' '.join(link[0].text_content().split()), destino,
                      ' '.join(trecho[0].text_content().split()) if trecho else ''))
    return saida[:RESULTADOS_MAX]


async def buscar(termos: str, transporte=None) -> tuple[str, str, str]:
    """(endereço, título, texto) da busca: a lista dos resultados, pro modelo ler o que serve."""
    endereco = BUSCA + quote_plus(termos)
    try:
        final, _, corpo = await conhecimento.baixar(endereco, transporte)
    except conhecimento.NaoLeu as e:
        raise NaoLeu(str(e)) from e
    resultados = await asyncio.to_thread(_resultados, corpo)
    if not resultados:
        raise NaoLeu('a busca não trouxe resultados (tente outras palavras, ou leia direto um site)')
    texto = '\n\n'.join(f'{i}. {t}\n   {u}\n   {s}' for i, (t, u, s) in enumerate(resultados, 1))
    return final, f'Resultados da busca: {termos}', (
        texto + '\n\nO trecho é só um resumo: pra responder, leia com WebFetch a página do resultado que serve.')


async def ler(url: str, transporte=None) -> tuple[str, str, str]:
    """(endereço final, título, texto). NaoLeu com o motivo em português."""
    termos = termos_da_busca(url)
    if termos:
        return await buscar(termos, transporte)
    try:
        endereco = conhecimento._endereco(url)
    except conhecimento.NaoLeu as e:
        raise NaoLeu(str(e)) from e
    if not await asyncio.to_thread(_publico, urlsplit(endereco).hostname or ''):
        raise NaoLeu('esse endereço é do próprio computador ou da rede de casa: daqui só se lê página da internet')
    try:
        final, tipo, corpo = await conhecimento.baixar(endereco, transporte)
    except conhecimento.NaoLeu as e:
        raise NaoLeu(str(e)) from e
    if final != endereco and not await asyncio.to_thread(_publico, urlsplit(final).hostname or ''):
        raise NaoLeu('a página mandou pra um endereço do computador ou da rede de casa: não li')
    try:
        nome, lido = await asyncio.to_thread(conhecimento.preparar_pagina, final, tipo, corpo)
    except conhecimento.NaoLeu as e:
        if not LEITOR_LIGADO:
            raise NaoLeu(str(e)) from e
        nome, lido = final, {'trechos': []}
    texto = '\n\n'.join(t for _, t in lido['trechos'])
    if len(texto) < POUCO_TEXTO and LEITOR_LIGADO:
        renderizado = await _renderizado(final, transporte)
        if renderizado and len(renderizado) > len(texto):
            texto = renderizado
    if not texto:
        raise NaoLeu('a página veio vazia (nem renderizada deu texto)')
    return final, nome, texto


# A página que só aparece com JavaScript (21/11/2026): o Globo Esporte do
# Flamengo veio com 598 caracteres, a cotação do dólar sem o número. Quando a
# leitura direta traz pouco, o Solis pede a página renderizada a um leitor
# grátis e sem chave (r.jina.ai: roda o JavaScript e devolve o texto), e fica
# com o que veio melhor. Só vai pra lá o endereço da página pública — nunca
# nada do Matheus. SOLIS_WEB_LEITOR=0 desliga.
LEITOR = 'https://r.jina.ai/'
LEITOR_LIGADO = os.environ.get('SOLIS_WEB_LEITOR', '1') != '0'
POUCO_TEXTO = 1500


def _limpar_markdown(md: str) -> str:
    """O texto do leitor sem as imagens, os endereços dos links e os menus curtos."""
    md = md.split('Markdown Content:', 1)[-1]
    md = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', md)
    md = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', md)
    linhas = [l.strip(' *#|-') for l in md.splitlines()]
    return '\n'.join(l for l in linhas if len(l) > 25 or re.search(r'\d', l))


async def _renderizado(url: str, transporte=None) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), transport=transporte) as c:
            r = await c.get(LEITOR + url, headers={'Accept': 'text/plain'})
    except httpx.HTTPError:
        return None
    return _limpar_markdown(r.text) if r.status_code == 200 else None


def para_o_modelo(final: str, titulo: str, texto: str, limite: int = TEXTO_MAX) -> str:
    """O cabeçalho (o endereço e o título) e o texto, cortado se passar do limite."""
    corte = ''
    if len(texto) > limite:
        corte = f'\n\n[cortado: a página tinha {len(texto)} caracteres; aqui vão os {limite} primeiros]'
        texto = texto[:limite]
    return f'- Page URL: {final}\n- Page Title: {titulo}\n\n{texto}{corte}'
