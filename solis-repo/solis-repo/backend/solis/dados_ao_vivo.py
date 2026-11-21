"""Dados ao vivo direto da fonte (21/11/2026): cotação, clima e jogos.

Medido no comparativo de cérebros pela voz: o que mais errava não era o
cérebro, eram os "olhos" — os sites de cotação vêm vazios sem JavaScript (o
Nemotron: "os sites exigem JavaScript"; a Groq deu o dólar a R$ 6,67). Pra o
que se pergunta todo dia, a fonte direta acerta sempre e responde na hora,
sem chave e de graça:

- cotação: AwesomeAPI (economia.awesomeapi.com.br), medida em 0,1 s;
- clima: Open-Meteo (o geocoding acha a cidade; a previsão, a temperatura),
  medida em 0,7 s;
- jogos: a ESPN (a busca de times e a agenda de cada um, as mesmas que o site
  e o app deles usam; sem chave, mas sem documentação: se mudar, a ferramenta
  diz que não conseguiu e o cérebro procura na web). Medida em 0,4 s. Pela
  busca, a Groq respondia o "último jogo do Flamengo" com um trecho de um mês
  antes (26/10), e a página de placares só vinha com o JavaScript.

São ferramentas do Solis (corpo.DO_SOLIS): valem pra qualquer cérebro.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import httpx

COTACAO_URL = 'https://economia.awesomeapi.com.br/json/last/{pares}'
GEO_URL = 'https://geocoding-api.open-meteo.com/v1/search'
CLIMA_URL = 'https://api.open-meteo.com/v1/forecast'
TEMPO = httpx.Timeout(10.0, connect=5.0)

MOEDAS = {
    'dolar': 'USD', 'dólar': 'USD', 'usd': 'USD', 'euro': 'EUR', 'eur': 'EUR', 'libra': 'GBP', 'gbp': 'GBP',
    'bitcoin': 'BTC', 'btc': 'BTC', 'ethereum': 'ETH', 'eth': 'ETH', 'iene': 'JPY', 'yen': 'JPY', 'jpy': 'JPY',
    'peso': 'ARS', 'peso argentino': 'ARS', 'ars': 'ARS', 'dolar canadense': 'CAD', 'cad': 'CAD',
    'franco': 'CHF', 'chf': 'CHF', 'yuan': 'CNY', 'cny': 'CNY',
}
NOMES = {'USD': 'Dólar', 'EUR': 'Euro', 'GBP': 'Libra', 'BTC': 'Bitcoin', 'ETH': 'Ethereum', 'JPY': 'Iene',
         'ARS': 'Peso argentino', 'CAD': 'Dólar canadense', 'CHF': 'Franco suíço', 'CNY': 'Yuan'}

# Os códigos de tempo do Open-Meteo (WMO), em português.
TEMPO_WMO = {0: 'céu limpo', 1: 'quase limpo', 2: 'parcialmente nublado', 3: 'nublado', 45: 'neblina', 48: 'neblina',
             51: 'garoa fraca', 53: 'garoa', 55: 'garoa forte', 61: 'chuva fraca', 63: 'chuva', 65: 'chuva forte',
             71: 'neve fraca', 73: 'neve', 75: 'neve forte', 80: 'pancadas de chuva fracas', 81: 'pancadas de chuva',
             82: 'pancadas de chuva fortes', 95: 'trovoada', 96: 'trovoada com granizo', 99: 'trovoada com granizo'}


class SemDado(Exception):
    pass


def _simples(t: str) -> str:
    return unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode().lower().strip()


def _codigos(moedas: str) -> list[str]:
    saida = []
    for parte in (moedas or 'dolar').replace(' e ', ',').split(','):
        p = parte.strip().lower()
        if not p:
            continue
        codigo = MOEDAS.get(p) or MOEDAS.get(_simples(p)) or (p.upper() if len(p) == 3 and p.isalpha() else None)
        if codigo and codigo != 'BRL' and codigo not in saida:
            saida.append(codigo)
    return saida or ['USD']


def _reais(valor: float) -> str:
    casas = 2 if valor >= 1 else 4
    return 'R$ ' + f'{valor:,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


async def cotacao(moedas: str, transporte: httpx.AsyncBaseTransport | None = None) -> str:
    """O valor de agora em reais (compra), com a hora da cotação."""
    codigos = _codigos(moedas)
    try:
        async with httpx.AsyncClient(timeout=TEMPO, transport=transporte) as c:
            r = await c.get(COTACAO_URL.format(pares=','.join(f'{m}-BRL' for m in codigos)))
    except httpx.HTTPError as e:
        raise SemDado(f'a fonte da cotação não respondeu ({e.__class__.__name__})') from e
    if r.status_code != 200:
        raise SemDado(f'a fonte da cotação respondeu {r.status_code}')
    dados = r.json()
    linhas = []
    for m in codigos:
        d = dados.get(f'{m}BRL')
        if not d:
            linhas.append(f'{NOMES.get(m, m)}: sem cotação agora')
            continue
        quando = d.get('create_date', '')
        dia = f'{quando[8:10]}/{quando[5:7]} às {quando[11:16]}' if len(quando) >= 16 else quando
        variacao = d.get('pctChange')
        linhas.append(f'{NOMES.get(m, m)}: {_reais(float(d["bid"]))} (compra), atualizado em {dia}'
                      + (f', variação de {float(variacao):+.2f}% no dia'.replace('.', ',') if variacao else ''))
    return '\n'.join(linhas)


async def clima(cidade: str, transporte: httpx.AsyncBaseTransport | None = None) -> str:
    """O tempo de agora e do dia numa cidade."""
    cidade = (cidade or '').strip()
    if not cidade:
        raise SemDado('faltou a cidade: pergunte ao Matheus ou procure na memória onde ele mora')
    try:
        async with httpx.AsyncClient(timeout=TEMPO, transport=transporte) as c:
            g = await c.get(GEO_URL, params={'name': cidade, 'count': 1, 'language': 'pt', 'format': 'json'})
            lugar = ((g.json() or {}).get('results') or [None])[0] if g.status_code == 200 else None
            if not lugar:
                raise SemDado(f'não achei a cidade "{cidade}"')
            p = await c.get(CLIMA_URL, params={
                'latitude': lugar['latitude'], 'longitude': lugar['longitude'], 'timezone': 'auto', 'forecast_days': 1,
                'current': 'temperature_2m,apparent_temperature,weather_code,relative_humidity_2m,wind_speed_10m',
                'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code'})
    except httpx.HTTPError as e:
        raise SemDado(f'a fonte do clima não respondeu ({e.__class__.__name__})') from e
    if p.status_code != 200:
        raise SemDado(f'a fonte do clima respondeu {p.status_code}')
    j = p.json()
    agora, dia = j.get('current', {}), j.get('daily', {})
    nome = ', '.join(x for x in (lugar.get('name'), lugar.get('admin1'), lugar.get('country')) if x)

    def um(chave):
        v = dia.get(chave) or [None]
        return v[0]
    partes = [f'{nome}: agora {round(agora.get("temperature_2m", 0))} °C'
              f' (sensação de {round(agora.get("apparent_temperature", 0))} °C), '
              f'{TEMPO_WMO.get(agora.get("weather_code"), "tempo indefinido")}, '
              f'umidade {agora.get("relative_humidity_2m")}%, vento {round(agora.get("wind_speed_10m", 0))} km/h.']
    if um('temperature_2m_max') is not None:
        partes.append(f'Hoje: máxima de {round(um("temperature_2m_max"))} °C, mínima de {round(um("temperature_2m_min"))} °C, '
                      f'{um("precipitation_probability_max") or 0}% de chance de chuva '
                      f'({TEMPO_WMO.get(um("weather_code"), "tempo indefinido")}).')
    return ' '.join(partes)


# --- Jogos (ESPN) ---
ESPN_BUSCA = 'https://site.web.api.espn.com/apis/search/v2'
ESPN_AGENDA = 'https://site.api.espn.com/apis/site/v2/sports/{esporte}/{liga}/teams/{time}/schedule'
BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
DIAS = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
# Como ele fala -> como a ESPN acha (a busca dela acha as seleções pelo nome em inglês).
APELIDOS = {'selecao brasileira': 'Brazil', 'selecao': 'Brazil', 'brasil': 'Brazil', 'mengao': 'Flamengo',
            'timao': 'Corinthians', 'verdao': 'Palmeiras', 'fogao': 'Botafogo', 'peixe': 'Santos',
            'galo': 'Atlético-MG', 'tricolor paulista': 'São Paulo', 'vascao': 'Vasco'}
_DE_BASE = re.compile(r'\b[US]-?\d{2}\b|youth|sub-?\d{2}|reserv', re.I)


def _principal(t: dict) -> int:
    """0 pro time principal; a base (sub-20) e o feminino ficam pra depois."""
    liga = t.get('defaultLeagueSlug') or ''
    return int(bool(_DE_BASE.search(t.get('displayName', '')) or '.w.' in liga or 'youth' in liga or '_u' in liga))


def _quando(iso: str, hora: bool = True) -> str:
    d = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(BRASILIA)
    return f'{DIAS[d.weekday()]}, {d:%d/%m}' + (f' às {d:%H:%M}' if hora else '')


def _placar(comp: dict) -> str:
    lados = sorted(comp.get('competitors', []), key=lambda x: x.get('homeAway') != 'home')
    if len(lados) != 2:
        return '?'

    def gols(x):
        s = x.get('score')
        return s.get('displayValue') if isinstance(s, dict) else s

    def nome(x):
        return (x.get('team') or {}).get('displayName') or '?'
    casa, fora = lados
    if gols(casa) is None or gols(fora) is None:
        return f'{nome(casa)} x {nome(fora)}'
    return f'{nome(casa)} {gols(casa)} x {gols(fora)} {nome(fora)}'


def _onde(e: dict, comp: dict) -> str:
    liga = (e.get('league') or {}).get('name') or (e.get('season') or {}).get('displayName') or ''
    estadio = (comp.get('venue') or {}).get('fullName')
    return liga + (f' ({estadio})' if estadio else '')


async def jogos(time: str, transporte: httpx.AsyncBaseTransport | None = None) -> str:
    """O jogo ao vivo, o último resultado, os dois anteriores e o próximo jogo de um time."""
    nome = (time or '').strip()
    if not nome:
        raise SemDado('faltou o time')
    busca = APELIDOS.get(_simples(nome), nome)
    try:
        async with httpx.AsyncClient(timeout=TEMPO, transport=transporte) as c:
            r = await c.get(ESPN_BUSCA, params={'query': busca, 'limit': 8, 'type': 'team', 'lang': 'pt',
                                                'region': 'br'})
            achados = [x for res in (r.json().get('results') or []) if res.get('type') == 'team'
                       for x in res.get('contents') or []] if r.status_code == 200 else []
            if not achados:
                raise SemDado(f'não achei o time "{nome}"')
            t = min(achados, key=_principal)  # o min é estável: o primeiro principal da lista
            esporte, liga = t.get('sport') or 'soccer', t.get('defaultLeagueSlug') or 'all'
            codigo = (t.get('uid') or '').rsplit('t:', 1)[-1]
            # A liga do time traz o jogo de hoje primeiro; "all" (só no futebol) traz as copas.
            ligas = [liga] + (['all'] if esporte == 'soccer' and liga != 'all' else [])
            pedidos = [c.get(ESPN_AGENDA.format(esporte=esporte, liga=lg, time=codigo),
                             params={'lang': 'pt', 'region': 'br', **extra})
                       for lg in ligas for extra in ({}, {'fixture': 'true'})]
            respostas = await asyncio.gather(*pedidos, return_exceptions=True)
    except httpx.HTTPError as e:
        raise SemDado(f'a fonte dos jogos não respondeu ({e.__class__.__name__})') from e
    eventos = {}
    for resp in respostas:
        if isinstance(resp, httpx.Response) and resp.status_code == 200:
            for e in resp.json().get('events') or []:
                eventos.setdefault(e.get('id'), e)
    linhas, passados, futuros = [], [], []
    for e in sorted(eventos.values(), key=lambda e: e.get('date', '')):
        comp = (e.get('competitions') or [{}])[0]
        estado = (comp.get('status') or {}).get('type') or {}
        if estado.get('state') == 'in':
            relogio = (comp.get('status') or {}).get('displayClock') or ''
            linhas.append(f'Ao vivo agora: {_placar(comp)}, {relogio}, {_onde(e, comp)}.')
        elif estado.get('state') == 'post' and estado.get('completed'):
            passados.append((e, comp))
        elif estado.get('state') == 'pre':
            futuros.append((e, comp))
    if passados:
        e, comp = passados[-1]
        linhas.append(f'Último jogo: {_placar(comp)}, {_quando(e["date"])}, {_onde(e, comp)}, encerrado.')
        if len(passados) > 1:
            linhas.append('Antes: ' + '; '.join(f'{_placar(c)} ({_quando(ev["date"], False)}, {_onde(ev, c)})'
                                                for ev, c in reversed(passados[-3:-1])) + '.')
    if futuros:
        e, comp = futuros[0]
        linhas.append(f'Próximo jogo: {_placar(comp)}, {_quando(e["date"])}, {_onde(e, comp)}.')
    if not linhas:
        raise SemDado(f'a fonte não tem jogos recentes do {t.get("displayName", nome)}')
    return f'{t.get("displayName", nome)} (horário de Brasília):\n' + '\n'.join(linhas)
