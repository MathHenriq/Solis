"""Exemplos de "Solis" com vozes em português (o treinador do openWakeWord só tem
vozes em inglês, que dizem "SÔ-liss"): as vozes do Edge (pt-BR, pt-PT e as
multilíngues, entre elas a Ava do Solis), em três velocidades e três tons,
salvas como WAV 16 kHz mono em design/_treino-solis/positivos-tts/ (fora do git).

Uso: backend/.venv/Scripts/python design/gravar-solis/gerar_vozes.py
"""
import asyncio
import io
import wave
from pathlib import Path

import av
import edge_tts
import numpy as np

DESTINO = Path(__file__).resolve().parents[1] / '_treino-solis' / 'positivos-tts'
VOZES = ['pt-BR-ThalitaMultilingualNeural', 'pt-BR-AntonioNeural', 'pt-BR-FranciscaNeural', 'pt-PT-DuarteNeural',
         'pt-PT-RaquelNeural', 'en-US-AvaMultilingualNeural', 'en-US-AndrewMultilingualNeural',
         'en-US-BrianMultilingualNeural', 'en-US-EmmaMultilingualNeural', 'fr-FR-VivienneMultilingualNeural',
         'it-IT-GiuseppeMultilingualNeural']
FRASES = ['Solis.', 'Solis!', 'Ei, Solis.', 'Oi, Solis.', 'Solis?']
VELOCIDADES = ['-20%', '+0%', '+20%']
TONS = ['-8Hz', '+0Hz', '+8Hz']


def para_wav(mp3: bytes) -> bytes:
    entrada = av.open(io.BytesIO(mp3))
    reamostra = av.AudioResampler(format='s16', layout='mono', rate=16000)
    partes = [q.to_ndarray().reshape(-1) for f in entrada.decode(audio=0) for q in reamostra.resample(f)]
    partes += [q.to_ndarray().reshape(-1) for q in reamostra.resample(None)]
    pcm = np.concatenate(partes).astype(np.int16)
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    return saida.getvalue()


async def um(sem, voz, frase, velocidade, tom, n):
    nome = DESTINO / f'{n:04d}-{voz.split("-")[2].replace("Neural", "")}.wav'
    if nome.exists():
        return 'já'
    async with sem:
        for tentativa in range(3):
            try:
                dados = b''
                async for p in edge_tts.Communicate(frase, voz, rate=velocidade, pitch=tom).stream():
                    if p['type'] == 'audio':
                        dados += p['data']
                nome.write_bytes(para_wav(dados))
                return 'ok'
            except Exception:  # noqa: BLE001 — o serviço falhou: tenta de novo
                await asyncio.sleep(2 * (tentativa + 1))
    return 'falhou'


async def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(4)
    tarefas, n = [], 0
    for voz in VOZES:
        for frase in FRASES:
            for v in VELOCIDADES:
                for t in TONS:
                    n += 1
                    tarefas.append(um(sem, voz, frase, v, t, n))
    r = await asyncio.gather(*tarefas)
    print({k: r.count(k) for k in set(r)}, 'em', DESTINO)


asyncio.run(main())
