"""Quem transcreve a escuta da palavra "Solis" — online primeiro (regra do
Matheus, 17/11/2026: o computador do cliente só quando não der).

Decisão dele ("só o pedido online", 17/11/2026), medida na gravação dele:

  - **Se tem "Solis"**: quem confere é o Whisper small, AQUI no computador (453 MB
    da placa, 0,14 s por trecho). Fala sem "Solis" — a conversa de quem estiver
    perto do microfone — nunca sai do computador.
  - **O pedido** (o que vem com e depois de "Solis") vai pro Whisper large-v3 da
    Groq: na gravação dele, esse caminho acordou 10 e entendeu 10 de 12, sem
    alarme falso, em 0,71 s (mediana). Só o pedido vai: ~US$ 0,50 por mês com 30
    chamadas por dia, contra ~US$ 11 se toda fala fosse pra nuvem.
  - **O que é privado** ("isso é privado...", memoria.eh_privado no texto do small)
    não vai: quem transcreve é o turbo daqui.
  - **Sem a Groq** (sem chave, sem internet, limite, erro): o turbo daqui, como
    antes (voz.py) — o modo offline. Uma falha deixa a Groq de lado por FORA_S.

Pra Groq vai só o vocabulário fixo (voz.VOCABULARIO_BASE): o local usa também
nomes das memórias, que não saem do computador. Números em docs/ESCOPO.md."""
import asyncio
import logging
import os
import re
import threading
import time

from . import ativacao, conexoes, memoria, voz

log = logging.getLogger('solis.transcricao')

MODELO_NUVEM = os.environ.get('SOLIS_ESCUTA_NUVEM', 'whisper-large-v3')
MODELO_PALAVRA = os.environ.get('SOLIS_ESCUTA_PALAVRA', 'faster-whisper-small')
URL_NUVEM = 'https://api.groq.com/openai/v1/audio/transcriptions'
TEMPO_NUVEM = 8.0
FORA_S = 60.0
_fora_ate = 0.0


# — A nuvem (Groq) ———————————————————————————————————————————————————————————————

class NuvemFalhou(Exception):
    pass


def online() -> bool:
    """A Groq pode transcrever agora: tem a chave e não falhou há pouco."""
    from . import apis
    return time.monotonic() >= _fora_ate and bool(apis._chave_de('groq'))


def _deixar_de_lado(segundos: float, motivo: str) -> None:
    global _fora_ate
    _fora_ate = time.monotonic() + segundos
    log.info('transcrição na nuvem fora por %.0f s: %s', segundos, motivo)


async def nuvem(audio: bytes) -> str:
    """O texto do áudio (WAV) pelo Whisper da Groq. NuvemFalhou se não deu."""
    from . import apis
    chave = apis._chave_de('groq')
    if not chave:
        raise NuvemFalhou('sem a chave da Groq')
    try:
        r = await conexoes.cliente('groq').post(
            URL_NUVEM,
            headers={'Authorization': f'Bearer {chave}'},
            files={'file': ('trecho.wav', audio, 'audio/wav')},
            data={'model': MODELO_NUVEM, 'language': voz.LINGUA or 'pt', 'response_format': 'json',
                  'temperature': '0', 'prompt': ', '.join(voz.VOCABULARIO_BASE) + '.'},
            timeout=TEMPO_NUVEM,
        )
    except Exception as e:  # noqa: BLE001 — rede, timeout: o local responde
        _deixar_de_lado(FORA_S, type(e).__name__)
        raise NuvemFalhou(type(e).__name__) from e
    if r.status_code == 429:
        try:
            espera = float(r.headers.get('retry-after', FORA_S))
        except ValueError:
            espera = FORA_S
        _deixar_de_lado(max(1.0, espera), 'limite (429)')
        raise NuvemFalhou('limite')
    if r.status_code >= 400:
        _deixar_de_lado(FORA_S, f'respondeu {r.status_code}')
        raise NuvemFalhou(f'respondeu {r.status_code}')
    try:
        return (r.json().get('text') or '').strip()
    except ValueError as e:
        raise NuvemFalhou('resposta sem JSON') from e


# — O Whisper pequeno, só pra palavra ————————————————————————————————————————————
# Separado do turbo (voz.py), que segue sendo o do apertar-pra-falar e o do modo
# offline: os dois podem estar carregados ao mesmo tempo.

