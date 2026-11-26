"""Gera a fala de teste do microfone falso (design/nuvem/testar_voz_celular.mjs):
"Que horas são?" numa voz do Edge, com 1 s de silêncio antes e 2 s depois, num
WAV de 48 kHz mono (o que o Chrome aceita como microfone falso). 26/11/2026.

Rodar da raiz do app:
    backend/.venv/Scripts/python design/nuvem/gerar_fala_teste.py <saida.wav>
"""
import asyncio
import sys
import wave
from pathlib import Path

import av
import edge_tts
import numpy as np

TEXTO = 'Que horas são?'
VOZ = 'pt-BR-AntonioNeural'
TAXA = 48000


async def mp3() -> bytes:
    partes = []
    async for pedaco in edge_tts.Communicate(TEXTO, VOZ).stream():
        if pedaco['type'] == 'audio':
            partes.append(pedaco['data'])
    return b''.join(partes)


def para_pcm(dados: bytes) -> np.ndarray:
    import io
    saida = []
    with av.open(io.BytesIO(dados)) as recipiente:
        conversor = av.AudioResampler(format='s16', layout='mono', rate=TAXA)
        for quadro in recipiente.decode(audio=0):
            saida += [q.to_ndarray() for q in conversor.resample(quadro)]
        saida += [q.to_ndarray() for q in conversor.resample(None)]
    return np.concatenate(saida, axis=1).ravel()


destino = Path(sys.argv[1])
fala = para_pcm(asyncio.run(mp3()))
tudo = np.concatenate([np.zeros(TAXA, np.int16), fala.astype(np.int16), np.zeros(2 * TAXA, np.int16)])
with wave.open(str(destino), 'wb') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(TAXA)
    w.writeframes(tudo.tobytes())
print(destino, f'{len(tudo) / TAXA:.1f} s')
