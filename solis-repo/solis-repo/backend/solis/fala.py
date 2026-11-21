"""O Solis falando: a resposta vira voz, por uma cadeia de vozes — a melhor da
nuvem primeiro, a reserva da nuvem depois, e a local quando a internet cai.

Escolhido ouvindo e medindo (09/11/2026, docs/ESCOPO.md → Voz). As locais que
rodam no notebook soaram esquisitas em português pro Matheus (Kokoro, Piper,
a Maria do Windows, e o Chatterbox pelo ONNX, que ainda entrava em repetição);
as locais mais fortes pedem o PyTorch, que o Controle Inteligente de
Aplicativos bloqueia. Decisão dele: nuvem na frente, com reserva, e a local
não sai — é o que fala sem internet.

A cadeia, na ordem:
1. Gemini TTS, com a chave do Gemini colada em Configurações → Cérebros. A
   mais natural; detecta a língua sozinho. Voz Aoede, escolhida pelo Matheus
   ouvindo 8 das 30. Modelo gemini-3.8-flash-lite-tts no plano grátis: o
   flash-tts grátis dá 10 pedidos por dia (medido com a chave dele, 09/11/2026)
   e cada resposta são 2 a 4 pedidos; o limite do Lite a documentação não diz.
   Pago (preço oficial até 31/12/2026): US$ 0,0015 a cada 10 s de fala no Lite,
   0,00225 no Flash — e no pago o Google não usa o conteúdo pros produtos dele.
2. Ava (en-US-AvaMultilingualNeural), a voz do Copilot pelo serviço de leitura
   do Edge: sem chave, fala português e inglês. Sem garantia de serviço —
   medido de 1,3 a 8 s até o primeiro áudio, e uma vez não respondeu.
3. Kokoro local (kokoro-onnx): pf_dora em português, af_heart em inglês.

Em teste (11/11/2026): a Fish Audio (S2.1 Pro), na frente da cadeia quando há
chave colada (Configurações → Voz). O modelo s2.1-pro-free é grátis por "um
período inicial" sem data certa, com uso justo; os pedidos podem ser usados
pra melhorar o modelo deles (por isso, como as outras da nuvem, nunca o
privado). Pago: US$ 15 por milhão de bytes de texto (SOLIS_FALA_FISH=s2.1-pro).
Sem chave, a cadeia é a de sempre.

Privado nunca vai pra nuvem: conversa com algo privado, ou texto de saúde,
dinheiro ou documento (memoria.SENSIVEL), é falado só pela local.
"""
import asyncio
import base64
import io
import logging
import os
import re
import threading
import time
import wave
from collections import OrderedDict
from pathlib import Path

import httpx

from . import banco, conexoes, memoria

log = logging.getLogger('solis.fala')

PASTA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Solis' / 'voz'
GEMINI_MODELO = os.environ.get('SOLIS_FALA_GEMINI', 'gemini-3.8-flash-lite-tts')
GEMINI_VOZ = os.environ.get('SOLIS_FALA_GEMINI_VOZ', 'Aoede')  # escolhida pelo Matheus ouvindo (09/11/2026)
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/interactions'
AVA = 'en-US-AvaMultilingualNeural'
FISH_URL = 'https://api.fish.audio/v1/tts'
FISH_VOZES_URL = 'https://api.fish.audio/model'
FISH_MODELO = os.environ.get('SOLIS_FALA_FISH', 's2.1-pro-free')
KOKORO_VOZ = {'pt': ('pf_dora', 'pt-br'), 'en': ('af_heart', 'en-us')}
TEMPO_NUVEM = 15.0  # segundos até desistir da nuvem e cair pra próxima
PARTE_MAX = 280  # caracteres por pedaço: o primeiro áudio chega antes, e a fala segue
PRIMEIRA_MAX = 90
CACHE_MAX = 64
OCIOSO = 10 * 60


class SemVoz(Exception):
    """Nenhuma voz da cadeia conseguiu falar."""


# — Texto pra fala ———————————————————————————————————————————————————————————————