_pequeno = None
_trava = threading.Lock()
_ultimo_uso = 0.0
_segurando = 0


def pequeno_disponivel() -> bool:
    return (voz.PASTA / MODELO_PALAVRA / 'model.bin').exists()


def _carregar_pequeno():
    global _pequeno
    if _pequeno is None:
        from faster_whisper import WhisperModel
        onde = voz._onde()
        if onde == 'cuda' and voz.CUBLAS_DO_OLLAMA.exists() and str(voz.CUBLAS_DO_OLLAMA) not in os.environ['PATH']:
            os.environ['PATH'] = str(voz.CUBLAS_DO_OLLAMA) + os.pathsep + os.environ['PATH']
        t0 = time.perf_counter()
        try:
            _pequeno = WhisperModel(str(voz.PASTA / MODELO_PALAVRA), device=onde, compute_type=voz.TIPOS[onde])
        except Exception as e:  # noqa: BLE001
            if onde != 'cuda':
                raise
            log.warning('whisper da palavra sem GPU (%s); indo pra CPU', e)
            _pequeno = WhisperModel(str(voz.PASTA / MODELO_PALAVRA), device='cpu', compute_type=voz.TIPOS['cpu'])
        log.info('whisper da palavra (%s) carregado em %.1f s', MODELO_PALAVRA, time.perf_counter() - t0)
    return _pequeno


# Uma passada só, e no máximo isto de texto por segundo de áudio. Era o padrão
# do faster-whisper: com o texto "ruim" (ruído, a TV, fala longe), ele refaz a
# transcrição com outras temperaturas, até 6 vezes, e alucina texto comprido.
# Medido em 18/11/2026: no servidor, 1,9 a 4,7 s por trecho de ~2 s (na placa,
# sem fila nem trava); em 42 trechos da gravação do teste da escuta, o pior
# caiu de 3,85 s para 0,16 s, e o "Solis" foi achado nas mesmas chamadas. O
# limite cresce com o áudio (12 por segundo, mais do que alguém fala; nunca
# menos de 32): o texto inteiro ainda confere o privado, só a alucinação some.
TOKENS_POR_S = 12
TOKENS_MIN = 32


def _limite_de_tokens(som) -> int:
    return max(TOKENS_MIN, round(len(som) / 16000 * TOKENS_POR_S))


def _palavra_agora(audio: bytes, vocab: str, entrou: float | None = None) -> str:
    """`entrou`: quando o pedido foi feito (antes da fila das threads), pro log
    dizer onde o tempo foi: no teste ao vivo de 17/11/2026 o pequeno levou de
    1,8 a 6,7 s no servidor, e 0,18 s sozinho num processo à parte."""
    global _ultimo_uso
    t0 = time.monotonic()
    som = voz.decodificar(audio)
    if not len(som):
        return ''
    t1 = time.monotonic()
    with _trava:
        t2 = time.monotonic()
        modelo = _carregar_pequeno()
        segmentos, _ = modelo.transcribe(som, language=voz.LINGUA or None, beam_size=5, vad_filter=False,
                                         initial_prompt=vocab or None, temperature=0.0,
                                         condition_on_previous_text=False, without_timestamps=True,
                                         max_new_tokens=_limite_de_tokens(som))
        texto = ' '.join(s.text.strip() for s in segmentos).strip()
        _ultimo_uso = time.monotonic()
    t3 = time.monotonic()
    if t3 - (entrou or t0) > LENTO_S:
        log.info('pequeno: fila %.2f s · decodificar %.2f s · trava %.2f s · transcrever %.2f s (%s)',
                 t0 - (entrou or t0), t1 - t0, t2 - t1, t3 - t2, getattr(modelo.model, 'device', '?'))
    return '' if voz.eco_do_vocabulario(texto, vocab) else texto


async def palavra(audio: bytes) -> str:
    """O texto pelo Whisper pequeno daqui — pra saber se tem "Solis" e se é privado."""
    t = time.monotonic()
    vocab = voz.vocabulario(voz._modelos_do_ollama())
    if time.monotonic() - t > 0.3:
        log.info('pequeno: o vocabulário levou %.2f s', time.monotonic() - t)
    return await asyncio.to_thread(_palavra_agora, audio, vocab, time.monotonic())


