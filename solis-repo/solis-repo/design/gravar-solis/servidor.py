"""Gravar os "Solis" pra treinar a palavra (backend/solis/palavra.py): uma página
só neste computador (http://localhost:8790) que grava cada exemplo e guarda em
%LOCALAPPDATA%/Solis/voz/amostras-solis/<quem>/ como WAV de 16 kHz, mono, 16
bits (o formato do openWakeWord). Nada sai do computador. Fora do app: é uma
ferramenta de uma vez, pra montar o treino.

Uso (o Python do backend, que tem o `av`):
    backend/.venv/Scripts/python design/gravar-solis/servidor.py
"""
import io
import json
import os
import re
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import av
import numpy as np

PORTA = 8790
PASTA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Solis' / 'voz' / 'amostras-solis'
PAGINA = Path(__file__).with_name('pagina.html')


def para_wav(dados: bytes) -> bytes:
    """O que o navegador gravou (webm/opus) → WAV 16 kHz mono 16 bits."""
    entrada = av.open(io.BytesIO(dados))
    reamostra = av.AudioResampler(format='s16', layout='mono', rate=16000)
    partes = [q.to_ndarray().reshape(-1) for f in entrada.decode(audio=0) for q in reamostra.resample(f)]
    partes += [q.to_ndarray().reshape(-1) for q in reamostra.resample(None)]
    pcm = np.concatenate(partes).astype(np.int16) if partes else np.zeros(0, np.int16)
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    return saida.getvalue()


def _quem(texto: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (texto or 'matheus').lower()).strip('-')[:30] or 'matheus'


class Pedido(BaseHTTPRequestHandler):
    def _responder(self, codigo: int, corpo: bytes, tipo: str = 'application/json'):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/':
            return self._responder(200, PAGINA.read_bytes(), 'text/html; charset=utf-8')
        if url.path == '/contagem':
            quem = _quem(parse_qs(url.query).get('quem', [''])[0])
            n = len(list((PASTA / quem).glob('*.wav'))) if (PASTA / quem).is_dir() else 0
            return self._responder(200, json.dumps({'quem': quem, 'gravados': n}).encode())
        self._responder(404, b'{}')

    def do_POST(self):
        url = urlsplit(self.path)
        if url.path != '/salvar':
            return self._responder(404, b'{}')
        q = parse_qs(url.query)
        quem, n = _quem(q.get('quem', [''])[0]), int(q.get('n', ['0'])[0])
        tipo = re.sub(r'[^a-z0-9-]+', '', q.get('tipo', ['normal'])[0])[:20] or 'normal'
        dados = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        try:
            wav = para_wav(dados)
        except Exception as e:  # noqa: BLE001 — a gravação veio quebrada: a página pede de novo
            return self._responder(400, json.dumps({'erro': str(e)[:200]}).encode())
        (PASTA / quem).mkdir(parents=True, exist_ok=True)
        destino = PASTA / quem / f'{n:03d}-{tipo}.wav'
        destino.write_bytes(wav)
        segundos = (len(wav) - 44) / 32000
        self._responder(200, json.dumps({'ok': True, 'arquivo': destino.name, 'segundos': round(segundos, 2)}).encode())

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    print(f'Gravar os "Solis": abra http://localhost:{PORTA} no navegador. Guarda em {PASTA}')
    ThreadingHTTPServer(('127.0.0.1', PORTA), Pedido).serve_forever()
