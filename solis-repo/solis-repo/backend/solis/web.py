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
        # O anúncio passa pelo próprio DuckDuckGo (duckduckgo.com/y.js?ad_domain=...):
        # visto em 21/11/2026, a página da loja do anúncio tinha 3,5 MB e entrou como resultado.
        if not destino.startswith('http') or (urlsplit(destino).hostname or '').endswith('duckduckgo.com'):
            continue
        trecho = r.xpath('.//*[contains(@class, "result__snippet")]')
        saida.append((' '.join(link[0].text_content().split()), destino,
                      ' '.join(trecho[0].text_content().split()) if trecho else ''))
    return saida[:RESULTADOS_MAX]


async def buscar(termos: str, transporte=None, voz: bool = False) -> tuple[str, str, str]:
    """(endereço, título, texto) da busca: a lista dos resultados, pro modelo ler o que serve.
    `voz`: menos resultados, e o que as melhores páginas dizem já junto (_ja_lidas)."""
    endereco = BUSCA + quote_plus(termos)
    try:
        final, _, corpo = await conhecimento.baixar(endereco, transporte)
    except conhecimento.NaoLeu as e:
        raise NaoLeu(str(e)) from e
    resultados = await asyncio.to_thread(_resultados, corpo)
    if not resultados:
        raise NaoLeu('a busca não trouxe resultados (tente outras palavras, ou leia direto um site)')
    if voz:
        resultados = resultados[:RESULTADOS_VOZ]
    texto = '\n\n'.join(f'{i}. {t}\n   {u}\n   {s}' for i, (t, u, s) in enumerate(resultados, 1))
    if voz:
        lidas = await _ja_lidas(resultados, termos, transporte)
        if lidas:
            return final, f'Resultados da busca: {termos}', (
                texto + '\n\nO que as melhores páginas dizem agora (lidas pelo Solis, só os trechos do assunto):\n\n'
                + '\n\n'.join(f'[{i}] {t}\n{trecho}' for i, t, trecho in lidas)
                + '\n\nResponda pelo que as páginas dizem: o trecho da busca pode ser antigo. Se nada aqui '
                'responde, leia com WebFetch a página de outro resultado.')
    return final, f'Resultados da busca: {termos}', (
        texto + '\n\nO trecho é só um resumo: pra responder, leia com WebFetch a página do resultado que serve. '
        'Pro mais recente (o último, o de hoje, o de agora), um trecho com data antiga não serve: leia a página.')


# Pela voz, a busca já traz o que as melhores páginas dizem (21/11/2026, medido):
# com a lista só, a Groq respondia pelo trechinho da busca (rápido, 1,5 a 2,7 s,
# mas o preço e a notícia do trecho podem ser velhos); mandada ler, era mais uma
# rodada inteira (~3 mil tokens do minuto grátis) e a leitura (0,2 a 2,8 s direto,
# 1 a 15 s pelo leitor). Aqui as melhores são lidas ao mesmo tempo, com prazo, e
# vão só os trechos do assunto. A que não terminou no prazo segue lendo e fica
# guardada uns minutos: se o cérebro pedir ela, já está pronta (ler).
RESULTADOS_VOZ = 5
LER_JUNTO = 3           # páginas lidas ao mesmo tempo
JUNTAR_MAX = 2          # quantas vão junto da lista
PRAZO_JUNTO = 2.5       # segundos esperando por elas, no máximo
TRECHO_MAX = 900        # caracteres de cada uma
GUARDADA_S = 180
_guardadas: dict[str, tuple[float, asyncio.Task]] = {}
# Os sites que recusam robôs (403): não se insiste (nem se disfarça o Solis de navegador).
_recusam: set[str] = set()


def _simples(t: str) -> str:
    import unicodedata
    return unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode().lower()


