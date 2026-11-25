"""O Vigia (docs/AGENTES.md → a lista unida; IDEIAS.md → Agentes, 25/11/2026):
confere os sites do Matheus e avisa quando um cai, antes de ele notar.

O "pronto quando" do painel: o Vigia avisa um site fora do ar antes de você notar.

Tudo em código, sem cérebro (IDEIAS.md: "onde entra IA: só para explicar o
problema"): a cada INTERVALO, abre cada site e vê se respondeu, se veio erro, se
a palavra que ele escolheu está na página e, uma vez por dia, quando vence o
certificado. Uma falha é conferida de novo CONFIRMA segundos depois: só duas
seguidas viram aviso (um tropeço da rede não acorda ninguém). Avisa de novo
quando o site volta, com quanto tempo ficou fora. Quem dá a voz ao aviso é o
Jarvis (o técnico), como as personalidades e os agentes do IDEIAS.md.

O Matheus manda vigiar pelas ferramentas do Solis (corpo.py: vigiar_site,
sites_vigiados, parar_de_vigiar), com qualquer cérebro.

Limite, dito antes: roda dentro do servidor do Solis, então só vigia com o PC
ligado e o Solis aberto. Com o cérebro na nuvem (a frente de depois), passa a
vigiar sempre.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import socket
import ssl
import time
import uuid
from urllib.parse import urlparse

import httpx

from . import banco

log = logging.getLogger('solis.vigia')

INTERVALO = dt.timedelta(minutes=5)     # entre uma conferida e outra de cada site
CONFIRMA = dt.timedelta(seconds=30)     # a segunda olhada depois de uma falha
VOLTA = 30                              # segundos entre uma volta do laço e outra
PRAZO = 10.0                            # segundos pra responder
LENTO_MS = 8000                         # respondeu, mas devagar demais
CERTIFICADO_AVISO = 14                  # dias antes de vencer
QUEDAS_GUARDADAS = 30
AGENTE = 'Jarvis · Vigia'
# O Vigia se apresenta (não se disfarça de navegador; web.py faz o mesmo).
CABECALHOS = {'User-Agent': 'Solis-Vigia/1.0 (confere se o site esta no ar)'}

_transporte: httpx.AsyncBaseTransport | None = None  # só os testes trocam


class EnderecoInvalido(ValueError):
    pass


# — os sites ———————————————————————————————————————————————————————————————————————

def _agora() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


def normalizar(endereco: str) -> str:
    """'meusite.com.br' → 'https://meusite.com.br'. EnderecoInvalido se não é um site."""
    e = (endereco or '').strip().strip('<>"\'')
    if not e:
        raise EnderecoInvalido('endereço vazio')
    if not re.match(r'^https?://', e, re.I):
        e = 'https://' + e
    u = urlparse(e)
    if not u.hostname or '.' not in u.hostname and u.hostname != 'localhost':
        raise EnderecoInvalido(f'"{endereco}" não parece um site')
    return e.rstrip('/') if u.path in ('', '/') else e


def sites() -> list[dict]:
    return list(banco.ajuste('vigiados') or [])


def _guardar(lista: list[dict]) -> None:
    banco.guardar_ajuste('vigiados', lista)


def _mudar(id_: str, **campos) -> dict | None:
    """Muda um site pelo id, relendo a lista agora (o laço e as ferramentas mexem nela)."""
    lista = sites()
    for s in lista:
        if s['id'] == id_:
            s.update(campos)
            _guardar(lista)
            return s
    return None


def achar(endereco_ou_nome: str) -> dict | None:
    alvo = (endereco_ou_nome or '').strip().lower()
    try:
        url = normalizar(alvo).lower()
    except EnderecoInvalido:
        url = None
    host = urlparse(url).hostname if url else None
    for s in sites():
        if alvo in (s['nome'].lower(), s['url'].lower()) or (url and s['url'].lower() == url) \
                or (host and urlparse(s['url']).hostname == host):
            return s
    return None


def adicionar(endereco: str, nome: str | None = None, palavra: str | None = None) -> dict:
    url = normalizar(endereco)
    if (ja := achar(url)) is not None:
        return ja
    s = {'id': uuid.uuid4().hex[:8], 'url': url, 'nome': (nome or urlparse(url).hostname or url).strip()[:80],
         'palavra': (palavra or '').strip()[:120] or None, 'criado': _agora().isoformat(),
         'estado': 'novo', 'desde': None, 'falhas': 0, 'motivo': None, 'conferido': None, 'ms': None,
         'certificado': None, 'certificado_conferido': None, 'avisou_certificado': None, 'quedas': []}
    _guardar(sites() + [s])
    return s


def remover(endereco_ou_nome: str) -> dict | None:
    s = achar(endereco_ou_nome)
    if s is not None:
        _guardar([x for x in sites() if x['id'] != s['id']])
    return s


# — conferir um site ————————————————————————————————————————————————————————————————

_SIGNIFICADO = {400: 'pedido recusado', 401: 'pede login',
                403: 'acesso negado; pode ser o site bloqueando robôs, abra no navegador pra ver',
                404: 'página não encontrada',
                429: 'limite de acessos', 500: 'erro no servidor', 502: 'o servidor por trás não respondeu',
                503: 'fora do ar ou sobrecarregado', 504: 'o servidor por trás demorou demais'}


def _motivo_da_queda(e: Exception) -> str:
    texto = f'{type(e).__name__}: {e}'.lower()
    if isinstance(e, httpx.TimeoutException):
        return f'não respondeu em {PRAZO:.0f} s'
    if 'getaddrinfo' in texto or 'name or service not known' in texto or 'nodename' in texto or '11001' in texto:
        return 'o endereço não existe mais (DNS)'
    if 'certificate' in texto or 'ssl' in texto:
        return 'erro no certificado de segurança (https)'
    if isinstance(e, httpx.ConnectError):
        return 'recusou a conexão'
    return f'não abriu ({type(e).__name__})'


async def conferir_site(s: dict) -> dict:
    """{'ok', 'status', 'ms', 'motivo', 'lento'} de uma olhada no site."""
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=PRAZO, follow_redirects=True, headers=CABECALHOS,
                                     transport=_transporte) as c:
            r = await c.get(s['url'])
    except Exception as e:  # noqa: BLE001 — qualquer falha de rede é o site fora, com o motivo
        return {'ok': False, 'status': None, 'ms': None, 'motivo': _motivo_da_queda(e), 'lento': False}
    ms = round((time.perf_counter() - t0) * 1000)
    # 429 é o site no ar limitando acessos, não fora (medido em 25/11/2026: o
    # Mercado Livre respondeu 429 conferido a cada minuto). E 401 é o site pedindo login.
    if r.status_code in (401, 429):
        return {'ok': True, 'status': r.status_code, 'ms': ms, 'motivo': None, 'lento': ms > LENTO_MS,
                'nota': _SIGNIFICADO[r.status_code]}
    if r.status_code >= 400:
        return {'ok': False, 'status': r.status_code, 'ms': ms, 'lento': False,
                'motivo': f'erro {r.status_code} ({_SIGNIFICADO.get(r.status_code, "o site respondeu com erro")})'}
    if s.get('palavra') and s['palavra'].lower() not in r.text.lower():
        return {'ok': False, 'status': r.status_code, 'ms': ms, 'lento': False,
                'motivo': f'a página abriu, mas sem "{s["palavra"]}" (pode estar quebrada)'}
    return {'ok': True, 'status': r.status_code, 'ms': ms, 'motivo': None, 'lento': ms > LENTO_MS}


def _vencimento_do_certificado(url: str) -> dt.date | None:
    """A data em que o certificado https vence (None: não é https, ou não deu pra ler)."""
    u = urlparse(url)
    if u.scheme != 'https' or not u.hostname:
        return None
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((u.hostname, u.port or 443), timeout=5) as bruto:
            with ctx.wrap_socket(bruto, server_hostname=u.hostname) as seguro:
                fim = seguro.getpeercert()['notAfter']
        return dt.datetime.fromtimestamp(ssl.cert_time_to_seconds(fim)).date()
    except Exception:  # noqa: BLE001 — sem a data, não avisa (a queda do https a conferida pega)
        return None


# — o laço ———————————————————————————————————————————————————————————————————————————

def _hora(d: dt.datetime) -> str:
    return f'{d.hour}h{d.minute:02d}'


def _duracao(segundos: float) -> str:
    if segundos < 60:
        return 'menos de 1 min'
    m = round(segundos / 60)
    if m < 60:
        return f'{m} min'
    h, m = divmod(m, 60)
    return f'{h} h' + (f' {m} min' if m else '')


def vencidos(agora: dt.datetime) -> list[dict]:
    """Os sites que é hora de conferir: os novos, os de INTERVALO atrás e os que
    falharam uma vez (a segunda olhada, CONFIRMA depois)."""
    saida = []
    for s in sites():
        if not s.get('conferido'):
            saida.append(s)
            continue
        desde = agora - dt.datetime.fromisoformat(s['conferido'])
        if desde >= INTERVALO or (s.get('falhas') == 1 and desde >= CONFIRMA):
            saida.append(s)
    return saida


async def _avisar(titulo: str, texto: str, tag: str) -> None:
    from . import avisos
    log.info('vigia: %s', texto)
    if avisos.ligados():
        await avisos.mostrar(titulo, texto, tag)


async def registrar(s: dict, r: dict, agora: dt.datetime) -> list[str]:
    """Guarda o resultado de uma olhada e avisa o que mudou. Devolve os avisos."""
    avisos_ = []
    if r['ok']:
        mudou = {'falhas': 0, 'motivo': None, 'conferido': agora.isoformat(), 'ms': r['ms']}
        if s['estado'] == 'fora':
            inicio = dt.datetime.fromisoformat(s['desde'])
            quedas = (s.get('quedas') or []) + [{'de': s['desde'], 'ate': agora.isoformat(), 'motivo': s['motivo']}]
            mudou.update(estado='no_ar', desde=agora.isoformat(), quedas=quedas[-QUEDAS_GUARDADAS:])
            avisos_.append(f'{s["nome"]} voltou ao ar às {_hora(agora)}, depois de '
                           f'{_duracao((agora - inicio).total_seconds())} fora.')
        elif s['estado'] != 'no_ar':
            mudou.update(estado='no_ar', desde=agora.isoformat())
        _mudar(s['id'], **mudou)
    else:
        falhas = (s.get('falhas') or 0) + 1
        mudou = {'falhas': falhas, 'motivo': r['motivo'], 'conferido': agora.isoformat(), 'ms': r['ms']}
        if falhas >= 2 and s['estado'] != 'fora':
            mudou.update(estado='fora', desde=agora.isoformat())
            avisos_.append(f'{s["nome"]} caiu: {r["motivo"]}. Conferi duas vezes, a última às {_hora(agora)}.')
        _mudar(s['id'], **mudou)
    for texto in avisos_:
        await _avisar(AGENTE, texto, f'vigia-{s["id"]}-{agora:%H%M%S}')
    return avisos_


async def _certificado(s: dict, agora: dt.datetime) -> str | None:
    """Uma vez por dia: quando vence o certificado, e o aviso se faltar pouco."""
    if s.get('certificado_conferido') == agora.date().isoformat():
        return None
    vence = await asyncio.to_thread(_vencimento_do_certificado, s['url'])
    s = _mudar(s['id'], certificado=vence.isoformat() if vence else None,
               certificado_conferido=agora.date().isoformat()) or s
    if not vence:
        return None
    faltam = (vence - agora.date()).days
    if faltam <= CERTIFICADO_AVISO and s.get('avisou_certificado') != vence.isoformat():
        _mudar(s['id'], avisou_certificado=vence.isoformat())
        texto = (f'O certificado de {s["nome"]} vence em {faltam} dias ({vence:%d/%m}). Sem renovar, o navegador '
                 'vai mostrar o site como inseguro.') if faltam >= 0 else f'O certificado de {s["nome"]} venceu.'
        await _avisar(AGENTE, texto, f'vigia-cert-{s["id"]}')
        return texto
    return None


async def uma_volta(agora: dt.datetime | None = None) -> list[str]:
    """Confere os sites que venceram, todos juntos. Devolve os avisos que saíram."""
    agora = agora or _agora()
    pendentes = vencidos(agora)
    if not pendentes:
        return []
    resultados = await asyncio.gather(*(conferir_site(s) for s in pendentes))
    saida = []
    for s, r in zip(pendentes, resultados):
        saida += await registrar(s, r, agora)
        if r['ok']:
            if (c := await _certificado(s, agora)) is not None:
                saida.append(c)
    return saida


async def vigiar() -> None:
    """O laço, dentro do servidor (como o dos avisos)."""
    while True:
        try:
            await uma_volta()
        except Exception:  # noqa: BLE001 — um site estranho não pode parar o Vigia
            log.exception('vigia: a volta falhou')
        await asyncio.sleep(VOLTA)


# — em palavras, pro cérebro e pra voz ————————————————————————————————————————————————

def _ultimos_dias(s: dict, dias: int, agora: dt.datetime) -> tuple[int, float]:
    """(quedas, segundos fora) nos últimos `dias`, contando a queda de agora."""
    corte = agora - dt.timedelta(days=dias)
    quedas = [(dt.datetime.fromisoformat(q['de']), dt.datetime.fromisoformat(q['ate'])) for q in s.get('quedas') or []]
    if s.get('estado') == 'fora' and s.get('desde'):
        quedas.append((dt.datetime.fromisoformat(s['desde']), agora))
    quedas = [(max(de, corte), ate) for de, ate in quedas if ate > corte]
    return len(quedas), sum((ate - de).total_seconds() for de, ate in quedas)


def descrever(s: dict, agora: dt.datetime | None = None) -> str:
    agora = agora or _agora()
    if s['estado'] == 'fora':
        estado = (f'FORA DO AR desde {_hora(dt.datetime.fromisoformat(s["desde"]))} '
                  f'({_duracao((agora - dt.datetime.fromisoformat(s["desde"])).total_seconds())}): {s["motivo"]}')
    elif s['estado'] == 'novo' or not s.get('conferido'):
        estado = 'ainda não conferido'
    else:
        estado = f'no ar (respondeu em {s["ms"] / 1000:.1f} s'.replace('.', ',') + \
            f', conferido às {_hora(dt.datetime.fromisoformat(s["conferido"]))})'
        if s.get('falhas'):
            estado += f'; a última olhada falhou ({s["motivo"]}), conferindo de novo'
    n, fora = _ultimos_dias(s, 7, agora)
    semana = f' Nos últimos 7 dias: {n} queda{"s" if n != 1 else ""}' + (f', {_duracao(fora)} fora.' if n else '.')
    cert = ''
    if s.get('certificado'):
        faltam = (dt.date.fromisoformat(s['certificado']) - agora.date()).days
        if faltam <= CERTIFICADO_AVISO:
            cert = f' O certificado vence em {faltam} dias.'
    return f'{s["nome"]} ({s["url"]}): {estado}.{semana}{cert}'


def resumo(agora: dt.datetime | None = None) -> str:
    lista = sites()
    if not lista:
        return 'Nenhum site sendo vigiado. Pra vigiar, é só dizer o endereço.'
    fora = [s for s in lista if s['estado'] == 'fora']
    cabeca = (f'{len(fora)} de {len(lista)} fora do ar.' if fora else
              f'{"O site está" if len(lista) == 1 else f"Os {len(lista)} sites estão"} no ar.'
              if all(s['estado'] == 'no_ar' for s in lista) else f'{len(lista)} sites vigiados.')
    return cabeca + '\n' + '\n'.join(f'- {descrever(s, agora)}' for s in lista)
