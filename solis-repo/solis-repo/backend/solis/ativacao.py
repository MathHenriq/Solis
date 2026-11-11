"""A palavra de ativação: "Solis", e o Solis começa a ouvir — sem clicar.

O navegador mantém o microfone aberto e manda o áudio (PCM 16 bits, 16 kHz,
mono) por um WebSocket, em quadros de 512 amostras. Dois motores acham a
palavra:

- **Whisper** (o de hoje): a energia do som separa os trechos de fala; os
  primeiros PREVIA segundos de cada trecho vão pro Whisper (voz.py), e se o
  texto começa com "Solis", o trecho vira comando. Funciona sem nada do
  Matheus, mas a GPU trabalha a cada trecho de fala que o microfone pega (TV,
  conversa no cômodo) — é a ponte até um modelo só da palavra.
- **Porcupine** (Picovoice), se houver AccessKey e o modelo .ppn: ouve a palavra
  na CPU, quadro a quadro. Ficou sem uso: a conta agora é só pra empresas, com
  teste de 7 dias. O openWakeWord (aberto) é o próximo candidato, com um modelo
  "Solis" treinado fora daqui (o PyTorch é bloqueado pelo Controle de Aplicativo).

Depois da palavra, o que vem é guardado até a pessoa parar de falar (energia
baixa por FIM_SILENCIO), vai pro Whisper, e o texto volta pro navegador, que
manda a mensagem. Nada vai pro disco: o áudio só existe em memória.
"""
import array
import logging
import math
import os
import re
import unicodedata
from collections import deque
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
# Sem falar nada depois da palavra: desiste. Era 5 s, e no teste de 11/11/2026
# a primeira chamada ouviu "Solis" e desistiu antes do pedido chegar.
INICIO_MAX = 8.0

# Fala é o que passa ACIMA_DO_PISO dB do ruído de fundo (e de FALA_MIN_DB).
# Medido com o microfone do Matheus no app (11/11/2026), sem o processamento de
# chamada: ruído em -46 dBFS (p10) e a fala só até -34 (p99). Com 12 dB acima
# do piso e mínimo de -45, quase nada passava como fala — e nenhum "Solis" foi
# ouvido em 3 minutos. Com 7 dB, a fala dele passa e o ruído não.
ACIMA_DO_PISO = 7.0
ACIMA_DO_PISO_COMANDO = 5.0
FALA_MIN_DB = -55.0
# O trecho vai pro Whisper com o pico levado a -3 dBFS (até 30x): o microfone
# dele chega baixo, e o Whisper erra mais com áudio baixo.
PICO_ALVO = 0.7
GANHO_MAX = 30.0

# Motor Whisper. PROVISÓRIO até medir com a voz do Matheus.
PREVIA = 2.0  # segundos do começo do trecho que vão pro Whisper procurar a palavra
# Segundos guardados antes do som subir: o "S" de Solis é baixo e ficava de
# fora do trecho (11/11/2026: 4 de 6 chamadas reais voltaram vazias).
ANTES = 0.6


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
    return {'chave': bool(chave()), 'palavra': PALAVRA.exists(), 'idioma': IDIOMA.exists(), 'motor': motor()}


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


# — A palavra no texto ——————————————————————————————————————————————————————————

def _sem_acento(texto: str) -> str:
    """Minúsculas e sem acento, letra por letra — o mesmo tamanho do original,
    pra o que for achado aqui ser cortado lá."""
    return ''.join((unicodedata.normalize('NFD', c)[0] if c.isalpha() else c).lower() for c in texto)


# "Solis", como o Whisper costuma escrever (Sólis, Solís, Sollis, Solys), no
# começo da frase ou depois de um chamado ("ei, Solis").
# O "S" pode sumir no começo da fala ("Olis").
_PALAVRA = re.compile(r"^[\s\W]*(?:(?:ei|hey|oi|ola|ok|e ai)[\s,!.]+)?s?ol+[eiy]s+e?\b[\s,!.:;?-]*")


def palavra_no_inicio(texto: str) -> tuple[bool, str]:
    """(achou, o resto): "Solis, me lembra de pagar a luz." → (True, "Me lembra
    de pagar a luz.")."""
    m = _PALAVRA.match(_sem_acento(texto))
    if not m:
        return False, texto.strip()
    resto = texto[m.end():].strip()
    return True, resto[:1].upper() + resto[1:]


# — A escuta ——————————————————————————————————————————————————————————————————————

def _energia(quadro: array.array) -> float:
    """dBFS do quadro (0 é o máximo; silêncio de sala fica abaixo de -50)."""
    if not quadro:
        return -100.0
    soma = sum(a * a for a in quadro) / len(quadro)
    return 10 * math.log10(soma / (32768.0 ** 2) + 1e-12)


def motor() -> str | None:
    """Quem vai achar a palavra: 'porcupine' (se configurado), 'whisper' (se
    o modelo está na pasta) ou None."""
    if chave() and PALAVRA.exists():
        return 'porcupine'
    from . import voz
    return 'whisper' if voz.disponivel() else None


