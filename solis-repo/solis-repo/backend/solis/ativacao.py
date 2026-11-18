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
# O máximo que a demora da decisão estica os prazos acima.
ATRASO_MAX = 10.0

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

# Quem decide o que é fala: 'energia' (o som acima do ruído de fundo, o de
# antes) ou 'silero' (o Silero VAD, um modelo de 2 MB que já vem com o
# faster-whisper, quadro a quadro na CPU: 0,08 ms por quadro, medido em
# 16/11/2026). Com ele, o fim da fala pode esperar menos.
VAD = os.environ.get('SOLIS_ESCUTA_VAD', 'energia')
VAD_LIMIAR = 0.5        # é fala a partir desta probabilidade...
VAD_LIMIAR_SAIR = 0.35  # ...e continua sendo até cair abaixo desta (o Silero sugere 0,15 a menos)
FIM_SILENCIO_VAD = 0.6  # PROVISÓRIO: sai da medição com a voz do Matheus


class _Silero:
    """O Silero VAD ao vivo: cada quadro de 512 amostras com as 64 de antes, e o
    estado (h, c) passando de um quadro pro outro — igual ao do lote do
    faster-whisper (conferido: diferença zero)."""

    def __init__(self):
        import numpy as np
        from faster_whisper.vad import get_vad_model
        self.np = np
        self.sessao = get_vad_model().session
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = np.zeros((1, 1, 128), dtype=np.float32)
        self.antes = np.zeros(64, dtype=np.float32)
        self.falando = False

    def fala(self, quadro: array.array) -> bool:
        np = self.np
        x = np.frombuffer(quadro.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
        saida, self.h, self.c = self.sessao.run(
            None, {'input': np.concatenate([self.antes, x])[None, :], 'h': self.h, 'c': self.c})
        self.antes = x[-64:]
        p = float(np.ravel(saida)[0])
        self.falando = p >= (VAD_LIMIAR_SAIR if self.falando else VAD_LIMIAR)
        return self.falando


# Motor Whisper. PROVISÓRIO até medir com a voz do Matheus.
PREVIA = 2.0  # segundos do começo do trecho que vão pro Whisper procurar a palavra

# A cascata (16/11/2026): o fim da fala custava FIM_SILENCIO de espera e mais
# ~0,3 s de Whisper depois dela. Agora, calado há RASCUNHO_SILENCIO, o que ele
# disse já vai pro Whisper; se ele continuar calado até o fim, o texto já está
# pronto. E um rascunho que termina em pergunta encerra em FIM_CEDO. Voltou a
# falar, o rascunho não vale e tudo segue como antes. PROVISÓRIO: os números
# saem do teste da escuta com a voz do Matheus.
RASCUNHO_SILENCIO = 0.35
FIM_CEDO = 0.6
FIM_CEDO_PONTOS = ('?',)
# O Whisper errou mais com o trecho cortado em RASCUNHO_SILENCIO do que com os
# FIM_SILENCIO de silêncio no fim (o teste da escuta, 16/11/2026: "sexta" virou
# "cesta"). Com isto, o silêncio do fim é completado (repetindo o ruído do
# próprio cômodo) até FIM_SILENCIO antes de ir pro Whisper.
COMPLETAR_SILENCIO = True
# A conferência cedo que não acha a palavra não fecha o trecho: no fim do
# silêncio ele é conferido de novo, inteiro, como antes da cascata. Medido em
# 16/11/2026: sem isto, "Solis, desliga a música" virou "Sani, Zizlega" na
# conferência cedo e não acordou. Custa um Whisper a mais por fala sem "Solis".
RECONFERIR = True


def _completado(amostras: array.array, silencio: float) -> array.array:
    # Em amostras inteiras: com segundos em float, a sobra de uma fração de
    # amostra virava um laço sem fim (e travou o servidor, 16/11/2026).
    falta = int(round((FIM_SILENCIO - silencio) * TAXA))
    n = min(int(silencio * TAXA), len(amostras))
    if not COMPLETAR_SILENCIO or falta <= 0 or n <= 0:
        return amostras
    ruido = amostras[-n:]
    saida = array.array('h', amostras)
    while falta > 0:
        k = min(n, falta)
        saida.extend(ruido[:k])
        falta -= k
    return saida
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
# começo da frase ou depois de até duas palavras curtas ("ei, Solis", "olha,
# Solis"). Antes era só ei/oi/ok: no teste com a voz do Matheus (16/11/2026) o
# "Ei Solis" virou "É isso, Solis." e a chamada se perdeu. Três palavras ou
# mais antes ("me passa o Solis") é conversa, não chamada.
# O "S" pode sumir no começo da fala ("Olis").
_PALAVRA = re.compile(r"^[\s\W]*(?:[a-z]{1,5}[\s,!.?-]+){0,2}?s?ol+[eiy]s+e?\b[\s,!.:;?-]*")


# Quem chama não põe artigo nem preposição antes do nome: "do Solis", "que o
# Solis", "no Solis" é falar DO Solis, não chamar. Relato do Matheus (18/11/2026):
# falando com ele, uma pausa no meio da frase e o resto ("...uma função do
# Solis") chamava de novo — a escuta aceita até duas palavras curtas antes.
_NAO_CHAMA = {'o', 'a', 'os', 'as', 'um', 'uma', 'do', 'da', 'dos', 'das', 'no', 'na', 'nos', 'nas', 'ao',
              'aos', 'pro', 'pra', 'pelo', 'pela', 'de', 'em', 'com', 'por', 'que', 'meu', 'seu', 'teu',
              'nosso', 'esse', 'este', 'sem', 'sobre', 'como'}


def palavra_no_inicio(texto: str) -> tuple[bool, str]:
    """(achou, o resto): "Solis, me lembra de pagar a luz." → (True, "Me lembra
    de pagar a luz.")."""
    m = _PALAVRA.match(_sem_acento(texto))
    antes = re.findall(r'[a-z]+', _sem_acento(texto)[:m.end()])[:-1] if m else []
    if not m or (antes and antes[-1] in _NAO_CHAMA):
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

    def __init__(self, motor_=None, whisper=False, vad: str | None = None):
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
        self.vad = vad or VAD
        self.silero = _Silero() if self.vad == 'silero' else None
        self.fim_silencio = FIM_SILENCIO_VAD if self.silero else FIM_SILENCIO
        self._fala_vad = False
        # Segundos que a decisão do Whisper demorou: o áudio desse tempo ficou na
        # fila, e a pessoa só começa o pedido depois do bipe. Os prazos do comando
        # contam a partir do bipe, não do "Solis".
        self.espera_extra = 0.0
        # A cascata: o texto do comando até aqui (vale enquanto ele não voltar a
        # falar), se já foi pedido nesta pausa, e o texto pronto do comando que acabou.
        self.rascunho: str | None = None
        self.rascunho_pedido = False
        self.pronto: str | None = None
        self.conferido = False  # o trecho já foi conferido (sem a palavra): não confere no fim
        self.cedo_feito = False  # a conferência cedo desta pausa já saiu
        self._ultimo = ''  # o último evento de trecho: 'previa', 'cedo' ou 'frase'
        self._ruido: list[float] = []  # aprender_piso: a energia dos quadros só de ruído

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

    def confirmar(self, atraso: float = 0.0, resto: str = '') -> str | None:
        """A palavra estava no trecho. `resto`: o que veio depois dela no texto.
        `atraso`: quanto a decisão demorou (o Whisper carregando, por exemplo) —
        o prazo pra começar a falar estica isso, até ATRASO_MAX.

        Devolve o comando já pronto quando o trecho acabou com ele inteiro
        ("Solis, que horas são?" e silêncio); senão None, e o comando segue:
        - na prévia (a pessoa ainda fala), o trecho vira o começo do comando;
        - conferido cedo com o pedido junto, o trecho vira o comando e o texto
          fica de rascunho — se ela continuar calada, já está pronto;
        - só "Solis" (e a pausa), o comando começa vazio: o pedido vem depois do bipe."""
        self.ativacoes += 1
        self.espera_extra = min(max(0.0, atraso), ATRASO_MAX)
        self.rascunho, self.rascunho_pedido, self.pronto = None, False, None
        aberto = self.trecho is not None
        if not aberto and resto:
            return resto
        if aberto and (self._ultimo == 'previa' or resto):
            self.comando, self.fala, self.silencio = self.trecho, self.t_fala, self.t_silencio
            if self._ultimo == 'cedo':
                self.rascunho, self.rascunho_pedido = resto, True
                # O pedido já foi dito: o fim não pode esperar mais fala.
                self.fala = max(self.fala, FALA_MINIMA)
        else:
            self.comando, self.fala, self.silencio = array.array('h'), 0.0, 0.0
        self.trecho = None
        return None

    def aprender_piso(self, pcm: bytes) -> float:
        """Só o ruído de fundo, sem evento nenhum: uma escuta nova (a reserva do
        modo Conversa, que já começa no pedido) não sabe ainda o que é silêncio
        na sala — com o piso padrão, o ruído da gravação do teste contou como
        fala e o pedido não acabava (18/11/2026). O piso fica na mediana dos
        quadros ouvidos (quem falar no meio não o puxa tanto pra cima). Medido em
        4 pedidos da gravação: o 30º percentil deixou um sem fim; a mediana
        acabou todos. PROVISÓRIO: medir no modo Conversa (o microfone dele tem
        a supressão de ruído ligada). Devolve os segundos já ouvidos."""
        self.sobra.frombytes(pcm[: len(pcm) - len(pcm) % 2])
        while len(self.sobra) >= self.n:
            quadro = self.sobra[: self.n]
            del self.sobra[: self.n]
            if self.silero:
                self.silero.fala(quadro)
            self._ruido.append(_energia(quadro))
        if self._ruido:
            self.piso = sorted(self._ruido)[len(self._ruido) // 2]
        return len(self._ruido) * self.n / TAXA

    def seguir(self) -> bool:
        """O Solis acabou de falar perguntando algo ("qual música?"): o pedido
        começa já, sem a palavra, e vale como um "Solis" ouvido agora — até
        INICIO_MAX pra pessoa começar a responder, senão ('comando', None).
        Com um pedido já aberto, nada muda (False). Pedido do Matheus,
        17/11/2026: a resposta dele à pergunta se perdia."""
        if self.comando is not None:
            return False
        self.ativacoes += 1
        self.trecho = None
        self.antes.clear()
        self.comando, self.fala, self.silencio = array.array('h'), 0.0, 0.0
        self.espera_extra = 0.0
        self.rascunho, self.rascunho_pedido, self.pronto = None, False, None
        return True

    def descartar(self):
        """Sem a palavra: o resto do trecho é ignorado até ele acabar. Conferido
        cedo, não: no fim do silêncio o trecho inteiro é conferido de novo
        (RECONFERIR), e também se a pessoa voltar a falar."""
        if self._ultimo != 'cedo':
            self.previa_feita = True
        elif not RECONFERIR:
            self.conferido = True

    def guardar_rascunho(self, texto: str):
        """O texto do evento 'rascunho' (sem a palavra do começo)."""
        if self.comando is not None:
            self.rascunho = texto

    def _e_fala(self, db: float, margem: float | None = None) -> bool:
        if self.silero:
            return self._fala_vad
        # Lido na hora (e não como valor padrão do argumento, que congelava o de
        # quando o módulo carregou): o teste da escuta mede variações dele.
        return db > max(self.piso + (ACIMA_DO_PISO if margem is None else margem), FALA_MIN_DB)

    def _quadro(self, quadro: array.array):
        dur = self.n / TAXA
        db = _energia(quadro)
        if self.silero:
            # Todo quadro passa pelo Silero, até no comando: o estado dele é contínuo.
            self._fala_vad = self.silero.fala(quadro)
        if self.comando is None:
            # O piso de ruído acompanha o ambiente devagar, só fora do comando.
            self.piso = 0.98 * self.piso + 0.02 * db
            if self.motor is not None:
                if self.motor.process(quadro) >= 0:
                    self.ativacoes += 1
                    self.comando, self.fala, self.silencio = array.array('h'), 0.0, 0.0
                    self.espera_extra = 0.0
                    return ('ativou', None)
                return None
            return self._trecho(quadro, db, dur)
        self.comando.extend(quadro)
        # Depois do "Solis", fala mais baixa ainda conta: quem chamou vai falar.
        if self._e_fala(db, ACIMA_DO_PISO_COMANDO):
            self.fala += dur
            self.silencio = 0.0
            # Voltou a falar: o rascunho ficou velho.
            self.rascunho, self.rascunho_pedido = None, False
        else:
            self.silencio += dur
        total = len(self.comando) / TAXA
        cedo = (self.rascunho is not None and self.rascunho.rstrip().endswith(FIM_CEDO_PONTOS)
                and self.silencio >= FIM_CEDO)
        acabou = ((self.fala >= FALA_MINIMA and (self.silencio >= self.fim_silencio or cedo))
                  or total >= COMANDO_MAX + self.espera_extra)
        desistiu = self.fala < FALA_MINIMA and total >= INICIO_MAX + self.espera_extra
        if acabou or desistiu:
            audio, self.comando = self.comando, None
            # O rascunho que vale (ele não falou mais depois) é o texto do comando.
            self.pronto = None if desistiu else self.rascunho
            self.rascunho, self.rascunho_pedido = None, False
            return ('comando', None if desistiu else _wav(audio))
        if (not self.rascunho_pedido and self.fala >= FALA_MINIMA and self.silencio >= RASCUNHO_SILENCIO):
            self.rascunho_pedido = True
            return ('rascunho', _wav(_completado(self.comando, self.silencio)))
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
            self.t_fala, self.t_silencio, self.previa_feita, self.conferido = dur, 0.0, False, False
            self.cedo_feito = False
            return None
        self.trecho.extend(quadro)
        if fala:
            self.t_fala += dur
            self.t_silencio = 0.0
            # Conferido cedo e voltou a falar: confere de novo, inteiro, no fim.
            self.conferido = self.cedo_feito = False
        else:
            self.t_silencio += dur
        total = len(self.trecho) / TAXA
        if self.t_silencio >= self.fim_silencio or total >= COMANDO_MAX:
            trecho, self.trecho = self.trecho, None
            if self.previa_feita or self.conferido or self.t_fala < FALA_MINIMA / 2:
                return None  # já conferido (sem a palavra), ou só um estalo
            self.trechos += 1
            self._ultimo = 'frase'
            return ('frase', _wav(trecho))
        # A cascata: calado há RASCUNHO_SILENCIO, o trecho já vai conferir — com a
        # palavra, não espera o resto do silêncio.
        if (not self.previa_feita and not self.cedo_feito and not fala
                and self.t_silencio >= RASCUNHO_SILENCIO and self.t_fala >= FALA_MINIMA / 2):
            self.cedo_feito = True
            self.trechos += 1
            self._ultimo = 'cedo'
            return ('frase', _wav(_completado(self.trecho, self.t_silencio)))
        # A prévia só sai com a pessoa ainda falando: trecho que está acabando
        # vai inteiro como 'frase' (senão "Solis" + pausa viraria prévia).
        if not self.previa_feita and fala and total >= PREVIA:
            self.previa_feita = True
            self.trechos += 1
            self._ultimo = 'previa'
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