def limpar(texto: str) -> str:
    """O texto como se fala: sem markdown, sem código, sem endereço."""
    texto = re.sub(r'```.*?```', ' (um trecho de código). ', texto, flags=re.S)
    texto = re.sub(r'`([^`]*)`', r'\1', texto)
    # O link em markdown antes do endereço solto: senão sobra "[a doc](o link".
    texto = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', texto)
    texto = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', texto)
    texto = re.sub(r'https?://\S+', 'o link', texto)
    # [ \t] e não \s: o \s atravessa a quebra de linha e engolia a linha em branco.
    texto = re.sub(r'^[ \t]{0,3}#{1,6}[ \t]*', '', texto, flags=re.M)
    texto = re.sub(r'^[ \t]*(?:[-*+]|\d+[.)])[ \t]+', '', texto, flags=re.M)
    texto = re.sub(r'(\*\*|__|\*|_|~~)(.+?)\1', r'\2', texto)
    texto = re.sub(r'\n[ \t]*\n\s*', '. ', texto)
    texto = re.sub(r'[ \t]*\n\s*', ', ', texto)
    # Pontuação dobrada que as trocas acima deixam (":." vira ":", ".," vira ".").
    texto = re.sub(r'([.!?:;,])(?:\s*[.,])+', r'\1', texto)
    return ' '.join(texto.split()).strip()


def partes(texto: str) -> list[str]:
    """Frases agrupadas em pedaços de até PARTE_MAX: o primeiro fica pronto
    rápido, e os outros são gerados enquanto ele toca."""
    frases = re.split(r'(?<=[.!?…])\s+', limpar(texto))
    saida, atual = [], ''
    for f in frases:
        if not f:
            continue
        # O primeiro pedaço é curto (uma frase, até PRIMEIRA_MAX): é ele que a
        # pessoa espera, e a Ava levou 8 a 9 s pra uma frase de 100 caracteres
        # (medido no servidor real, 09/11/2026). Os outros são gerados enquanto
        # o primeiro toca.
        limite = PRIMEIRA_MAX if not saida else PARTE_MAX
        if atual and len(atual) + 1 + len(f) > limite:
            saida.append(atual)
            atual = f
        else:
            atual = f'{atual} {f}'.strip()
        while len(atual) > PARTE_MAX * 2:  # frase enorme sem ponto: corta na vírgula ou no espaço
            corte = max(atual.rfind(', ', 0, PARTE_MAX), atual.rfind(' ', 0, PARTE_MAX))
            saida.append(atual[:corte].strip(' ,'))
            atual = atual[corte:].strip(' ,')
    if atual:
        saida.append(atual)
    return saida


_PT = re.compile(r'[ãõçáéíóúâêô]|\b(não|você|que|de|para|pra|com|uma|está|é|isso|tem)\b', re.I)
_EN = re.compile(r'\b(the|and|you|is|are|to|of|for|with|this|that|have|it)\b', re.I)


def lingua(texto: str) -> str:
    """'pt' ou 'en', pelo que aparece mais. Empate, português."""
    return 'en' if len(_EN.findall(texto)) > len(_PT.findall(texto)) else 'pt'


def privado(texto: str, conversa: int | None) -> bool:
    return bool(
        (conversa is not None and banco.tem_privada(conversa))
        or memoria.eh_privado(texto)
        or memoria.SENSIVEL.search(texto)
    )


# — As vozes ———————————————————————————————————————————————————————————————————————

def modelo_gemini() -> str:
    """O modelo de TTS do Gemini (ajuste modelo_fala_gemini), ou o padrão."""
    return banco.ajuste('modelo_fala_gemini') or GEMINI_MODELO


def _espera(texto: str) -> float | None:
    """Os segundos do "retry in 11h57m24s" de um 429 do Google, se houver."""
    m = re.search(r'retry in ((?:\d+h)?(?:\d+m)?(?:[\d.]+s)?)', texto)
    if not m or not m.group(1):
        return None
    partes = dict((u, float(v)) for v, u in re.findall(r'([\d.]+)([hms])', m.group(1)))
    return partes.get('h', 0) * 3600 + partes.get('m', 0) * 60 + partes.get('s', 0)


# As 30 vozes do Gemini TTS (documentação, 09/11/2026).
VOZES_GEMINI = [
    'Zephyr', 'Puck', 'Charon', 'Kore', 'Fenrir', 'Leda', 'Orus', 'Aoede', 'Callirrhoe', 'Autonoe', 'Enceladus',
    'Iapetus', 'Umbriel', 'Algieba', 'Despina', 'Erinome', 'Algenib', 'Rasalgethi', 'Laomedeia', 'Achernar',
    'Alnilam', 'Schedar', 'Gacrux', 'Pulcherrima', 'Achird', 'Zubenelgenubi', 'Vindemiatrix', 'Sadachbia',
    'Sadaltager', 'Sulafat',
]
MODELOS_GEMINI = ['gemini-3.8-flash-tts', 'gemini-3.8-flash-lite-tts']