class Escuta:
    """Uma escuta (uma conexão): alimentada com áudio, devolve eventos.

    Com o Porcupine: 'ativou', depois ('comando', wav) com o que veio depois
    (ou None se a pessoa não falou).
    Com o Whisper (motor None): ('previa', wav) com o começo de um trecho de
    fala ainda em curso, ou ('frase', wav) com um trecho curto que já acabou.
    Quem recebe transcreve e responde com confirmar() — achou a palavra — ou
    descartar(). Confirmado, o trecho segue como comando até a pessoa parar.

    alimentar() é um gerador: entre um evento e o próximo quadro, quem chama
    decide (confirmar/descartar), e o quadro seguinte já vê a decisão. Separada
    do WebSocket pra ser testada com áudio de arquivo."""

    def __init__(self, motor_=None, whisper=False):
        if motor_ is None and not whisper:
            qual = motor()
            if qual is None:
                raise SemConfiguracao('falta o modelo do Whisper (ou a chave e o modelo do Porcupine)')
            if qual == 'porcupine':
                baixar_idioma()
                motor_ = _criar(chave(), PALAVRA)
        self.motor = motor_
        self.n = motor_.frame_length if motor_ else 512
        self.sobra = array.array('h')
        self.comando: array.array | None = None
        self.fala = 0.0  # segundos de voz no comando
        self.silencio = 0.0  # segundos de silêncio seguidos no fim
        self.piso = -60.0  # ruído de fundo, aprendido fora do comando
        self.ativacoes = 0
        # Whisper: o trecho de fala em curso, ainda sem saber se tem a palavra.
        self.antes: deque = deque(maxlen=max(1, round(ANTES * TAXA / self.n)))
        self.trecho: array.array | None = None
        self.t_fala = self.t_silencio = 0.0
        self.previa_feita = False
        self.trechos = 0  # quantos foram pro Whisper (pra medir o custo)

    def fechar(self):
        try:
            if self.motor:
                self.motor.delete()
        except Exception:
            pass

    def alimentar(self, pcm: bytes):
        self.sobra.frombytes(pcm[: len(pcm) - len(pcm) % 2])
        while len(self.sobra) >= self.n:
            quadro = self.sobra[: self.n]
            del self.sobra[: self.n]
            evento = self._quadro(quadro)
            if evento:
                yield evento

    def confirmar(self):
        """A palavra estava no trecho: ele vira o começo do comando (ou, se o
        trecho já acabou só com "Solis", o comando começa vazio)."""
        self.ativacoes += 1
        if self.trecho is not None:
            self.comando, self.fala, self.silencio = self.trecho, self.t_fala, self.t_silencio
            self.trecho = None
        else:
            self.comando, self.fala, self.silencio = array.array('h'), 0.0, 0.0

    def descartar(self):
        """Sem a palavra: o resto do trecho é ignorado até ele acabar."""
        self.previa_feita = True

    def _e_fala(self, db: float, margem: float = ACIMA_DO_PISO) -> bool:
        return db > max(self.piso + margem, FALA_MIN_DB)

    def _quadro(self, quadro: array.array):
        dur = self.n / TAXA
        db = _energia(quadro)
        if self.comando is None:
            # O piso de ruído acompanha o ambiente devagar, só fora do comando.
            self.piso = 0.98 * self.piso + 0.02 * db
            if self.motor is not None:
                if self.motor.process(quadro) >= 0:
                    self.ativacoes += 1
                    self.comando, self.fala, self.silencio = array.array('h'), 0.0, 0.0
                    return ('ativou', None)
                return None
            return self._trecho(quadro, db, dur)
        self.comando.extend(quadro)
        # Depois do "Solis", fala mais baixa ainda conta: quem chamou vai falar.
        if self._e_fala(db, ACIMA_DO_PISO_COMANDO):
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

    def _trecho(self, quadro: array.array, db: float, dur: float):
        """Whisper: junta um trecho de fala e manda o começo dele pra conferir."""
        fala = self._e_fala(db)
        if self.trecho is None:
            self.antes.append(quadro)
            if not fala:
                return None
            self.trecho = array.array('h')
            for q in self.antes:
                self.trecho.extend(q)
            self.antes.clear()
            self.t_fala, self.t_silencio, self.previa_feita = dur, 0.0, False
            return None
        self.trecho.extend(quadro)
        if fala:
            self.t_fala += dur
            self.t_silencio = 0.0
        else:
            self.t_silencio += dur
        total = len(self.trecho) / TAXA
        if self.t_silencio >= FIM_SILENCIO or total >= COMANDO_MAX:
            trecho, self.trecho = self.trecho, None
            if self.previa_feita or self.t_fala < FALA_MINIMA / 2:
                return None  # já conferido (sem a palavra), ou só um estalo
            self.trechos += 1
            return ('frase', _wav(trecho))
        # A prévia só sai com a pessoa ainda falando: trecho que está acabando
        # vai inteiro como 'frase' (senão "Solis" + pausa viraria prévia).
        if not self.previa_feita and fala and total >= PREVIA:
            self.previa_feita = True
            self.trechos += 1
            return ('previa', _wav(self.trecho))
        return None


def _normalizar(amostras: array.array) -> array.array:
    """O pico em PICO_ALVO, com no máximo GANHO_MAX — áudio baixo vira áudio
    num volume que o Whisper ouve bem; o que já está alto não muda."""
    pico = max((abs(a) for a in amostras), default=0)
    if not pico:
        return amostras
    ganho = min(GANHO_MAX, PICO_ALVO * 32767 / pico)
    if ganho <= 1.0:
        return amostras
    return array.array('h', (max(-32768, min(32767, int(a * ganho))) for a in amostras))


def _wav(amostras: array.array) -> bytes:
    import io
    import wave
    amostras = _normalizar(amostras)
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(amostras.tobytes())
    return saida.getvalue()
