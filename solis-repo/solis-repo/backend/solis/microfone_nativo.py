"""O microfone aberto direto do Windows, pelo servidor (21/11/2026).

A escuta abria o microfone na janela do app (o motor de navegador do WebView2).
Com o Discord numa chamada, isso estragava o som dos dois lados: a voz dos
amigos esquisita (19/11 e 21/11) e, com o som a 48 kHz, a voz do Matheus
abafada pra eles (21/11). A suspeita: o motor de navegador abre o microfone
como "chamada" e muda o modo do fone pra todo mundo.

Aqui o microfone é aberto como um gravador comum, pela API de gravação mais
simples do Windows (waveIn, da winmm.dll, que já vem no Windows — nada a
instalar): 16 kHz, 16 bits, mono, no aparelho padrão de gravação, em pedaços de
64 ms. Uma thread lê e entrega os pedaços numa fila do asyncio.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import threading
from ctypes import wintypes

log = logging.getLogger('solis.microfone_nativo')

TAXA = 16000
AMOSTRAS = 1024          # por pedaço (64 ms)
PEDACOS = 8              # na fila do Windows ao mesmo tempo
WAVE_MAPPER = 0xFFFFFFFF  # o aparelho padrão de gravação
CALLBACK_EVENT = 0x00050000
WHDR_DONE = 0x00000001


class _Formato(ctypes.Structure):
    _fields_ = [('wFormatTag', wintypes.WORD), ('nChannels', wintypes.WORD), ('nSamplesPerSec', wintypes.DWORD),
                ('nAvgBytesPerSec', wintypes.DWORD), ('nBlockAlign', wintypes.WORD),
                ('wBitsPerSample', wintypes.WORD), ('cbSize', wintypes.WORD)]


class _Cabecalho(ctypes.Structure):
    pass


_Cabecalho._fields_ = [('lpData', ctypes.c_void_p), ('dwBufferLength', wintypes.DWORD),
                       ('dwBytesRecorded', wintypes.DWORD), ('dwUser', ctypes.c_size_t),
                       ('dwFlags', wintypes.DWORD), ('dwLoops', wintypes.DWORD),
                       ('lpNext', ctypes.POINTER(_Cabecalho)), ('reserved', ctypes.c_size_t)]


class SemMicrofone(Exception):
    pass


class Gravador:
    """`abrir(laco, fila)` começa a gravar e põe cada pedaço (bytes PCM) na fila;
    `fechar()` para."""

    def __init__(self):
        self._handle = wintypes.HANDLE()
        self._evento = None
        self._cabecalhos: list[_Cabecalho] = []
        self._buffers: list = []
        self._parar = threading.Event()
        self._fio: threading.Thread | None = None

    def abrir(self, laco: asyncio.AbstractEventLoop, fila: asyncio.Queue) -> None:
        if os.name != 'nt':
            raise SemMicrofone('só no Windows')
        winmm = ctypes.WinDLL('winmm')
        kernel = ctypes.WinDLL('kernel32')
        kernel.CreateEventW.restype = wintypes.HANDLE
        self._winmm, self._kernel = winmm, kernel
        self._evento = kernel.CreateEventW(None, False, False, None)
        fmt = _Formato(1, 1, TAXA, TAXA * 2, 2, 16, 0)
        r = winmm.waveInOpen(ctypes.byref(self._handle), WAVE_MAPPER, ctypes.byref(fmt),
                             ctypes.c_size_t(self._evento), ctypes.c_size_t(0), CALLBACK_EVENT)
        if r != 0:
            raise SemMicrofone(f'o Windows não abriu o microfone (waveInOpen {r})')
        tamanho = AMOSTRAS * 2
        for _ in range(PEDACOS):
            buf = ctypes.create_string_buffer(tamanho)
            cab = _Cabecalho()
            cab.lpData = ctypes.cast(buf, ctypes.c_void_p)
            cab.dwBufferLength = tamanho
            winmm.waveInPrepareHeader(self._handle, ctypes.byref(cab), ctypes.sizeof(cab))
            winmm.waveInAddBuffer(self._handle, ctypes.byref(cab), ctypes.sizeof(cab))
            self._buffers.append(buf)
            self._cabecalhos.append(cab)
        if winmm.waveInStart(self._handle) != 0:
            self.fechar()
            raise SemMicrofone('o Windows não começou a gravar')
        self._parar.clear()
        self._fio = threading.Thread(target=self._ler, args=(laco, fila), daemon=True, name='solis-microfone-nativo')
        self._fio.start()
        log.info('microfone nativo: aberto (16 kHz, waveIn)')

    def _ler(self, laco, fila):
        while not self._parar.is_set():
            self._kernel.WaitForSingleObject(wintypes.HANDLE(self._evento), 200)
            for cab, buf in zip(self._cabecalhos, self._buffers):
                if self._parar.is_set():
                    return
                if cab.dwFlags & WHDR_DONE:
                    dados = buf.raw[:cab.dwBytesRecorded]
                    cab.dwFlags &= ~WHDR_DONE
                    self._winmm.waveInAddBuffer(self._handle, ctypes.byref(cab), ctypes.sizeof(cab))
                    if dados:
                        try:
                            laco.call_soon_threadsafe(fila.put_nowait, dados)
                        except RuntimeError:  # o laço fechou
                            return

    def fechar(self) -> None:
        self._parar.set()
        if self._fio is not None:
            self._fio.join(1)
            self._fio = None
        if self._handle:
            self._winmm.waveInReset(self._handle)
            for cab in self._cabecalhos:
                self._winmm.waveInUnprepareHeader(self._handle, ctypes.byref(cab), ctypes.sizeof(cab))
            self._winmm.waveInClose(self._handle)
            self._handle = wintypes.HANDLE()
            log.info('microfone nativo: fechado')
        if self._evento:
            self._kernel.CloseHandle(wintypes.HANDLE(self._evento))
            self._evento = None
        self._cabecalhos, self._buffers = [], []