def trecho_do_assunto(texto: str, termos: str, limite: int = TRECHO_MAX) -> str:
    """As linhas da página que falam do que se buscou (as palavras, um preço, um
    número), na ordem da página; sem nenhuma, o começo."""
    palavras = set(re.findall(r'\w{4,}', _simples(termos)))
    # Por frase, não por linha: os trechos da leitura juntam parágrafos inteiros.
    linhas = [l.strip()[:300] for l in re.split(r'(?<=[.!?])\s+|\n+', texto) if len(l.strip()) > 2]

    def nota(linha: str) -> int:
        s = _simples(linha)
        return sum(p in s for p in palavras) + (2 if re.search(r'R\$\s?\d|\d+[.,]\d|\d+\s?%', linha) else 0)
    notas = [nota(l) for l in linhas]
    escolhidas, total = set(), 0
    for i in sorted(range(len(linhas)), key=lambda i: -notas[i]):
        if notas[i] == 0:
            break
        if total + len(linhas[i]) + 1 > limite:
            continue
        escolhidas.add(i)
        total += len(linhas[i]) + 1
    # Nenhuma linha do assunto: a página não serve (a de login do Mercado Livre,
    # "acesse sua conta", entrava como se fosse o preço).
    return '\n'.join(linhas[i] for i in sorted(escolhidas))


def _guardar_leitura(url: str, transporte) -> asyncio.Task:
    agora = asyncio.get_running_loop().time()
    for u, (quando, _) in list(_guardadas.items()):
        if agora - quando > GUARDADA_S:
            _guardadas.pop(u, None)
    if url not in _guardadas:
        tarefa = asyncio.create_task(_ler_de_verdade(url, transporte))
        # A que ninguém pediu e falhou não vira "exception was never retrieved" no log.
        tarefa.add_done_callback(lambda t: t.cancelled() or t.exception())
        _guardadas[url] = (agora, tarefa)
    return _guardadas[url][1]


async def _ja_lidas(resultados, termos: str, transporte) -> list[tuple[int, str, str]]:
    """(número do resultado, título, trecho do assunto) das páginas lidas no prazo."""
    candidatos = [(i, t, u) for i, (t, u, _) in enumerate(resultados, 1)
                  if (urlsplit(u).hostname or '') not in _recusam][:LER_JUNTO]
    tarefas = {_guardar_leitura(u, transporte): (i, t) for i, t, u in candidatos}
    laco = asyncio.get_running_loop()
    ate = laco.time() + PRAZO_JUNTO
    faltam, uteis = set(tarefas), {}
    # Para quando JUNTAR_MAX servem ou o prazo acaba: não espera a mais lenta.
    while faltam and len(uteis) < JUNTAR_MAX and laco.time() < ate:
        prontas, faltam = await asyncio.wait(faltam, timeout=ate - laco.time(), return_when=asyncio.FIRST_COMPLETED)
        for tarefa in prontas:
            if tarefa.cancelled() or tarefa.exception() is not None:
                continue
            _, _, texto = tarefa.result()
            trecho = trecho_do_assunto(texto, termos)
            if len(trecho) >= 80:
                uteis[tarefa] = trecho
    lidas = [(*tarefas[t], uteis[t]) for t in tarefas if t in uteis]  # na ordem da busca
    return lidas[:JUNTAR_MAX]


async def ler(url: str, transporte=None, voz: bool = False) -> tuple[str, str, str]:
    """(endereço final, título, texto). NaoLeu com o motivo em português."""
    termos = termos_da_busca(url)
    if termos:
        return await buscar(termos, transporte, voz)
    guardada = _guardadas.get(url)
    if guardada is not None:
        return await asyncio.shield(guardada[1])  # lida junto da busca: pronta ou terminando
    return await _ler_de_verdade(url, transporte)


async def _ler_de_verdade(url: str, transporte=None) -> tuple[str, str, str]:
    try:
        endereco = conhecimento._endereco(url)
    except conhecimento.NaoLeu as e:
        raise NaoLeu(str(e)) from e
    if not await asyncio.to_thread(_publico, urlsplit(endereco).hostname or ''):
        raise NaoLeu('esse endereço é do próprio computador ou da rede de casa: daqui só se lê página da internet')
    try:
        final, tipo, corpo = await conhecimento.baixar(endereco, transporte)
    except conhecimento.NaoLeu as e:
        if '403' in str(e):
            _recusam.add(urlsplit(endereco).hostname or '')
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
