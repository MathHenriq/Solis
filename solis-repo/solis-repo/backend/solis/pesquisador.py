"""O Atlas · Pesquisador (docs/AGENTES.md → a lista unida; IDEIAS.md → Agentes,
25/11/2026): uma vez por semana, as novidades de IA que servem pro Matheus e pro
Solis.

O "pronto quando" do painel: o Pesquisador traz uma novidade útil por semana.

A regra-mãe do IDEIAS.md ("nada de lorota") decide o desenho:
- o código busca as novidades da semana em fontes de verdade, grátis e sem
  login (Hacker News, GitHub, Hugging Face), e separa as de IA;
- o cérebro (qualquer um, na ordem dele em Configurações → Cérebros) só ESCOLHE,
  pelo número da lista, e diz por que serve e o que fazer; o título, a fonte e
  o link vêm sempre da fonte, nunca do cérebro. Inventar uma novidade ou um link
  não tem como;
- nada útil na semana: diz que não achou (melhor nenhuma que uma inútil).

Entrega numa conversa nova ("Novidades da semana · Atlas", nos Recentes), com o
aviso no Windows. Quem dá a voz é o Jarvis (o técnico), como os outros agentes.
Roda sozinho uma vez por semana (segunda, a partir das 9h, ou na primeira vez
que o Solis abrir depois disso) e quando ele pede (a ferramenta
novidades_da_semana). Só o que não é privado vai pro cérebro: a lista pública e
um perfil do que interessa.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re

import httpx

from . import banco

log = logging.getLogger('solis.pesquisador')

AGENTE = 'Jarvis · Atlas'
TITULO = 'Novidades da semana · Atlas'
DIA, HORA = 0, dt.time(9, 0)   # segunda, 9h
ITENS_MAX = 5
CANDIDATAS_MAX = 60
PRAZO = 20.0
CABECALHOS = {'User-Agent': 'Solis-Atlas/1.0 (pesquisa semanal de novidades)'}
_transporte: httpx.AsyncBaseTransport | None = None  # só os testes trocam

# O que interessa (vai pro cérebro: é o produto, nada privado).
PERFIL = (
    'O Matheus trabalha com IA e extração de dados, e constrói o Solis: um assistente pessoal de IA pro desktop '
    '(Tauri, React, Python/FastAPI, SQLite), com voz em português do Brasil (palavra de ativação, transcrição pela '
    'Groq e Whisper local, fala pelo Gemini TTS e Fish Audio, o Gemini Live em tempo real), qualquer cérebro '
    '(Claude, GPT, Groq, Gemini, OpenRouter, modelos locais no Ollama, numa placa de 8 GB), ferramentas e '
    'agentes, MCP, controle do PC e do navegador. Prefere o grátis ou barato, online primeiro, e vai vender o '
    'Solis. A prioridade número 1 é a voz: chamar, ouvir, responder rápido e com voz natural.'
)

SISTEMA = (
    'Você é o Atlas, o pesquisador do Solis. Da lista de novidades da semana abaixo, escolha até 5 que sejam úteis '
    'DE VERDADE pro Matheus ou pro Solis (o perfil vem junto). Prefira o que dá pra usar já: um modelo, uma '
    'ferramenta, uma biblioteca, um recurso novo de um provedor, de preferência grátis ou barato, que melhore a '
    'voz (ativação, transcrição, fala em português, tempo real), deixe as respostas mais rápidas ou baratas, rode '
    'bem num PC com 8 GB de vídeo, ou ajude os agentes e o controle do PC. Ignore hype, notícia de empresa sem nada '
    'pra usar, polêmica e o que não serve ao perfil. Escolha pelo número da lista. Para cada uma: por que é útil '
    '(uma ou duas frases concretas: o que ele faria com isso no Solis ou no trabalho) e o que fazer (testar, ler, '
    'guardar pra depois). Se nada for útil, devolva a lista vazia: melhor nenhuma que uma inútil. Em português do '
    'Brasil.'
)
ESQUEMA = {
    'type': 'object', 'required': ['itens'],
    'properties': {'itens': {'type': 'array', 'items': {
        'type': 'object', 'required': ['numero', 'por_que', 'o_que_fazer'],
        'properties': {'numero': {'type': 'integer'}, 'por_que': {'type': 'string'},
                       'o_que_fazer': {'type': 'string'}}}}},
}

# O que é de IA, no título ou na descrição (o Hacker News e o GitHub trazem de tudo).
DE_IA = re.compile(
    r'\b(ai|llms?|gpt[\w.-]*|claude|gemini|anthropic|openai|llama|qwen|mistral|deepseek|phi-?\d|gemma|models?'
    r'|agents?|agentic|rag|embeddings?|transformers?|diffusion|voice|speech|tts|stt|whisper|asr|wake ?word'
    r'|text-to-speech|speech-to-text|mcp|inference|fine-?tun\w*|neural|machine learning|copilot|cursor|ollama'
    r'|groq|hugging ?face|vllm|llama\.cpp|gguf|quantiz\w*|multimodal|reasoning|chatbot|assistant)\b', re.I)


class Falhou(Exception):
    pass


# — as fontes ————————————————————————————————————————————————————————————————————————

async def _hacker_news(c: httpx.AsyncClient, desde: dt.datetime) -> list[dict]:
    r = await c.get('https://hn.algolia.com/api/v1/search', params={
        'tags': 'story', 'hitsPerPage': 100,
        'numericFilters': f'created_at_i>{int(desde.timestamp())},points>60'})
    r.raise_for_status()
    saida = []
    for h in r.json().get('hits', []):
        titulo = (h.get('title') or '').strip()
        if not titulo or not DE_IA.search(titulo):
            continue
        saida.append({'fonte': 'Hacker News', 'titulo': titulo, 'descricao': '',
                      'url': h.get('url') or f'https://news.ycombinator.com/item?id={h.get("objectID")}',
                      'peso': int(h.get('points') or 0), 'medida': f'{h.get("points")} pontos'})
    return saida


async def _github(c: httpx.AsyncClient, desde: dt.datetime) -> list[dict]:
    r = await c.get('https://api.github.com/search/repositories', headers={'Accept': 'application/vnd.github+json'},
                    params={'q': f'created:>{desde:%Y-%m-%d} stars:>50', 'sort': 'stars', 'order': 'desc',
                            'per_page': 60})
    r.raise_for_status()
    saida = []
    for x in r.json().get('items', []):
        texto = f'{x.get("full_name")} {x.get("description") or ""} {" ".join(x.get("topics") or [])}'
        if not DE_IA.search(texto):
            continue
        saida.append({'fonte': 'GitHub', 'titulo': x['full_name'], 'descricao': (x.get('description') or '')[:200],
                      'url': x['html_url'], 'peso': int(x.get('stargazers_count') or 0),
                      'medida': f'{x.get("stargazers_count")} estrelas'})
    return saida


async def _hugging_face(c: httpx.AsyncClient, desde: dt.datetime) -> list[dict]:
    r = await c.get('https://huggingface.co/api/models', params={'sort': 'trendingScore', 'direction': -1,
                                                                 'limit': 25})
    r.raise_for_status()
    saida = []
    for m in r.json():
        criado = m.get('createdAt') or ''
        # Só os da semana (ou do mês, com pouco do da semana): o que está em alta e é novo.
        if criado and criado[:10] < (desde - dt.timedelta(days=21)).strftime('%Y-%m-%d'):
            continue
        tipo = m.get('pipeline_tag') or ''
        saida.append({'fonte': 'Hugging Face', 'titulo': m['id'], 'descricao': tipo,
                      'url': f'https://huggingface.co/{m["id"]}', 'peso': int(m.get('likes') or 0),
                      'medida': f'{m.get("likes")} curtidas'})
    return saida


FONTES = [_hacker_news, _github, _hugging_face]


async def coletar(agora: dt.datetime | None = None) -> tuple[list[dict], dict]:
    """(as candidatas de IA da semana, quantas por fonte — ou o erro da fonte)."""
    agora = agora or dt.datetime.now()
    desde = agora - dt.timedelta(days=7)
    async with httpx.AsyncClient(timeout=PRAZO, headers=CABECALHOS, follow_redirects=True,
                                 transport=_transporte) as c:
        resultados = await asyncio.gather(*(f(c, desde) for f in FONTES), return_exceptions=True)
    candidatas, contagem = [], {}
    for f, r in zip(FONTES, resultados):
        nome = f.__name__.strip('_')
        if isinstance(r, Exception):
            contagem[nome] = f'falhou ({type(r).__name__})'
            log.info('atlas: a fonte %s falhou: %s', nome, r)
            continue
        contagem[nome] = len(r)
        candidatas += r
    # Sem repetir o mesmo link; as mais fortes de cada fonte primeiro, misturadas.
    vistos, unicas = set(), []
    for x in sorted(candidatas, key=lambda x: -x['peso']):
        chave = x['url'].rstrip('/').lower()
        if chave not in vistos:
            vistos.add(chave)
            unicas.append(x)
    por_fonte: dict[str, list[dict]] = {}
    for x in unicas:
        por_fonte.setdefault(x['fonte'], []).append(x)
    mistura = []
    while any(por_fonte.values()) and len(mistura) < CANDIDATAS_MAX:
        for lista in por_fonte.values():
            if lista and len(mistura) < CANDIDATAS_MAX:
                mistura.append(lista.pop(0))
    return mistura, contagem


# — a escolha (o cérebro) ————————————————————————————————————————————————————————————

def _lista_pro_cerebro(candidatas: list[dict]) -> str:
    return '\n'.join(f'{i}. [{x["fonte"]}, {x["medida"]}] {x["titulo"]}' + (f' — {x["descricao"]}' if x['descricao'] else '')
                     for i, x in enumerate(candidatas, 1))


def _cerebros() -> list[str]:
    """Os que respondem em JSON, na ordem dele: os de API primeiro, o local por
    último (online primeiro, a regra do Matheus; o local é a reserva sem internet)."""
    from . import apis, roteador
    ligados = [p['nome'] for p in roteador.preferencia() if p['ligado']]
    return [n for n in ligados if n in apis.PROVEDORES and apis.tem_chave(n)] + (['local'] if 'local' in ligados else [])


# A segunda passada (25/11/2026): no ensaio, o "por que" saía só do título e de
# 200 letras de descrição, e o cérebro completava o resto ("ideal pra 8 GB",
# "reduz em até 34%") sem saber. Agora ele pré-escolhe pelo título, o Solis lê a
# página de cada uma, e o porquê é escrito só com o que a página diz.
PRE_MAX = 8
PAGINA_MAX = 1500
SISTEMA_CONFIRMA = (
    'Você é o Atlas, o pesquisador do Solis. Antes você escolheu estas novidades pelo título; agora vem o começo da '
    'página de cada uma. Fique com até 5 que a PÁGINA confirma que servem pro Matheus ou pro Solis (o perfil vem '
    'junto). Escreva o por que e o que fazer só com o que está no texto da página: um número, um recurso ou uma '
    'compatibilidade só se a página disser. Se a página disser uma limitação que importa (só pra pesquisa, licença '
    'que não deixa usar num produto vendido, só inglês, precisa de placa de vídeo grande, pago), diga no por que: o '
    'Solis vai ser vendido. A que não deu pra ler, ou cuja página não confirma, descarte. Use o '
    'mesmo número de cada uma. Se nenhuma se confirmar, devolva a lista vazia. Em português do Brasil.'
)


async def _ler_pagina(c: httpx.AsyncClient, x: dict) -> str:
    """O começo da página de uma novidade, em texto ('' se não deu pra ler)."""
    try:
        if x['fonte'] == 'GitHub':
            r = await c.get(f'https://api.github.com/repos/{x["titulo"]}/readme',
                            headers={'Accept': 'application/vnd.github.raw'})
            r.raise_for_status()
            texto = r.text
        elif x['fonte'] == 'Hugging Face':
            r = await c.get(f'https://huggingface.co/{x["titulo"]}/raw/main/README.md')
            r.raise_for_status()
            texto = re.sub(r'\A---.*?---', '', r.text, flags=re.S)
        else:
            from . import web
            _, _, texto = await web.ler(x['url'])
    except Exception:  # noqa: BLE001 — sem a página, a novidade não se confirma
        return ''
    # Sem HTML, imagens e selos (os badges do README), só o texto.
    texto = re.sub(r'<[^>]+>|\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)|!\[[^\]]*\]\([^)]*\)', ' ', texto)
    return ' '.join(texto.split())[:PAGINA_MAX]


async def _perguntar(nome: str, sistema: str, prompt: str) -> dict:
    from . import apis, ollama
    if nome == 'local':
        from .main import MODELO_FUNDO
        return await ollama.responder_json(MODELO_FUNDO, sistema, prompt, ESQUEMA)
    return await apis.responder_json(nome, sistema, prompt, ESQUEMA)


def _numeros(resposta: dict, validos: set[int]) -> list[dict]:
    """Os itens da resposta com número da lista (um número inventado não vira novidade), sem repetir."""
    saida, vistos = [], set()
    for item in resposta.get('itens') or []:
        n = item.get('numero')
        if isinstance(n, int) and n in validos and n not in vistos:
            vistos.add(n)
            saida.append({'numero': n, 'por_que': str(item.get('por_que') or '').strip(),
                          'o_que_fazer': str(item.get('o_que_fazer') or '').strip()})
    return saida


async def escolher(candidatas: list[dict]) -> tuple[list[dict], str]:
    """(as escolhidas, com por_que e o_que_fazer; quem escolheu). Falhou se nenhum cérebro respondeu."""
    from . import cerebros, ollama
    falhas = (cerebros.CerebroFalhou, ollama.OllamaIndisponivel, ollama.ModeloInexistente)
    prompt = (f'O perfil:\n{PERFIL}\n\nAs novidades de IA desta semana (escolha até {PRE_MAX} pra ler):\n'
              f'{_lista_pro_cerebro(candidatas)}')
    erros = []
    for nome in _cerebros():
        try:
            pre = _numeros(await _perguntar(nome, SISTEMA, prompt), set(range(1, len(candidatas) + 1)))[:PRE_MAX]
        except falhas as e:
            erros.append(f'{nome}: {e}')
            continue
        if not pre:
            return [], nome
        async with httpx.AsyncClient(timeout=PRAZO, headers=CABECALHOS, follow_redirects=True,
                                     transport=_transporte) as c:
            paginas = await asyncio.gather(*(_ler_pagina(c, candidatas[p['numero'] - 1]) for p in pre))
        blocos = [f'{p["numero"]}. [{candidatas[p["numero"] - 1]["fonte"]}] {candidatas[p["numero"] - 1]["titulo"]}\n'
                  f'O que a página diz: {texto or "(não deu pra ler a página)"}' for p, texto in zip(pre, paginas)]
        try:
            final = _numeros(await _perguntar(nome, SISTEMA_CONFIRMA, f'O perfil:\n{PERFIL}\n\n' + '\n\n'.join(blocos)),
                             {p['numero'] for p, texto in zip(pre, paginas) if texto})
        except falhas as e:
            erros.append(f'{nome} (ao confirmar): {e}')
            continue
        return [{**candidatas[f['numero'] - 1], **f} for f in final][:ITENS_MAX], nome
    raise Falhou('; '.join(erros) or 'nenhum cérebro ligado que responda')


def relatorio(escolhidas: list[dict], candidatas: list[dict], contagem: dict, agora: dt.datetime) -> str:
    de = agora - dt.timedelta(days=7)
    fontes = ', '.join(f'{n.replace("_", " ").title()} {c}' for n, c in contagem.items())
    if not escolhidas:
        return (f'Nada que valha o seu tempo nesta semana ({de:%d/%m} a {agora:%d/%m}): olhei {len(candidatas)} '
                f'novidades de IA ({fontes}) e nenhuma serve pro Solis ou pro seu trabalho agora.')
    linhas = [f'As novidades da semana ({de:%d/%m} a {agora:%d/%m}) que servem pra você:', '']
    for i, x in enumerate(escolhidas, 1):
        linhas.append(f'{i}. **{x["titulo"]}** ({x["fonte"]}, {x["medida"]}). {x["por_que"]}'
                      + (f' O que fazer: {x["o_que_fazer"]}' if x['o_que_fazer'] else ''))
        linhas.append(f'   {x["url"]}')
    linhas += ['', f'Escolhi entre {len(candidatas)} novidades de IA da semana ({fontes}). Os links vêm direto das '
               'fontes. Se alguma não serviu, diga: o Atlas aprende com o seu voto.']
    return '\n'.join(linhas)


# — rodar ——————————————————————————————————————————————————————————————————————————————

def ultima() -> dict | None:
    return banco.ajuste('pesquisador_ultima')


async def rodar(agora: dt.datetime | None = None, avisar: bool = True) -> dict:
    """Coleta, escolhe e entrega. {'conversa', 'texto', 'itens', 'cerebro', 'candidatas'}."""
    agora = agora or dt.datetime.now().replace(microsecond=0)
    candidatas, contagem = await coletar(agora)
    if not candidatas:
        raise Falhou(f'nenhuma fonte respondeu ({contagem})')
    escolhidas, cerebro = await escolher(candidatas)
    texto = relatorio(escolhidas, candidatas, contagem, agora)
    conversa = banco.nova_conversa(titulo=TITULO)
    banco.adicionar(conversa, 'solis', texto, cerebro=cerebro, personalidade='jarvis')
    feito = {'quando': agora.isoformat(), 'conversa': conversa, 'itens': len(escolhidas), 'cerebro': cerebro,
             'candidatas': len(candidatas), 'contagem': contagem}
    banco.guardar_ajuste('pesquisador_ultima', feito)
    if avisar:
        from . import avisos
        if avisos.ligados():
            n = len(escolhidas)
            resumo = (f'{n} novidade{"s" if n != 1 else ""} da semana que serve{"m" if n != 1 else ""} pra você. '
                      'Está nos Recentes do Solis.' if n else 'Nada útil nesta semana.')
            await avisos.mostrar(AGENTE, resumo, f'atlas-{agora:%Y%m%d}')
    return {**feito, 'texto': texto}


def hora_de_rodar(agora: dt.datetime) -> bool:
    """Já passou a segunda das 9h desta semana e ainda não rodou desde então?"""
    segunda = (agora - dt.timedelta(days=(agora.weekday() - DIA) % 7)).date()
    marco = dt.datetime.combine(segunda, HORA)
    if agora < marco:
        return False
    u = ultima()
    return not u or dt.datetime.fromisoformat(u['quando']) < marco


async def vigiar() -> None:
    """O relógio semanal, dentro do servidor."""
    while True:
        try:
            if hora_de_rodar(dt.datetime.now()):
                await rodar()
        except Exception:  # noqa: BLE001 — tenta de novo na próxima volta
            log.exception('atlas: a pesquisa da semana falhou')
        await asyncio.sleep(15 * 60)