def aquecer_pequeno() -> None:
    """Bloqueia. Carrega o pequeno e transcreve 1 s de silêncio (a primeira
    transcrição na GPU carrega a cuBLAS: 2,1 s contra 0,14 s, medido)."""
    global _ultimo_uso
    import numpy as np
    with _trava:
        modelo = _carregar_pequeno()
        try:
            list(modelo.transcribe(np.zeros(16000, dtype=np.float32), language='pt', vad_filter=False)[0])
        except RuntimeError:
            pass
        _ultimo_uso = time.monotonic()


def segurar() -> None:
    global _segurando
    with _trava:
        _segurando += 1


def soltar() -> None:
    global _segurando, _ultimo_uso
    with _trava:
        _segurando = max(0, _segurando - 1)
        _ultimo_uso = time.monotonic()


def descarregar_se_ocioso() -> bool:
    global _pequeno
    with _trava:
        if _pequeno is not None and not _segurando and time.monotonic() - _ultimo_uso > voz.OCIOSO:
            _pequeno = None
            log.info('whisper da palavra descarregado (%d min sem uso)', voz.OCIOSO // 60)
            return True
    return False


# — Quem transcreve cada trecho da escuta ——————————————————————————————————————————

async def _local(audio: bytes) -> str:
    try:
        return (await voz.transcrever(audio, vad=False))['texto']
    except voz.AudioRuim:
        return ''


# Acima disto, o log conta quanto cada etapa de um trecho levou (só os tempos,
# nunca o que foi dito): no teste ao vivo de 17/11/2026 a decisão levou de 2 a
# 9 s, contra 0,76 s de mediana na medida, sem dizer onde.
LENTO_S = 1.5


async def escuta(tipo: str, audio: bytes) -> str:
    """O texto de um trecho da escuta (ativacao.Escuta): `tipo` 'previa' ou
    'frase' (tem "Solis"?), 'rascunho' ou 'comando' (o pedido)."""
    tempos: list[str] = []
    t0 = time.monotonic()

    def marca(etapa: str, desde: float) -> float:
        agora = time.monotonic()
        tempos.append(f'{etapa} {agora - desde:.2f} s')
        return agora

    try:
        if not online() or not pequeno_disponivel():
            texto = await _local(audio)
            marca('local (offline)', t0)
            return texto
        texto = await palavra(audio)
        t = marca('pequeno', t0)
        chamada = tipo in ('previa', 'frase')
        achou = ativacao.palavra_no_inicio(texto)[0]
        if chamada and not achou and not _cita_solis(texto):
            return texto  # nem cita "Solis": nada sai do computador
        if memoria.eh_privado(texto):
            texto = await _local(audio)  # o privado não vai pra nuvem
            marca('local (privado)', t)
            return texto
        try:
            texto_nuvem = await nuvem(audio)
            marca('nuvem', t)
        except NuvemFalhou as e:
            t = marca(f'nuvem falhou ({e})', t)
            texto = await _local(audio)
            marca('local', t)
            return texto
        if chamada and not ativacao.palavra_no_inicio(texto_nuvem)[0]:
            # A nuvem não ouviu a chamada: vale o que o pequeno ouviu (se ele achou, a palavra é dele).
            return texto
        return texto_nuvem
    finally:
        total = time.monotonic() - t0
        if total > LENTO_S:
            log.info('escuta %s: %.1f s (%s; %.1f s de áudio)', tipo, total, ' · '.join(tempos),
                     max(0, len(audio) - 44) / 32000)


# O pequeno às vezes ouve a chamada torta: "Ei Solis, quanto é..." virou "É isso aí,
# Solis" na gravação do Matheus (17/11/2026) — três palavras antes do nome, e a
# regra (ativacao.palavra_no_inicio) aceita duas; afrouxar acordaria com "me passa
# o Solis aí". Então quando o pequeno ouve "Solis" no começo da fala, mas fora do
# lugar de chamada, quem decide é o Whisper da nuvem. Só vão as falas que citam o
# nome do Solis.
_SOLIS_NO_COMECO = re.compile(r'^(?:\W*\w+){0,5}?\W*s?ol+[eiy]s+e?\b')


def _cita_solis(texto: str) -> bool:
    return bool(_SOLIS_NO_COMECO.search(ativacao._sem_acento(texto)))
