"""Voz: o áudio do microfone vira texto, no próprio computador (Whisper, pelo
faster-whisper). Apertar pra falar é a primeira camada (docs/ESCOPO.md → Voz):
o front grava, manda o áudio, e o texto volta pra caixa da conversa — a pessoa
confere antes de enviar.

Escolhido medindo (09/11/2026): 8 frases com texto conhecido (tarefas, datas,
"Syngenta", "FastAPI", "qwen"), na voz pt-BR do Windows, limpas e com ruído
(SNR 15 dB). Erro por palavra, limpo / com ruído:

    modelo          onde   sem vocabulário   com vocabulário   nomes   por frase
    small           CPU    9,5 / 9,7 %       —                 1/7     2,5 a 3,5 s
    medium          CPU    8,8 / 10,9 %      —                 2/7     8,6 s
    large-v3-turbo  CPU    7,4 / 7,1 %       —                 2/7     11 a 13 s
    small           GPU    8,2 / 9,7 %       2,1 / 4,4 %       5/7     0,5 s
    large-v3-turbo  GPU    7,4 / 7,1 %       2,7 / 4,7 %       5/7     0,5 s

Quase todo o erro era nome ("singenta", "FESTE-API", "QVN3", "LORMA"), e o
vocabulário (o initial_prompt do Whisper, com os nomes que o Solis já conhece)
derruba o erro quatro vezes. Com ele o small empata com o turbo ocupando 455 MB
de placa em vez de 1,2 GB — e a placa é disputada pelo qwen3:8b e pelo jogo.
Por isso: small, na GPU (int8_float16), e na CPU se a GPU não der.

A GPU usa a cuBLAS que o Ollama já traz (lib/ollama/cuda_v12), em vez de baixar
a da NVIDIA: o ctranslate2 acha a biblioteca pelo PATH do processo.

O modelo carrega na primeira fala (segundos) e fica na memória; depois de
OCIOSO sem uso, sai — e libera a placa.
"""
import asyncio
import io
import logging
import os
import re
import threading
import time
from collections import Counter
from pathlib import Path

from . import banco

log = logging.getLogger('solis.voz')

PASTA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Solis' / 'whisper'
MODELO = os.environ.get('SOLIS_WHISPER', 'faster-whisper-small')
# 'auto' tenta a GPU e cai pra CPU; 'cpu' e 'cuda' forçam.
DISPOSITIVO = os.environ.get('SOLIS_WHISPER_DISPOSITIVO', 'auto')
TIPOS = {'cuda': 'int8_float16', 'cpu': 'int8'}
CUBLAS_DO_OLLAMA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Programs' / 'Ollama' / 'lib' / 'ollama' / 'cuda_v12'
LINGUA = os.environ.get('SOLIS_WHISPER_LINGUA', 'pt')
OCIOSO = 10 * 60  # segundos sem fala até o modelo sair da memória
AUDIO_MAX = 25 * 1024 * 1024  # ~25 min de opus; apertar pra falar é frase, não palestra


def decodificar(dados: bytes):
    """O áudio (webm/opus do navegador, wav, mp3...) como o Whisper quer: mono,
    16 kHz, float32 entre -1 e 1. Pelo PyAV direto, e não pelo decode_audio do
    faster-whisper 1.2.1: ele passa ao av.open um parâmetro (metadata_errors)
    que o av 19 tirou, e nada transcrevia (visto em 09/11/2026)."""
    import av
    import numpy as np

    partes = []
    with av.open(io.BytesIO(dados)) as recipiente:
        conversor = av.AudioResampler(format='s16', layout='mono', rate=16000)
        for quadro in recipiente.decode(audio=0):
            partes += [q.to_ndarray() for q in conversor.resample(quadro)]
        partes += [q.to_ndarray() for q in conversor.resample(None)]
    if not partes:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(partes, axis=1).ravel().astype(np.float32) / 32768.0


class SemModelo(Exception):
    """O modelo do Whisper não está na pasta (ou o faster-whisper não instalou)."""


class AudioRuim(Exception):
    """O áudio não abriu, ou veio vazio."""


_modelo = None
_dispositivo = None  # onde o _modelo está carregado
_sem_gpu = False  # a GPU falhou uma vez: daqui pra frente, CPU
_ultimo_uso = 0.0
_trava = threading.Lock()

# — Vocabulário ——————————————————————————————————————————————————————————————————

# Sempre: quem fala e com quem, e os nomes que aparecem na conversa sobre ele.
VOCABULARIO_BASE = ['Matheus', 'Solis', 'Ollama', 'Claude', 'Codex', 'Gemini', 'Groq', 'Mistral', 'OpenRouter']
VOCABULARIO_MAX = 40
# Palavra que é nome: começa com maiúscula fora do começo da frase, ou mistura
# maiúscula e minúscula (FastAPI), ou letra e número (qwen3).
_MISTURADA = re.compile(r'^(?=.*[a-zà-ú])(?=.*[A-Z]).+[A-Z]|^[A-Za-z]+\d')


def _nomes(texto: str) -> list[str]:
    achados = []
    for frase in re.split(r'[.!?\n]+', texto):
        palavras = re.findall(r"[\wÀ-ú][\wÀ-ú.+-]*[\wÀ-ú]|[\wÀ-ú]", frase)
        for i, p in enumerate(palavras):
            if len(p) < 3 or p.isdigit():
                continue
            if (i > 0 and p[0].isupper()) or _MISTURADA.search(p):
                achados.append(p)
    return achados


