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
# O large-v3-turbo desde 11/11/2026: em comandos curtos com voz baixa e ruído
# (24, medidos), os três erram 3, mas o small erra longe ("E oração" no lugar
# de "que horas são") e o turbo erra perto ("E horas são", que o rapidas.py
# entende). Custa 0,15 s a mais por comando (0,33 contra 0,18 s, mediana).
MODELO = os.environ.get('SOLIS_WHISPER', 'faster-whisper-large-v3-turbo-ct2')
# Se o escolhido não está na pasta, o melhor que estiver, nesta ordem — e o log
# diz. Em 16/11/2026 o turbo existia só numa pasta isolada das ferramentas do
# Claude Code (baixado por um processo delas), e o Solis de verdade, sem ele,
# ficou sem transcrever nada: a escuta nem começava.
RESERVAS = ('faster-whisper-large-v3-turbo-ct2', 'faster-whisper-medium', 'faster-whisper-small')


def modelo_em_uso() -> str | None:
    """O modelo que vai rodar: o escolhido, ou a melhor reserva que está na pasta."""
    for m in dict.fromkeys((MODELO, *RESERVAS)):
        if (PASTA / m / 'model.bin').exists():
            return m
    return None
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
_carregado = None  # qual modelo está carregado (modelo_em_uso pode mudar)
_sem_gpu = False  # a GPU falhou uma vez: daqui pra frente, CPU
_ultimo_uso = 0.0
_trava = threading.Lock()
# Quantas escutas da palavra estão abertas: com alguma, o modelo não sai da
# memória. Medido em 16/11/2026 (RTX 4060 8 GB, turbo): carregar 5,5 s e a
# primeira transcrição 1,2 s, contra 0,3 s com ele carregado — a primeira
# chamada depois de 10 min quieto esperava ~7 s pelo bipe e se perdia. O preço:
# 1,1 GB de VRAM enquanto a escuta estiver ligada.
_segurando = 0

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


def eco_do_vocabulario(texto: str, vocab: str | None) -> bool:
    """O Whisper, diante de som que não é fala (um zumbido que varia, música),
    às vezes devolve o próprio vocabulário: "Matheus, Solis, Ollama, Claude".
    Três palavras ou mais, quase todas do vocabulário, é eco — não fala. Um
    "Solis." sozinho passa (é a palavra de ativação)."""
    if not vocab:
        return False
    nomes = {n.strip(' .').lower() for n in vocab.split(',')}
    palavras = [p for p in (x.strip(' .,!?;:').lower() for x in texto.split()) if p]
    return len(palavras) >= 3 and sum(p in nomes for p in palavras) / len(palavras) >= 0.6


def disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError as e:
        log.warning('faster-whisper não importa neste processo: %s', e)
        return False
    return modelo_em_uso() is not None


def _onde() -> str:
    if DISPOSITIVO != 'auto':
        return DISPOSITIVO
    return 'cpu' if _sem_gpu else 'cuda'


def _carregar():
    global _modelo, _dispositivo, _sem_gpu, _carregado
    # Um modelo melhor chegou na pasta (o turbo baixado depois): troca sem reiniciar.
    if _modelo is not None and modelo_em_uso() != _carregado:
        log.info('whisper: %s chegou na pasta, trocando o %s', modelo_em_uso(), _carregado)
        _modelo = None
    if _modelo is None:
        if not disponivel():
            raise SemModelo(f'falta o modelo do Whisper ({MODELO} ou uma reserva) em {PASTA}')
        qual = modelo_em_uso()
        if qual != MODELO:
            log.warning('o whisper %s não está em %s: usando a reserva %s', MODELO, PASTA, qual)
        from faster_whisper import WhisperModel
        onde = _onde()
        if onde == 'cuda' and CUBLAS_DO_OLLAMA.exists() and str(CUBLAS_DO_OLLAMA) not in os.environ['PATH']:
            os.environ['PATH'] = str(CUBLAS_DO_OLLAMA) + os.pathsep + os.environ['PATH']
        t0 = time.perf_counter()
        try:
            _modelo = WhisperModel(str(PASTA / qual), device=onde, compute_type=TIPOS[onde])
        except Exception as e:
            if onde != 'cuda' or DISPOSITIVO != 'auto':
                raise
            log.warning('whisper sem GPU (%s); indo pra CPU', e)
            _sem_gpu, onde = True, 'cpu'
            _modelo = WhisperModel(str(PASTA / qual), device=onde, compute_type=TIPOS[onde])
        _dispositivo, _carregado = onde, qual
        log.info('whisper %s carregado (%s/%s) em %.1f s', qual, onde, TIPOS[onde], time.perf_counter() - t0)
    return _modelo