def ajustar(voz: str | None = None, modelo: str | None = None) -> None:
    """Guarda a voz e o modelo do Gemini. Trocar o modelo tira o Gemini do
    descanso: o limite é por modelo, e o outro pode ter cota."""
    if voz is not None:
        if voz not in VOZES_GEMINI:
            raise ValueError(f'voz desconhecida: {voz}')
        banco.guardar_ajuste('voz_gemini', voz)
    if modelo is not None:
        if modelo not in MODELOS_GEMINI:
            raise ValueError(f'modelo desconhecido: {modelo}')
        banco.guardar_ajuste('modelo_fala_gemini', modelo)
        _fora_ate.pop('gemini', None)
        _cache.clear()


def voz_gemini() -> str:
    """A voz do Gemini escolhida (ajuste voz_gemini), ou a padrão."""
    return banco.ajuste('voz_gemini') or GEMINI_VOZ


async def gemini(
    texto: str, lingua_: str, transporte: httpx.AsyncBaseTransport | None = None, voz: str | None = None,
) -> bytes:
    from . import apis
    chave = apis._chave_de('gemini')
    if not chave:
        raise SemVoz('sem chave do Gemini')
    corpo = {
        'model': modelo_gemini(),
        'input': [{'type': 'user_input', 'content': [{'type': 'text', 'text': texto}]}],
        'response_format': {'type': 'audio'},
        'generation_config': {'speech_config': [{'voice': voz or voz_gemini()}]},
    }
    async with httpx.AsyncClient(timeout=TEMPO_NUVEM, transport=transporte) as c:
        r = await c.post(GEMINI_URL, json=corpo, headers={'x-goog-api-key': chave})
    if r.status_code >= 400:
        raise SemVoz(f'Gemini respondeu {r.status_code}: {r.text[:160]}')
    audio = [
        parte['data']
        for passo in r.json().get('steps', []) if passo.get('type') == 'model_output'
        for parte in passo.get('content', []) if parte.get('type') == 'audio' and parte.get('data')
    ]
    if not audio:
        raise SemVoz('Gemini não devolveu áudio')
    return base64.b64decode(audio[-1])


def chave_fish() -> str | None:
    from . import apis
    return apis._chave_de('fish')


def voz_fish() -> str | None:
    """O id da voz da Fish escolhida (ajuste voz_fish); None = a padrão deles."""
    return banco.ajuste('voz_fish')


async def fish(
    texto: str, lingua_: str, transporte: httpx.AsyncBaseTransport | None = None, voz: str | None = None,
) -> bytes:
    chave = chave_fish()
    if not chave:
        raise SemVoz('sem chave da Fish Audio')
    corpo = {
        'text': texto,
        'format': 'mp3',
        # balanced: menos espera até o primeiro áudio (a documentação fala em
        # ~300 ms), com a mesma voz. O idioma só acerta a leitura de números e
        # siglas — a voz é a da referência.
        'latency': 'balanced',
        'language': 'pt-BR' if lingua_ == 'pt' else 'en',
    }
    if voz or voz_fish():
        corpo['reference_id'] = voz or voz_fish()
    async with httpx.AsyncClient(timeout=TEMPO_NUVEM, transport=transporte) as c:
        r = await c.post(FISH_URL, json=corpo, headers={'Authorization': f'Bearer {chave}', 'model': FISH_MODELO})
    if r.status_code >= 400:
        raise SemVoz(f'Fish respondeu {r.status_code}: {r.text[:160]}')
    if not r.content:
        raise SemVoz('Fish não devolveu áudio')
    return r.content


ORDENS_FISH = ('score', 'task_count', 'created_at')


