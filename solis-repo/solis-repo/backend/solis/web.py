"""Ler uma página da internet pelo corpo do Solis (corpo.py): a ferramenta
WebFetch, o mesmo nome da do Claude. O Solis baixa a página e devolve só o
texto principal (a trafilatura, como no Conhecimento), sem abrir janela e bem
mais leve que o retrato do navegador (o grátis da Groq: 8 mil tokens por
minuto). É o "ler" da pesquisa longa nos outros cérebros; o "buscar" é o
navegador (a página de resultados do Google).

Só endereço público: localhost e a rede de casa (127.x, 10.x, 192.168.x,
172.16–31.x, o ::1...) são recusados, antes e depois dos redirecionamentos —
senão um cérebro na nuvem leria o próprio servidor do Solis (as memórias, as
conversas) e levaria pra fora. O texto vai cercado e sem as ordens escondidas
(corpo.cercar, injecao.py), como o das páginas do navegador."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from . import conhecimento

TEXTO_MAX = 10_000   # caracteres da página que vão pro modelo (o resto, cortado com aviso)


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


async def ler(url: str, transporte=None) -> tuple[str, str, str]:
    """(endereço final, título, texto). NaoLeu com o motivo em português."""
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
        raise NaoLeu(str(e)) from e
    texto = '\n\n'.join(t for _, t in lido['trechos'])
    return final, nome, texto


def para_o_modelo(final: str, titulo: str, texto: str) -> str:
    """O cabeçalho (o endereço e o título) e o texto, cortado se passar do limite."""
    corte = ''
    if len(texto) > TEXTO_MAX:
        corte = f'\n\n[cortado: a página tinha {len(texto)} caracteres; aqui vão os {TEXTO_MAX} primeiros]'
        texto = texto[:TEXTO_MAX]
    return f'- Page URL: {final}\n- Page Title: {titulo}\n\n{texto}{corte}'
