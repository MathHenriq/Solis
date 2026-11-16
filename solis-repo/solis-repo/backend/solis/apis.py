"""Cérebros por API, no plano grátis de cada serviço: Groq, Gemini, Mistral e
OpenRouter.

Os quatro falam o mesmo formato de chamada (o `chat/completions` da OpenAI),
então é um código só: cada serviço é um endereço, uma chave e um modelo. Os
endereços foram conferidos nas páginas oficiais em 08/11/2026.

O MODELO NÃO É FIXADO NO CÓDIGO. Os nomes mudam a cada poucos meses e as
próprias documentações se contradizem (a do Mistral diz que mistral-small-latest
é a 3.2 numa página e a 4 em outra). Ao guardar a chave, o Solis pergunta ao
serviço o que existe (`GET /models`) e escolhe pela preferência abaixo; o nome
escolhido fica guardado e aparece na tela.

A chave fica no banco selada pelo cofre (DPAPI): legível só neste usuário do
Windows. Ela nunca volta pro front — a tela só sabe se existe uma.

Grátis tem preço, e a tela diz qual (`nota`): o Gemini grátis pode usar o que
recebe pra melhorar os produtos do Google; o Mistral treina até ser desligado no
console; no OpenRouter quem roda o modelo grátis pode guardar o pedido. O que é
privado nunca chega aqui — o roteador tira antes, como faz pro Claude e o Codex.
"""
import asyncio
import json
import re
import contextlib
import time
from collections.abc import AsyncIterator

import httpx

from . import banco, cofre, conexoes
from .cerebros import CerebroFalhou, pausar
from .etapas import MUDA

PROVEDORES = {
    'groq': {
        'rotulo': 'Groq',
        'base': 'https://api.groq.com/openai/v1',
        'site': 'https://console.groq.com/keys',
        'preferidos': ['openai/gpt-oss-120b', 'llama-3.3-70b-versatile'],
        'nota': 'Grátis, perto de 1.000 pedidos por dia. Modelos abertos, muito rápidos.',
    },
    'gemini': {
        'rotulo': 'Gemini',
        'base': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'site': 'https://aistudio.google.com/apikey',
        'preferidos': [],  # o Flash mais novo, ver _escolher
        'nota': 'Grátis, só os modelos Flash. No grátis o Google pode usar o que você manda pra melhorar os produtos dele.',
    },
    'mistral': {
        'rotulo': 'Mistral',
        'base': 'https://api.mistral.ai/v1',
        'site': 'https://console.mistral.ai/api-keys',
        'preferidos': ['mistral-medium-latest', 'mistral-small-latest'],
        'nota': 'Grátis no plano Experiment. Treina com o que você manda até você desligar em Privacidade, no console.',
    },
    'openrouter': {
        'rotulo': 'OpenRouter',
        'base': 'https://openrouter.ai/api/v1',
        'site': 'https://openrouter.ai/settings/keys',
        # Só os grátis (":free"); entre eles, estes primeiro.
        'preferidos': ['gpt-oss-120b', 'deepseek', 'qwen3', 'llama-3.3-70b'],
        'nota': 'Só os modelos grátis, 50 pedidos por dia. Quem roda o modelo pode guardar o que você manda.',
    },
}

# Pra listar os modelos basta pouco. Pra responder, 60 s sem receber nada (no
# começo ou no meio) é travado — o maior silêncio aceito pros CLIs (cerebros.py).
TIMEOUT_LISTA = httpx.Timeout(15.0, connect=5.0)
TIMEOUT_RESPOSTA = httpx.Timeout(60.0, connect=5.0)
# O primeiro pedaço tem prazo próprio: em 16/11/2026 o Gemini grátis ficou 60 s
# calado até o ReadTimeout, numa resposta por voz. Quem não começa em 15 s está
# falhando, e o próximo cérebro tenta. Entre um pedaço e outro, os 60 s valem.
PRIMEIRO_MAX = 15.0
# Na voz, o prazo é do pedido inteiro até a primeira palavra (não só da primeira
# linha): em 16/11/2026, com a Groq no limite, o Gemini levou 12 s só pra dizer
# 503, e a resposta falada saiu em 22 s. A Groq medida: 0,36 a 2,04 s.
PRIMEIRO_VOZ = 5.0
# Na voz, quanto o gpt-oss pensa antes de responder (None: o padrão dele).
# PROVISÓRIO: medindo tempo e acerto.
RACIOCINIO_NA_VOZ = 'low'


class ChaveRecusada(Exception):
    """O serviço não aceitou a chave (401/403)."""


class ProvedorFora(Exception):
    """Não deu pra falar com o serviço (rede, erro do lado dele)."""


def _chave_de(nome: str) -> str | None:
    selada = banco.ajuste(f'chave:{nome}')
    if not selada:
        return None
    chave = cofre.abrir(selada)
    return None if chave == cofre.ILEGIVEL else chave


def tem_chave(nome: str) -> bool:
    return nome in PROVEDORES and _chave_de(nome) is not None


