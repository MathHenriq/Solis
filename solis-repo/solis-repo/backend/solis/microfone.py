"""Quem mais está usando o microfone: a escuta do Solis sai do caminho de uma
chamada.

Relato do Matheus (19/11/2026, e o parecido de 18/11): com o Solis aberto, a
chamada do Discord ficava abafada (e no dia antes, o áudio dele sumia); com o
Solis fechado, voltava ao normal. Medido: no dia 18, fechar só a janela
principal — onde a escuta mora, com o microfone e um canal de som abertos o
tempo todo — já resolveu. Então, enquanto outro programa estiver com o
microfone ativo (o Discord numa chamada, o Zoom, o Meet...), a escuta solta o
microfone e o som dela por completo, e volta quando ele soltar.

O vigia (microfone_vigia.ps1) é um PowerShell só, ligado enquanto houver
escuta aberta: a cada segundo, os programas com uma sessão de captura ativa
(pela API de áudio do Windows), uma linha a cada mudança. O próprio Solis não
conta. Pelo PowerShell, como o OCR: é do sistema e já vem assinado.
"""
import asyncio
import json
import logging
import os
import subprocess
import threading
from pathlib import Path

log = logging.getLogger('solis.microfone')

SCRIPT = Path(__file__).with_name('microfone_vigia.ps1')

# Sair do caminho quando outro programa está no microfone. Testado desligado
# em 21/11/2026 com o Matheus numa chamada do Discord: o Solis ouviu todas as
# chamadas normais, mas a voz dos amigos no Discord ficou esquisita de novo
# (o mesmo de 19/11) — ligado de volta na hora, até achar a causa. Ligado, quem
# passa o dia num canal de voz fica com o Solis surdo. SOLIS_CEDER_MICROFONE=0 desliga.
# Teste 1 de 21/11/2026 (o som da escuta a 48 kHz em vez de 16): a voz DELE pros
# amigos ficou ruim e abafada — pior. Voltou a ceder.
CEDER = os.environ.get('SOLIS_CEDER_MICROFONE', '1') == '1'


class Vigia:
    """Um vigia pra todas as escutas abertas. `entrar()` devolve uma fila que
    recebe a lista de programas no microfone (a de agora, e cada mudança)."""

    def __init__(self):
        self.outros: list[str] = []
        self._filas: set[asyncio.Queue] = set()
        self._proc: subprocess.Popen | None = None
        self._laco: asyncio.AbstractEventLoop | None = None
        self._trava = threading.Lock()
        self._leu = threading.Event()  # a primeira leitura do vigia chegou

    def entrar(self) -> asyncio.Queue:
        fila: asyncio.Queue = asyncio.Queue()
        self._laco = asyncio.get_running_loop()
        with self._trava:
            self._filas.add(fila)
            if self._proc is None or self._proc.poll() is not None:
                self._ligar()
        fila.put_nowait(list(self.outros))
        return fila

    def sair(self, fila: asyncio.Queue) -> None:
        with self._trava:
            self._filas.discard(fila)
            if not self._filas:
                self._desligar()

    def _ligar(self) -> None:
        if os.name != 'nt':
            return
        try:
            self._proc = subprocess.Popen(
                ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError:
            log.warning('o vigia do microfone não abriu', exc_info=True)
            self._proc = None
            return
        self._leu.clear()
        threading.Thread(target=self._ler, args=(self._proc,), daemon=True, name='solis-microfone').start()

    async def primeira_leitura(self, espera: float = 4.0) -> None:
        """Espera o vigia dizer quem está no microfone agora (o PowerShell leva
        ~1-2 s pra subir): abrir o Solis no meio de uma chamada não pode abrir o
        microfone nem por um instante."""
        if self._proc is None or self._proc.poll() is not None:
            return
        await asyncio.to_thread(self._leu.wait, espera)

    def _desligar(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()
        self._proc = None
        self.outros = []

    def _ler(self, proc: subprocess.Popen) -> None:
        for linha in iter(proc.stdout.readline, b''):
            try:
                outros = [str(n) for n in json.loads(linha.decode('utf-8', 'replace'))['outros']]
            except (ValueError, KeyError, TypeError):
                continue
            self.mudou(outros)
            self._leu.set()

    def mudou(self, outros: list[str]) -> None:
        """Uma lista nova (do vigia, ou de um teste): vai pra todas as escutas."""
        if outros == self.outros:
            return
        if outros:
            log.info('microfone: %s está usando; %s', ', '.join(outros),
                     'a escuta solta' if CEDER else 'a escuta continua junto')
        else:
            log.info('microfone: livre de novo%s', '; a escuta volta' if CEDER else '')
        self.outros = outros
        laco = self._laco
        if laco is None:
            return
        with self._trava:
            filas = list(self._filas)
        for fila in filas:
            laco.call_soon_threadsafe(fila.put_nowait, list(outros))


vigia = Vigia()
