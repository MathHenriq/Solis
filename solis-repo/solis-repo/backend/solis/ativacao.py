"""A palavra de ativação: "Solis", e o Solis começa a ouvir — sem clicar.

Camada 1 da voz (docs/ESCOPO.md → "Voz e a GPU"): só reconhece a palavra, não
entende mais nada, e roda na CPU com custo mínimo. O motor é o Porcupine
(Picovoice), escolhido pelo Matheus: a palavra "Solis" em português é gerada
no console deles, sem treino nosso; pede uma AccessKey (conta pessoal grátis).
O openWakeWord, aberto, não tem "Solis" pronto e treinar pede o PyTorch, que o
Controle Inteligente de Aplicativos bloqueia.

O caminho: o navegador mantém o microfone aberto e manda o áudio (PCM 16 bits,
16 kHz, mono) por um WebSocket; aqui ele passa pelo Porcupine em quadros de 512
amostras. Ao ouvir a palavra, o que vem depois é guardado até a pessoa parar de
falar (energia baixa por FIM_SILENCIO), vai pro Whisper (voz.py), e o texto
volta pro navegador, que manda a mensagem. Nada vai pro disco: o áudio só
existe em memória, e antes da palavra nem é guardado.

A chave fica selada no cofre (como as dos cérebros). O modelo da palavra
(.ppn) e o de português ficam em %LOCALAPPDATA%\\Solis\\voz\\porcupine.
"""
import array
import logging
import math
import os
from pathlib import Path

import httpx

from . import banco, cofre

log = logging.getLogger('solis.ativacao')

PASTA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Solis' / 'voz' / 'porcupine'
PALAVRA = PASTA / 'solis.ppn'
IDIOMA = PASTA / 'porcupine_params_pt.pv'
IDIOMA_URL = 'https://raw.githubusercontent.com/Picovoice/porcupine/v4.0/lib/common/porcupine_params_pt.pv'
CHAVE = 'chave:picovoice'
TAXA = 16000
SENSIBILIDADE = float(os.environ.get('SOLIS_ATIVACAO_SENSIBILIDADE', '0.5'))

# O fim do comando: depois de pelo menos FALA_MINIMA de voz, FIM_SILENCIO de
# energia baixa encerra; COMANDO_MAX corta de qualquer jeito. PROVISÓRIO: os
# limiares saem da medição com o modelo do Matheus.
FALA_MINIMA = 0.4
FIM_SILENCIO = 0.9
COMANDO_MAX = 15.0
INICIO_MAX = 5.0  # sem falar nada depois da palavra: desiste


class SemConfiguracao(Exception):
    """Falta a chave, o modelo da palavra ou o de português."""


class ChaveRecusada(Exception):
    pass


class ModeloRecusado(Exception):
    pass


# — Configuração ——————————————————————————————————————————————————————————————————

def chave() -> str | None:
    selada = banco.ajuste(CHAVE)
    return cofre.abrir(selada) if selada else None


def estado() -> dict:
    """O que falta pra escuta funcionar — a tela mostra isso."""
    return {'chave': bool(chave()), 'palavra': PALAVRA.exists(), 'idioma': IDIOMA.exists()}


def baixar_idioma(transporte: httpx.BaseTransport | None = None) -> None:
    """O modelo de português do Porcupine (o pacote só traz o de inglês)."""
    if IDIOMA.exists():
        return
    with httpx.Client(timeout=60, follow_redirects=True, transport=transporte) as c:
        r = c.get(IDIOMA_URL)
    if r.status_code != 200 or len(r.content) < 10_000:
        raise SemConfiguracao(f'não consegui baixar o modelo de português ({r.status_code})')
    PASTA.mkdir(parents=True, exist_ok=True)
    IDIOMA.write_bytes(r.content)


def _criar(access_key: str, palavra: Path):
    import pvporcupine
    return pvporcupine.create(
        access_key=access_key, keyword_paths=[str(palavra)], model_path=str(IDIOMA), sensitivities=[SENSIBILIDADE],
    )