def modelo(nome: str) -> str | None:
    return banco.ajuste(f'modelo:{nome}')


def _versao(texto: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r'\d+', texto))


def _escolher(nome: str, ids: list[str]) -> str | None:
    """O modelo a usar entre os que o serviço tem agora."""
    if nome == 'gemini':
        # O Flash mais novo que conversa: sem lite, sem áudio/imagem, sem
        # experimental; o estável antes do preview.
        fora = ('lite', 'tts', 'image', 'live', 'audio', 'embedding', 'exp', 'thinking')
        flash = [i for i in ids if 'flash' in i and not any(f in i for f in fora)]
        flash.sort(key=lambda i: ('preview' not in i, _versao(i)), reverse=True)
        return flash[0] if flash else None
    if nome == 'openrouter':
        ids = [i for i in ids if i.endswith(':free')]
        for parte in PROVEDORES[nome]['preferidos']:
            for i in ids:
                if parte in i:
                    return i
        return ids[0] if ids else None
    for preferido in PROVEDORES[nome]['preferidos']:
        if preferido in ids:
            return preferido
    return ids[0] if ids else None


async def listar(nome: str, chave: str, transporte: httpx.AsyncBaseTransport | None = None) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_LISTA, transport=transporte) as c:
            r = await c.get(f"{PROVEDORES[nome]['base']}/models", headers={'Authorization': f'Bearer {chave}'})
    except httpx.HTTPError as e:
        raise ProvedorFora(str(e) or type(e).__name__) from e
    if nome == 'gemini' and r.status_code in (401, 403, 404):
        # Há relato de o /models do formato OpenAI do Gemini dar 401 com chave
        # boa (o chat funcionando). Antes de recusar, pergunta pela API nativa.
        return await _listar_gemini_nativo(chave, transporte)
    if r.status_code in (401, 403):
        raise ChaveRecusada()
    if r.status_code >= 400:
        raise ProvedorFora(f'{PROVEDORES[nome]["rotulo"]} respondeu {r.status_code}')
    # O Gemini devolve "models/gemini-...", e o chat aceita sem o prefixo.
    return [m['id'].removeprefix('models/') for m in r.json().get('data', []) if m.get('id')]


async def _listar_gemini_nativo(chave: str, transporte: httpx.AsyncBaseTransport | None) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_LISTA, transport=transporte) as c:
            r = await c.get(
                'https://generativelanguage.googleapis.com/v1beta/models',
                headers={'x-goog-api-key': chave},
                params={'pageSize': 1000},
            )
    except httpx.HTTPError as e:
        raise ProvedorFora(str(e) or type(e).__name__) from e
    # A API nativa responde 400 ("API key not valid") pra chave errada.
    if r.status_code in (400, 401, 403):
        raise ChaveRecusada()
    if r.status_code >= 400:
        raise ProvedorFora(f'Gemini respondeu {r.status_code}')
    return [
        m['name'].removeprefix('models/')
        for m in r.json().get('models', [])
        if 'generateContent' in m.get('supportedGenerationMethods', ['generateContent'])
    ]


async def guardar_chave(nome: str, chave: str, transporte: httpx.AsyncBaseTransport | None = None) -> str:
    """Confere a chave no próprio serviço, escolhe o modelo e guarda os dois.
    Devolve o modelo. Chave que o serviço recusa não é guardada."""
    ids = await listar(nome, chave, transporte)
    escolhido = _escolher(nome, ids)
    if escolhido is None:
        raise ProvedorFora('nenhum modelo grátis de conversa disponível')
    banco.guardar_ajuste(f'chave:{nome}', cofre.selar(chave))
    banco.guardar_ajuste(f'modelo:{nome}', escolhido)
    return escolhido


def apagar_chave(nome: str) -> None:
    banco.apagar_ajuste(f'chave:{nome}')
    banco.apagar_ajuste(f'modelo:{nome}')


def _espera(r: httpx.Response) -> float | None:
    """Até quando (epoch) o serviço pediu pra esperar, se disse."""
    try:
        return time.time() + float(r.headers['retry-after'])
    except (KeyError, ValueError):
        return None


# As tarefas de fundo (o aprendizado com o Ollama fora) esperam mais: ninguém
# está olhando, e o modelo pensa antes.
TIMEOUT_FUNDO = httpx.Timeout(60.0, connect=5.0)
FUNDO_TENTATIVAS = 3
FUNDO_ESPERA_MAX = 30.0