async def vozes_fish(
    transporte: httpx.AsyncBaseTransport | None = None, chave: str | None = None, busca: str = '',
    pagina: int = 1, ordem: str = 'score', lingua_: str | None = 'pt', etiqueta: str | None = None,
) -> dict:
    """Uma página da biblioteca pública de vozes da Fish: id, nome, descrição,
    etiquetas, usos, curtidas e a amostra deles. `busca` procura no nome;
    `ordem` é a da Fish (score = a nota deles; task_count = mais usadas;
    created_at = mais novas); `etiqueta` filtra (male, female, calm...)."""
    chave = chave or chave_fish()
    if not chave:
        raise SemVoz('sem chave da Fish Audio')
    params = {'sort_by': ordem if ordem in ORDENS_FISH else 'score', 'page_size': 20, 'page_number': max(1, pagina)}
    if lingua_:
        params['language'] = lingua_
    if busca.strip():
        params['title'] = busca.strip()[:80]
    if etiqueta:
        params['tag'] = etiqueta
    async with httpx.AsyncClient(timeout=TEMPO_NUVEM, transport=transporte) as c:
        r = await c.get(FISH_VOZES_URL, params=params, headers={'Authorization': f'Bearer {chave}'})
    if r.status_code >= 400:
        raise SemVoz(f'Fish respondeu {r.status_code}: {r.text[:160]}')
    dados = r.json()
    vozes = [
        {'id': v['_id'], 'nome': (v.get('title') or v['_id']).strip(), 'descricao': (v.get('description') or '').strip()[:240],
         'etiquetas': (v.get('tags') or [])[:8], 'linguas': v.get('languages') or [], 'usos': v.get('task_count', 0),
         'curtidas': v.get('like_count', 0),
         'amostra': next((a.get('audio') for a in v.get('samples') or [] if a.get('audio')), None)}
        for v in dados.get('items', [])
        if v.get('_id') and v.get('state', 'trained') == 'trained' and not v.get('dmca_taken_down')
    ]
    return {'vozes': vozes, 'tem_mais': bool(dados.get('has_more'))}


async def guardar_chave_fish(chave: str, transporte: httpx.AsyncBaseTransport | None = None) -> None:
    """Confere a chave na própria Fish e guarda
    selada, como as dos cérebros. Chave recusada não é guardada."""
    from . import cofre
    # A lista pública de vozes responde até sem chave válida (conferido: 200
    # com uma chave inventada); a das vozes da própria conta (self=true) não.
    async with httpx.AsyncClient(timeout=TEMPO_NUVEM, transport=transporte) as c:
        r = await c.get(FISH_VOZES_URL, params={'self': 'true', 'page_size': 1},
                        headers={'Authorization': f'Bearer {chave.strip()}'})
    if r.status_code >= 400:
        raise SemVoz(f'Fish recusou a chave ({r.status_code})')
    banco.guardar_ajuste('chave:fish', cofre.selar(chave.strip()))
    _fora_ate.pop('fish', None)
    _cache.clear()


def esquecer_chave_fish() -> None:
    banco.apagar_ajuste('chave:fish')
    _cache.clear()


def escolher_voz_fish(voz: str | None, nome: str | None = None) -> None:
    banco.guardar_ajuste('voz_fish', voz or None)
    # O nome vai junto: a tela mostra qual está em uso sem perguntar à Fish.
    banco.guardar_ajuste('voz_fish_nome', (nome or '').strip()[:120] or None if voz else None)
    _cache.clear()


def nome_voz_fish() -> str | None:
    return banco.ajuste('voz_fish_nome')


async def ava(texto: str, lingua_: str) -> bytes:
    import edge_tts
    audio = bytearray()

    async def ler():
        async for p in edge_tts.Communicate(texto, AVA).stream():
            if p['type'] == 'audio':
                audio.extend(p['data'])
    try:
        await asyncio.wait_for(ler(), TEMPO_NUVEM)
    except Exception as e:
        raise SemVoz(f'Ava: {type(e).__name__}') from e
    if not audio:
        raise SemVoz('Ava não devolveu áudio')
    return bytes(audio)


_kokoro = None
_kokoro_uso = 0.0
_kokoro_trava = threading.Lock()