def conferir(access_key: str, palavra: Path) -> None:
    """Liga o Porcupine uma vez com a chave e o modelo, e desliga — é como
    sabe se os dois valem antes de guardar. ChaveRecusada / ModeloRecusado."""
    import pvporcupine
    try:
        baixar_idioma()
        _criar(access_key, palavra).delete()
    except (pvporcupine.PorcupineActivationError, pvporcupine.PorcupineActivationLimitError,
            pvporcupine.PorcupineActivationRefusedError, pvporcupine.PorcupineActivationThrottledError) as e:
        raise ChaveRecusada(str(e)) from e
    except (pvporcupine.PorcupineInvalidArgumentError, pvporcupine.PorcupineIOError) as e:
        raise ModeloRecusado(str(e)) from e


def guardar_chave(access_key: str) -> None:
    access_key = access_key.strip()
    if not access_key:
        raise ChaveRecusada('chave vazia')
    if PALAVRA.exists():
        conferir(access_key, PALAVRA)
    banco.guardar_ajuste(CHAVE, cofre.selar(access_key))


def guardar_palavra(dados: bytes) -> None:
    """O .ppn do console. Conferido com a chave, se já houver."""
    if not dados or len(dados) > 5 * 1024 * 1024:
        raise ModeloRecusado('o arquivo não parece um modelo .ppn')
    PASTA.mkdir(parents=True, exist_ok=True)
    provisorio = PASTA / 'solis.ppn.novo'
    provisorio.write_bytes(dados)
    try:
        if chave():
            conferir(chave(), provisorio)
    except Exception:
        provisorio.unlink(missing_ok=True)
        raise
    provisorio.replace(PALAVRA)


def apagar() -> None:
    banco.apagar_ajuste(CHAVE)
    PALAVRA.unlink(missing_ok=True)


# — A escuta ——————————————————————————————————————————————————————————————————————

def _energia(quadro: array.array) -> float:
    """dBFS do quadro (0 é o máximo; silêncio de sala fica abaixo de -50)."""
    if not quadro:
        return -100.0
    soma = sum(a * a for a in quadro) / len(quadro)
    return 10 * math.log10(soma / (32768.0 ** 2) + 1e-12)


class Escuta:
    """Uma escuta (uma conexão): alimentada com áudio, devolve eventos —
    'ativou' quando ouve a palavra, 'comando' com o áudio do que veio depois.
    Separada do WebSocket pra ser testada com áudio de arquivo."""

    def __init__(self, motor=None):
        if motor is None:
            k = chave()
            if not (k and PALAVRA.exists()):
                raise SemConfiguracao('falta a chave ou o modelo da palavra')
            baixar_idioma()
            motor = _criar(k, PALAVRA)
        self.motor = motor
        self.n = motor.frame_length
        self.sobra = array.array('h')
        self.comando: array.array | None = None
        self.fala = 0.0  # segundos de voz no comando
        self.silencio = 0.0  # segundos de silêncio seguidos no fim
        self.piso = -60.0  # ruído de fundo, aprendido antes da palavra
        self.ativacoes = 0

    def fechar(self):
        try:
            self.motor.delete()
        except Exception:
            pass

    def alimentar(self, pcm: bytes) -> list[tuple[str, bytes | None]]:
        self.sobra.frombytes(pcm[: len(pcm) - len(pcm) % 2])
        eventos = []
        while len(self.sobra) >= self.n:
            quadro = self.sobra[: self.n]
            del self.sobra[: self.n]
            evento = self._quadro(quadro)
            if evento:
                eventos.append(evento)
        return eventos

    def _quadro(self, quadro: array.array):
        dur = self.n / TAXA
        db = _energia(quadro)
        if self.comando is None:
            # O piso de ruído acompanha o ambiente devagar, só fora do comando.
            self.piso = 0.98 * self.piso + 0.02 * db
            if self.motor.process(quadro) >= 0:
                self.ativacoes += 1
                self.comando, self.fala, self.silencio = array.array('h'), 0.0, 0.0
                return ('ativou', None)
            return None
        self.comando.extend(quadro)
        if db > max(self.piso + 12, -45):
            self.fala += dur
            self.silencio = 0.0
        else:
            self.silencio += dur
        total = len(self.comando) / TAXA
        acabou = (self.fala >= FALA_MINIMA and self.silencio >= FIM_SILENCIO) or total >= COMANDO_MAX
        desistiu = self.fala < FALA_MINIMA and total >= INICIO_MAX
        if acabou or desistiu:
            audio, self.comando = self.comando, None
            return ('comando', None if desistiu else _wav(audio))
        return None


def _wav(amostras: array.array) -> bytes:
    import io
    import wave
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(amostras.tobytes())
    return saida.getvalue()