def vocabulario(modelos_instalados: list[str] | None = None) -> str:
    """Os nomes que o Solis já conhece, pro Whisper escrever certo: os das
    memórias, dos títulos das conversas e dos arquivos do Conhecimento, e as
    famílias dos modelos instalados (qwen, llama...). O áudio e este texto não
    saem do computador, então o que é privado entra também."""
    contagem = Counter()
    for m in banco.memorias():
        contagem.update(_nomes(m['texto']))
    for c in banco.conversas(limite=50):
        contagem.update(_nomes(c.get('titulo') or ''))
    for d in banco.documentos():
        contagem.update(_nomes(re.sub(r'\.\w+$', '', d['nome'])))
    familias = {re.split(r'[\d.:]', n)[0] for n in modelos_instalados or [] if 'embed' not in n}
    termos = list(dict.fromkeys(
        VOCABULARIO_BASE + sorted(f for f in familias if f) + [n for n, _ in contagem.most_common(VOCABULARIO_MAX)]
    ))
    return ', '.join(termos[:VOCABULARIO_MAX]) + '.'


def disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError as e:
        log.warning('faster-whisper não importa neste processo: %s', e)
        return False
    return (PASTA / MODELO / 'model.bin').exists()


def _onde() -> str:
    if DISPOSITIVO != 'auto':
        return DISPOSITIVO
    return 'cpu' if _sem_gpu else 'cuda'


def _carregar():
    global _modelo, _dispositivo, _sem_gpu
    if _modelo is None:
        if not disponivel():
            raise SemModelo(f'falta o modelo {MODELO} em {PASTA}')
        from faster_whisper import WhisperModel
        onde = _onde()
        if onde == 'cuda' and CUBLAS_DO_OLLAMA.exists() and str(CUBLAS_DO_OLLAMA) not in os.environ['PATH']:
            os.environ['PATH'] = str(CUBLAS_DO_OLLAMA) + os.pathsep + os.environ['PATH']
        t0 = time.perf_counter()
        try:
            _modelo = WhisperModel(str(PASTA / MODELO), device=onde, compute_type=TIPOS[onde])
        except Exception as e:
            if onde != 'cuda' or DISPOSITIVO != 'auto':
                raise
            log.warning('whisper sem GPU (%s); indo pra CPU', e)
            _sem_gpu, onde = True, 'cpu'
            _modelo = WhisperModel(str(PASTA / MODELO), device=onde, compute_type=TIPOS[onde])
        _dispositivo = onde
        log.info('whisper %s carregado (%s/%s) em %.1f s', MODELO, onde, TIPOS[onde], time.perf_counter() - t0)
    return _modelo


def _transcrever(som, vocab: str | None):
    segmentos, info = _modelo.transcribe(
        som, language=LINGUA or None, beam_size=5, vad_filter=True, initial_prompt=vocab or None,
    )
    # Os segmentos são preguiçosos: é aqui, lendo, que a GPU trabalha (e falha).
    return ' '.join(s.text.strip() for s in segmentos).strip(), info


def transcrever_agora(audio: bytes, vocab: str | None = None) -> dict:
    """Bloqueia (roda numa thread). {texto, segundos (do áudio), duracao (da
    transcrição), modelo}. Uma transcrição por vez: o modelo não é reentrante, e
    duas falas ao mesmo tempo não acontecem num apertar pra falar."""
    global _ultimo_uso
    if not audio:
        raise AudioRuim('áudio vazio')
    if len(audio) > AUDIO_MAX:
        raise AudioRuim('áudio longo demais')
    with _trava:
        _carregar()
        t0 = time.perf_counter()
        try:
            som = decodificar(audio)
        except Exception as e:  # PyAV não abriu o formato, ou o arquivo veio cortado
            raise AudioRuim(f'não consegui abrir o áudio: {e}') from e
        if not len(som):
            raise AudioRuim('áudio vazio')
        try:
            texto, info = _transcrever(som, vocab)
        except RuntimeError as e:
            # A cuBLAS só é carregada na primeira transcrição: sem ela (Ollama
            # desinstalado, versão nova), a GPU falha só aqui. Vai pra CPU.
            if _dispositivo != 'cuda' or DISPOSITIVO != 'auto':
                raise
            global _modelo, _sem_gpu
            log.warning('whisper falhou na GPU (%s); indo pra CPU', e)
            _modelo, _sem_gpu = None, True
            _carregar()
            texto, info = _transcrever(som, vocab)
        _ultimo_uso = time.monotonic()
        return {'texto': texto, 'segundos': round(info.duration, 1), 'duracao': round(time.perf_counter() - t0, 2),
                'modelo': MODELO, 'onde': _dispositivo}


async def transcrever(audio: bytes) -> dict:
    from . import ollama
    try:
        instalados = sorted(await ollama.instalados())
    except ollama.OllamaIndisponivel:
        instalados = []
    return await asyncio.to_thread(transcrever_agora, audio, vocabulario(instalados))


def descarregar_se_ocioso() -> bool:
    global _modelo
    with _trava:
        if _modelo is not None and time.monotonic() - _ultimo_uso > OCIOSO:
            _modelo = None
            log.info('whisper descarregado (%d min sem uso)', OCIOSO // 60)
            return True
    return False


async def vigiar() -> None:
    while True:
        await asyncio.sleep(60)
        descarregar_se_ocioso()