def _kokoro_agora(texto: str, lingua_: str) -> bytes:
    global _kokoro, _kokoro_uso
    import numpy as np
    with _kokoro_trava:
        if _kokoro is None:
            modelo = PASTA / 'kokoro' / 'kokoro-v1.0.int8.onnx'
            vozes = PASTA / 'kokoro' / 'voices-v1.0.bin'
            if not (modelo.exists() and vozes.exists()):
                raise SemVoz(f'falta a Kokoro em {PASTA / "kokoro"}')
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(str(modelo), str(vozes))
        voz, codigo = KOKORO_VOZ[lingua_]
        amostras, taxa = _kokoro.create(texto, voice=voz, speed=1.0, lang=codigo)
        _kokoro_uso = time.monotonic()
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((np.clip(amostras, -1, 1) * 32767).astype(np.int16).tobytes())
    return saida.getvalue()


async def kokoro(texto: str, lingua_: str) -> bytes:
    return await asyncio.to_thread(_kokoro_agora, texto, lingua_)


# Nome, tipo do áudio, função. A ordem é a cadeia.
NUVEM = [('fish', 'audio/mpeg', fish), ('gemini', 'audio/wav', gemini), ('ava', 'audio/mpeg', ava)]
LOCAL = [('kokoro', 'audio/wav', kokoro)]

# A voz que falhou por limite ou chave fica fora até esta hora (como os cérebros).
_fora_ate: dict[str, float] = {}
_cache: OrderedDict = OrderedDict()
# Por que as vozes antes da que falou falharam, na última fala (vai no
# cabeçalho X-Solis-Antes da rota: o que caiu fica visível sem abrir o log).
ultimos_motivos: list[str] = []


async def falar(texto: str, conversa: int | None = None, voz: str | None = None) -> tuple[bytes, str, str]:
    """(áudio, tipo, quem falou) de um pedaço de texto. SemVoz se ninguém.
    `voz`: uma voz do Gemini no lugar da escolhida (pra ouvir antes de escolher)."""
    texto = limpar(texto)
    if not texto:
        raise SemVoz('nada pra falar')
    lingua_ = lingua(texto)
    cadeia = LOCAL if privado(texto, conversa) else NUVEM + LOCAL
    if voz:
        # Ouvir uma voz do Gemini antes de escolher: quem fala é o Gemini, não
        # a Fish que viria antes dele na cadeia.
        cadeia = [c for c in cadeia if c[0] != 'fish']
    chave = (texto, voz or voz_gemini(), voz_fish(), tuple(n for n, _, _ in cadeia))
    if chave in _cache:
        _cache.move_to_end(chave)
        return _cache[chave]
    motivos = []
    ultimos_motivos.clear()
    for nome, tipo, funcao in cadeia:
        if _fora_ate.get(nome, 0) > time.time():
            motivos.append(f'{nome}: descansando')
            continue
        try:
            audio = await (funcao(texto, lingua_, voz=voz) if nome == 'gemini' and voz else funcao(texto, lingua_))
        except SemVoz as e:
            motivos.append(f'{nome}: {e}')
            # Chave recusada ou limite: a voz descansa em vez de ser tentada (e
            # esperada) a cada pedaço — o tempo que o Google mandar ("retry in
            # 11h57m": o limite diário do plano grátis), ou 10 min.
            if re.search(r'\b(401|403|429)\b', str(e)):
                _fora_ate[nome] = time.time() + (_espera(str(e)) or 600)
            continue
        except Exception as e:  # rede, biblioteca: segue a cadeia
            motivos.append(f'{nome}: {type(e).__name__}')
            continue
        resultado = (audio, tipo, nome)
        _cache[chave] = resultado
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
        if motivos:
            log.info('fala por %s (antes: %s)', nome, '; '.join(motivos))
            ultimos_motivos.extend(motivos)
        return resultado
    raise SemVoz('; '.join(motivos) or 'nenhuma voz disponível')


# Só os testes trocam: um transporte falso no lugar da rede.
_transporte_fish: httpx.AsyncBaseTransport | None = None


DEMORA_ANOTAR_S = 1.5


def _anotar_demora(t0: float, quem: str, texto: str) -> None:
    """Quanto o primeiro som de um pedaço demorou, quando passa de 1,5 s — sem
    o que foi dito: quem falou e o tamanho. O Matheus: "algumas vezes demora pra
    sair o áudio" (18/11/2026); o log diz se foi a voz e qual."""
    demora = time.monotonic() - t0
    if demora > DEMORA_ANOTAR_S:
        log.info('fala: primeiro som em %.1f s por %s (%d caracteres)', demora, quem, len(texto))