async def responder_json(
    nome: str, sistema: str, prompt: str, esquema: dict, qual: str | None = None,
    transporte: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Uma resposta presa a um JSON Schema (o response_format da API), inteira,
    sem streaming. `qual`: o modelo (senão, o escolhido pra conversa). Pro
    aprendizado: não pausa o cérebro no limite grátis — quem responde a
    conversa usa outro modelo, e o limite é por modelo."""
    chave = _chave_de(nome)
    escolhido = qual or modelo(nome)
    if not chave or not escolhido:
        raise CerebroFalhou('sem chave')
    corpo = {
        'model': escolhido,
        'messages': [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': prompt}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'resposta', 'schema': esquema}},
    }
    async with contextlib.AsyncExitStack() as pilha:
        c = (conexoes.cliente(nome) if transporte is None
             else await pilha.enter_async_context(httpx.AsyncClient(transport=transporte)))
        for tentativa in range(FUNDO_TENTATIVAS):
            try:
                r = await c.post(f"{PROVEDORES[nome]['base']}/chat/completions", json=corpo,
                                 headers={'Authorization': f'Bearer {chave}'}, timeout=TIMEOUT_FUNDO)
            except httpx.HTTPError as e:
                raise CerebroFalhou(f'{type(e).__name__}: {e}'[:200]) from e
            ultima = tentativa == FUNDO_TENTATIVAS - 1
            if r.status_code == 429 and not ultima:
                # O limite por minuto (medido: ~1.300 tokens de entrada por
                # aprendizado, e o grátis do 20b aguenta 2 a 3 por minuto).
                # Ninguém espera esta resposta: espera o que a Groq disse.
                quando = _espera(r)
                await asyncio.sleep(min(FUNDO_ESPERA_MAX, max(1.0, (quando or time.time() + 10) - time.time())))
                continue
            if r.status_code == 400 and 'json_validate_failed' in r.text and not ultima:
                continue  # o modelo saiu do esquema: de novo, uma vez
            break
    if r.status_code >= 400:
        raise CerebroFalhou(f'respondeu {r.status_code}: {r.text[:200]}')
    try:
        return json.loads(r.json()['choices'][0]['message']['content'])
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise CerebroFalhou(f'não veio JSON: {r.text[:200]}') from e


async def responder(
    nome: str, sistema: str, prompt: str, etapas=MUDA, transporte: httpx.AsyncBaseTransport | None = None,
    rapido: bool = False,
) -> AsyncIterator[str]:
    """A resposta em pedaços, pelo streaming (SSE) do chat/completions.
    `rapido` (a voz): o gpt-oss pensa pouco antes de responder."""
    chave, escolhido = _chave_de(nome), modelo(nome)
    if not chave or not escolhido:
        raise CerebroFalhou('sem chave')
    corpo = {
        'model': escolhido,
        'stream': True,
        'messages': [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': prompt}],
    }
    if rapido and RACIOCINIO_NA_VOZ and 'gpt-oss' in escolhido:
        corpo['reasoning_effort'] = RACIOCINIO_NA_VOZ
    # A conexão guardada (conexoes.py); com um transporte de teste, uma só desta vez.
    async with contextlib.AsyncExitStack() as pilha:
        if transporte is None:
            c = conexoes.cliente(nome)
        else:
            c = await pilha.enter_async_context(httpx.AsyncClient(transport=transporte))
        prazo = PRIMEIRO_VOZ if rapido else None
        try:
            async with asyncio.timeout(prazo) as ate_a_primeira:
                async with c.stream(
                    'POST',
                    f"{PROVEDORES[nome]['base']}/chat/completions",
                    headers={'Authorization': f'Bearer {chave}'},
                    json=corpo,
                    timeout=TIMEOUT_RESPOSTA,
                ) as r:
                    etapas.marcar('pedido', cerebro=nome)
                    if r.status_code == 429:
                        pausar(nome, _espera(r), 'o limite grátis acabou')
                        raise CerebroFalhou('o limite grátis acabou')
                    if r.status_code in (401, 403):
                        pausar(nome, time.time() + 24 * 3600, 'a chave foi recusada')
                        raise CerebroFalhou('a chave foi recusada')
                    if r.status_code >= 400:
                        await r.aread()
                        raise CerebroFalhou(f'respondeu {r.status_code}: {r.text[:160]}')
                    pensou = False
                    linhas = r.aiter_lines()
                    primeira = True
                    while True:
                        try:
                            if primeira:
                                linha = await asyncio.wait_for(anext(linhas), PRIMEIRO_MAX)
                                primeira = False
                            else:
                                linha = await anext(linhas)
                        except StopAsyncIteration:
                            return
                        except asyncio.TimeoutError as e:
                            raise CerebroFalhou(f'não começou a responder em {PRIMEIRO_MAX:.0f} s') from e
                        if not linha.startswith('data:'):
                            continue
                        dado = linha[5:].strip()
                        if dado == '[DONE]':
                            return
                        try:
                            delta = json.loads(dado)['choices'][0].get('delta', {})
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        # Modelos que raciocinam mandam o raciocínio à parte; não vai
                        # pra tela, só o fato de que está pensando.
                        if not pensou and (delta.get('reasoning') or delta.get('reasoning_content')):
                            etapas.marcar('pensando', cerebro=nome)
                            pensou = True
                        if delta.get('content'):
                            ate_a_primeira.reschedule(None)
                            yield delta['content']
        except TimeoutError as e:
            raise CerebroFalhou(f'não começou a responder em {prazo:.0f} s') from e
        except httpx.HTTPError as e:
            raise CerebroFalhou(f'{type(e).__name__}: {e}'[:200]) from e
