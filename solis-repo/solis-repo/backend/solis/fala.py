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

from . import banco, memoria

log = logging.getLogger('solis.fala')

PASTA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Solis' / 'voz'
GEMINI_MODELO = os.environ.get('SOLIS_FALA_GEMINI', 'gemini-3.8-flash-lite-tts')
GEMINI_VOZ = os.environ.get('SOLIS_FALA_GEMINI_VOZ', 'Aoede')  # escolhida pelo Matheus ouvindo (09/11/2026)
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/interactions'
AVA = 'en-US-AvaMultilingualNeural'
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
NUVEM = [('gemini', 'audio/wav', gemini), ('ava', 'audio/mpeg', ava)]
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
    chave = (texto, voz or voz_gemini(), tuple(n for n, _, _ in cadeia))
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