async def falar_aos_pedacos(texto: str, conversa: int | None = None):
    """(áudio em pedaços, tipo, quem falou): como falar(), mas a Fish manda o
    áudio enquanto gera — medido com a chave do Matheus (11/11/2026): o
    primeiro pedaço em 0,7–0,8 s, contra ~3 s do áudio inteiro. Se a Fish
    falhar antes do primeiro pedaço, segue a cadeia de sempre (inteiro).
    Privado nunca chega aqui na Fish: a cadeia dele é só a local."""
    limpo = limpar(texto)
    if not limpo:
        raise SemVoz('nada pra falar')
    lingua_ = lingua(limpo)
    chave_cache = (limpo, voz_gemini(), voz_fish(), tuple(n for n, _, _ in NUVEM + LOCAL))
    nuvem = not privado(limpo, conversa)
    t0 = time.monotonic()
    # A voz G primeiro (o teste cego de 21/11/2026), depois a Fish (a segunda).
    if nuvem and chave_cache not in _cache and _fora_ate.get('gemini-flash', 0) <= time.time():
        try:
            pedacos = await _gemini_aos_pedacos(limpo, chave_cache)
            _anotar_demora(t0, 'gemini-flash', limpo)
            return pedacos, 'audio/mpeg', 'gemini-flash'
        except SemVoz as e:
            log.info('gemini flash aos pedaços falhou (%s): segue pra Fish', str(e)[:200])
            if re.search(r'\b(401|403|429)\b', str(e)):
                # O limite diário do grátis: descansa o que o Google mandar (ou 10 min).
                _fora_ate['gemini-flash'] = time.time() + (_espera(str(e)) or 600)
        except httpx.HTTPError as e:
            log.info('gemini flash aos pedaços caiu (%s): segue pra Fish', type(e).__name__)
    if nuvem and chave_cache not in _cache and chave_fish() and _fora_ate.get('fish', 0) <= time.time():
        try:
            pedacos = await _fish_aos_pedacos(limpo, lingua_, chave_cache)
            _anotar_demora(t0, 'fish', limpo)
            return pedacos, 'audio/mpeg', 'fish'
        except SemVoz as e:
            log.info('fish aos pedaços falhou (%s): segue a cadeia', e)
            if re.search(r'\b(401|403|429)\b', str(e)):
                _fora_ate['fish'] = time.time() + 600
        except httpx.HTTPError as e:
            log.info('fish aos pedaços caiu (%s): segue a cadeia', type(e).__name__)
    audio, tipo, quem = await falar(texto, conversa)
    _anotar_demora(t0, quem, limpo)

    async def inteiro():
        yield audio
    return inteiro(), tipo, quem


async def _fish_aos_pedacos(texto: str, lingua_: str, chave_cache) -> 'AsyncIterator[bytes]':
    """Abre o pedido na Fish e espera o PRIMEIRO pedaço aqui — é aqui que a
    falha aparece, enquanto ainda dá pra cair pra outra voz."""
    corpo = {'text': texto, 'format': 'mp3', 'latency': 'balanced', 'language': 'pt-BR' if lingua_ == 'pt' else 'en'}
    if voz_fish():
        corpo['reference_id'] = voz_fish()
    # A conexão guardada (conexoes.py); com um transporte de teste, uma só desta vez.
    proprio = _transporte_fish is not None
    cliente = httpx.AsyncClient(transport=_transporte_fish) if proprio else conexoes.cliente('fish')
    try:
        r = await cliente.send(
            cliente.build_request('POST', FISH_URL, json=corpo, timeout=TEMPO_NUVEM,
                                  headers={'Authorization': f'Bearer {chave_fish()}', 'model': FISH_MODELO}),
            stream=True,
        )
        if r.status_code >= 400:
            corpo_erro = (await r.aread()).decode(errors='replace')[:160]
            await r.aclose()
            raise SemVoz(f'Fish respondeu {r.status_code}: {corpo_erro}')
        pedacos = r.aiter_bytes()
        primeiro = await anext(pedacos, b'')
        if not primeiro:
            await r.aclose()
            raise SemVoz('Fish não devolveu áudio')
    except BaseException:
        if proprio:
            await cliente.aclose()
        raise

    async def resto():
        recebido = [primeiro]
        completo = False
        try:
            yield primeiro
            async for p in pedacos:
                recebido.append(p)
                yield p
            completo = True
        finally:
            await r.aclose()
            if proprio:
                await cliente.aclose()
            # Inteiro, entra no cache como os outros: repetir a frase é na hora.
            if completo:
                _cache[chave_cache] = (b''.join(recebido), 'audio/mpeg', 'fish')
                while len(_cache) > CACHE_MAX:
                    _cache.popitem(last=False)
    return resto()