def _transcrever(som, vocab: str | None, vad: bool = True):
    segmentos, info = _modelo.transcribe(
        som, language=LINGUA or None, beam_size=5, vad_filter=vad, initial_prompt=vocab or None,
    )
    # Os segmentos são preguiçosos: é aqui, lendo, que a GPU trabalha (e falha).
    return ' '.join(s.text.strip() for s in segmentos).strip(), info


def transcrever_agora(audio: bytes, vocab: str | None = None, vad: bool = True) -> dict:
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
            texto, info = _transcrever(som, vocab, vad)
        except RuntimeError as e:
            # A cuBLAS só é carregada na primeira transcrição: sem ela (Ollama
            # desinstalado, versão nova), a GPU falha só aqui. Vai pra CPU.
            if _dispositivo != 'cuda' or DISPOSITIVO != 'auto':
                raise
            global _modelo, _sem_gpu
            log.warning('whisper falhou na GPU (%s); indo pra CPU', e)
            _modelo, _sem_gpu = None, True
            _carregar()
            texto, info = _transcrever(som, vocab, vad)
        _ultimo_uso = time.monotonic()
        if eco_do_vocabulario(texto, vocab):
            log.info('whisper devolveu o vocabulário (som que não é fala); ignorado')
            texto = ''
        return {'texto': texto, 'segundos': round(info.duration, 1), 'duracao': round(time.perf_counter() - t0, 2),
                'modelo': modelo_em_uso(), 'onde': _dispositivo}


async def transcrever(audio: bytes, vad: bool = True) -> dict:
    """`vad=False` na escuta da palavra: o trecho já foi separado pela energia, e
    o filtro de voz do Whisper descartava o "Solis" curto e baixo (11/11/2026: 4
    de 6 chamadas reais voltaram vazias)."""
    return await asyncio.to_thread(transcrever_agora, audio, vocabulario(_modelos_do_ollama()), vad)


# Os modelos do Ollama, pro vocabulário: guardados, e atualizados em segundo
# plano. Perguntar a cada transcrição custava 2 s com o Ollama desligado (o
# Windows insiste na porta fechada de 127.0.0.1) — medido em 16/11/2026: 2,35 s
# por trecho na escuta, dos quais 0,3 s eram o Whisper.
OLLAMA_CACHE_S = 300
_ollama: dict = {'quando': -1e9, 'nomes': [], 'buscando': False}


def _modelos_do_ollama() -> list[str]:
    if time.monotonic() - _ollama['quando'] > OLLAMA_CACHE_S and not _ollama['buscando']:
        _ollama['buscando'] = True
        try:
            asyncio.get_running_loop().create_task(_buscar_ollama())
        except RuntimeError:
            _ollama['buscando'] = False
    return _ollama['nomes']


async def _buscar_ollama() -> None:
    from . import ollama
    try:
        _ollama['nomes'] = sorted(await ollama.instalados())
    except ollama.OllamaIndisponivel:
        pass
    finally:
        _ollama.update(quando=time.monotonic(), buscando=False)


def segurar() -> None:
    """Uma escuta abriu: o modelo fica na memória até ela fechar."""
    global _segurando
    with _trava:
        _segurando += 1


def soltar() -> None:
    global _segurando, _ultimo_uso
    with _trava:
        _segurando = max(0, _segurando - 1)
        # Os 10 min de folga contam a partir de agora, não da última fala.
        _ultimo_uso = time.monotonic()


def aquecer() -> None:
    """Bloqueia (roda numa thread). Carrega o modelo e faz uma transcrição de
    silêncio: a primeira transcrição na GPU carrega a cuBLAS (1,2 s em vez de
    0,3 s) — melhor aqui do que no primeiro "Solis"."""
    global _ultimo_uso
    import numpy as np
    with _trava:
        if _modelo is not None and _carregado == modelo_em_uso():
            return
        _carregar()
        try:
            _transcrever(np.zeros(16000, dtype=np.float32), None, vad=False)  # 1 s a 16 kHz
        except RuntimeError:
            pass  # a GPU falhando aparece (e cai pra CPU) na transcrição de verdade
        _ultimo_uso = time.monotonic()


def descarregar_se_ocioso() -> bool:
    global _modelo
    with _trava:
        if _modelo is not None and not _segurando and time.monotonic() - _ultimo_uso > OCIOSO:
            _modelo = None
            log.info('whisper descarregado (%d min sem uso)', OCIOSO // 60)
            return True
    return False


async def vigiar() -> None:
    while True:
        await asyncio.sleep(60)
        descarregar_se_ocioso()