# — A voz G (21/11/2026): o Gemini Flash TTS (não o Lite), Aoede, em pedaços ————
# O teste cego do Matheus deu G=5 (Flash TTS · Aoede), A=4 (Fish), C=E=3 (o Lite)
# — "a mais direta pra passar a informação, sem cara de IA, e a entonação".
# Pelo endpoint de sempre (interactions) ela devolvia a frase inteira em 4 a 5 s;
# pelo streamGenerateContent (SSE), medido: o primeiro pedaço em 0,92 s e a frase
# em 2,2 s. Vem em PCM 24 kHz; vira mp3 enquanto chega (a tela toca mp3 em pedaços,
# como a Fish). Grátis: 10 pedidos por dia (cai pra Fish quando acaba); pago,
# US$ 0,00225 a cada 10 s de fala (~US$ 0,0135 por minuto).
GEMINI_FLUXO_MODELO = os.environ.get('SOLIS_FALA_GEMINI_FLUXO', 'gemini-3.8-flash-tts')
GEMINI_FLUXO_URL = 'https://generativelanguage.googleapis.com/v1beta/models/{modelo}:streamGenerateContent?alt=sse'
_transporte_gemini: httpx.AsyncBaseTransport | None = None  # só os testes trocam


class _PcmEmMp3:
    """PCM 16 bits mono (24 kHz) em mp3, aos pedaços (libmp3lame, pelo av)."""

    def __init__(self, taxa: int = 24000):
        import av
        self._av = av
        self.cc = av.CodecContext.create('libmp3lame', 'w')
        self.cc.sample_rate = taxa
        self.cc.layout = 'mono'
        self.cc.format = 's16p'
        self.cc.bit_rate = 64000
        self.taxa = taxa
        self.fila = av.AudioFifo()
        self.pts = 0

    def _sair(self, frame) -> bytes:
        return b''.join(bytes(p) for p in self.cc.encode(frame))

    def __call__(self, pcm: bytes) -> bytes:
        import numpy as np
        if not pcm:
            return b''
        amostras = np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype=np.int16).reshape(1, -1)
        quadro = self._av.AudioFrame.from_ndarray(amostras, format='s16p', layout='mono')
        quadro.sample_rate = self.taxa
        quadro.pts = None
        self.fila.write(quadro)
        saida = b''
        tamanho = self.cc.frame_size or 1152
        while self.fila.samples >= tamanho:
            q = self.fila.read(tamanho)
            q.pts, self.pts = self.pts, self.pts + tamanho
            saida += self._sair(q)
        return saida

    def fim(self) -> bytes:
        saida = b''
        if self.fila.samples:
            q = self.fila.read(self.fila.samples)
            q.pts = self.pts
            saida += self._sair(q)
        return saida + self._sair(None)


async def _gemini_aos_pedacos(texto: str, chave_cache) -> 'AsyncIterator[bytes]':
    """Abre o pedido no Gemini Flash TTS e espera o PRIMEIRO pedaço de áudio
    aqui — é onde a falha (limite do grátis, chave) aparece, e ainda dá pra cair
    pra Fish."""
    import json as _json

    from . import apis
    chave = apis._chave_de('gemini')
    if not chave:
        raise SemVoz('sem chave do Gemini')
    corpo = {'contents': [{'role': 'user', 'parts': [{'text': texto}]}],
             'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {
                 'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voz_gemini()}}}}}
    cliente = httpx.AsyncClient(transport=_transporte_gemini, timeout=TEMPO_NUVEM)
    try:
        r = await cliente.send(cliente.build_request(
            'POST', GEMINI_FLUXO_URL.format(modelo=GEMINI_FLUXO_MODELO), json=corpo,
            headers={'x-goog-api-key': chave}), stream=True)
        if r.status_code >= 400:
            erro = (await r.aread()).decode(errors='replace')[:300]
            await r.aclose()
            raise SemVoz(f'Gemini Flash TTS respondeu {r.status_code}: {erro}')
        linhas = r.aiter_lines()

        async def pcm():
            async for linha in linhas:
                if not linha.startswith('data:'):
                    continue
                for c in _json.loads(linha[5:]).get('candidates', []):
                    for p in c.get('content', {}).get('parts', []):
                        if (p.get('inlineData') or {}).get('data'):
                            yield base64.b64decode(p['inlineData']['data'])

        fonte = pcm()
        mp3 = _PcmEmMp3()
        primeiro = b''
        async for bruto in fonte:
            primeiro = mp3(bruto)
            if primeiro:
                break
        if not primeiro:
            await r.aclose()
            raise SemVoz('Gemini Flash TTS não devolveu áudio')
    except BaseException:
        await cliente.aclose()
        raise

    async def resto():
        recebido = [primeiro]
        completo = False
        try:
            yield primeiro
            async for bruto in fonte:
                p = mp3(bruto)
                if p:
                    recebido.append(p)
                    yield p
            ultimo = mp3.fim()
            if ultimo:
                recebido.append(ultimo)
                yield ultimo
            completo = True
        finally:
            await r.aclose()
            await cliente.aclose()
            if completo:
                _cache[chave_cache] = (b''.join(recebido), 'audio/mpeg', 'gemini-flash')
                while len(_cache) > CACHE_MAX:
                    _cache.popitem(last=False)
    return resto()


def descarregar_se_ocioso() -> bool:
    global _kokoro
    with _kokoro_trava:
        if _kokoro is not None and time.monotonic() - _kokoro_uso > OCIOSO:
            _kokoro = None
            return True
    return False


async def vigiar() -> None:
    while True:
        await asyncio.sleep(60)
        descarregar_se_ocioso()


# — Frases fixas (a narração do IDEIAS.md) ——————————————————————————————————————
# O que o Solis diz enquanto um cérebro lento trabalha: pela voz, o Claude leva
# de 3,5 a 14 s até a primeira palavra, e era silêncio. Cada frase é gerada uma
# vez, com a voz escolhida, e fica no disco — depois, custo zero e sem espera.
# Texto fixo, nada do Matheus: pode ir pra voz de nuvem.
FRASES = {
    'claude': 'Vou passar pro Claude, um instante.',
    'codex': 'Vou passar pro Codex, um instante.',
}
PASTA_FRASES = PASTA / 'frases'


def _arquivo_da_frase(nome: str, ext: str) -> Path:
    import hashlib
    # A voz escolhida entra na chave: trocou a voz, a frase é gravada de novo.
    marca = hashlib.sha1(f'{FRASES[nome]}|{voz_fish()}|{voz_gemini()}|{FISH_MODELO}'.encode()).hexdigest()[:12]
    return PASTA_FRASES / f'{nome}-{marca}.{ext}'


async def frase(nome: str) -> tuple[bytes, str, str]:
    """(áudio, tipo, quem) de uma frase fixa: do disco, ou gerada agora e guardada.
    KeyError se a frase não existe."""
    texto = FRASES[nome]
    for ext, tipo in (('mp3', 'audio/mpeg'), ('wav', 'audio/wav')):
        arquivo = _arquivo_da_frase(nome, ext)
        if arquivo.is_file():
            return arquivo.read_bytes(), tipo, 'gravada'
    audio, tipo, quem = await falar(texto)
    # Só fica gravada na voz escolhida: com a Fish configurada, a reserva que
    # falou porque a Fish caiu não vira a frase pra sempre.
    if quem == 'fish' or (not chave_fish() and quem not in {n for n, _, _ in LOCAL}):
        PASTA_FRASES.mkdir(parents=True, exist_ok=True)
        _arquivo_da_frase(nome, 'mp3' if tipo == 'audio/mpeg' else 'wav').write_bytes(audio)
    return audio, tipo, quem


async def gravar_frases() -> None:
    """Grava (em segundo plano, quando o servidor sobe) as frases que faltam.
    Só com a Fish: é a voz de nuvem que leva ~2,5 s pra gerar a frase (medido
    em 16/11/2026: 2,47 s a primeira vez, 0,004 a 0,013 s do disco depois)."""
    if not chave_fish():
        return
    for nome in FRASES:
        try:
            await frase(nome)
        except Exception as e:  # noqa: BLE001 — sem a frase, ela é gerada na hora
            log.info('a frase %s não foi gravada: %s', nome, e)
