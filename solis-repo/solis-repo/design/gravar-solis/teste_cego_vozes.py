"""O teste cego das vozes do Solis (21/11/2026): as mesmas falas em cada voz
que dá pra usar, sorteadas com letras (A, B, C...). O Matheus ouve e escolhe
sem saber qual é qual; o mapa fica em mapa.json, fora da página.

Usa as funções de voz do próprio Solis (backend/solis/fala.py) e as chaves do
cofre dele (uma cópia do banco, só pra ler). Mede também o tempo até o áudio
de cada uma. Sai em design/_amostras-voz/teste-cego/: os áudios, o mapa e
dados.json (o que a página do teste mostra).

Uso: backend\\.venv\\Scripts\\python design\\gravar-solis\\teste_cego_vozes.py
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import random
import sqlite3
import sys
import tempfile
import time
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'backend'))
SAIDA = REPO / 'design' / '_amostras-voz' / 'teste-cego'

# O banco de verdade, copiado (só pra ler as chaves do cofre: Gemini e Fish).
copia = Path(tempfile.mkdtemp()) / 'solis.db'
origem = sqlite3.connect(f"file:{Path(os.environ['APPDATA']) / 'Solis' / 'solis.db'}?mode=ro", uri=True)
destino = sqlite3.connect(copia)
origem.backup(destino)
origem.close()
destino.close()

from solis import banco, fala  # noqa: E402

banco.usar(copia)

FALAS = [
    'Bom dia, Matheus! Hoje você tem reunião às três da tarde, e o dólar abriu em cinco e trinta e cinco.',
    'Pronto, abri o YouTube pra você. Quer que eu coloque aquela playlist de foco?',
    'Olha, o servidor da Micro Ka caiu faz dez minutos. Já reiniciei e está tudo no ar de novo, mas vale '
    'ficar de olho.',
]


async def edge(texto, voz):
    import edge_tts
    pedacos = []
    async for p in edge_tts.Communicate(texto, voz).stream():
        if p['type'] == 'audio':
            pedacos.append(p['data'])
    return b''.join(pedacos)


def gemini_com(modelo, voz):
    async def f(texto):
        fala.modelo_gemini = lambda: modelo
        return await fala.gemini(texto, 'pt', voz=voz)
    return f


CANDIDATAS = [
    ('Fish Audio (s2.1-pro-free, a voz padrão)', 'nuvem, grátis por enquanto', 'audio/mpeg',
     lambda t: fala.fish(t, 'pt')),
    ('Gemini Flash Lite TTS · Aoede (a de hoje)', 'nuvem, grátis (pago: ~US$ 0,009/min)', 'audio/wav',
     gemini_com('gemini-3.8-flash-lite-tts', 'Aoede')),
    ('Gemini Flash TTS · Aoede', 'nuvem, grátis 10 pedidos/dia (pago: ~US$ 0,014/min)', 'audio/wav',
     gemini_com('gemini-3.8-flash-tts', 'Aoede')),
    ('Gemini Flash Lite TTS · Charon', 'nuvem, grátis', 'audio/wav', gemini_com('gemini-3.8-flash-lite-tts', 'Charon')),
    ('Gemini Flash Lite TTS · Puck', 'nuvem, grátis', 'audio/wav', gemini_com('gemini-3.8-flash-lite-tts', 'Puck')),
    ('Edge · Francisca (pt-BR)', 'nuvem, sem chave e sem garantia', 'audio/mpeg',
     lambda t: edge(t, 'pt-BR-FranciscaNeural')),
    ('Edge · Antonio (pt-BR)', 'nuvem, sem chave e sem garantia', 'audio/mpeg', lambda t: edge(t, 'pt-BR-AntonioNeural')),
    ('Edge · Thalita Multilingual (pt-BR)', 'nuvem, sem chave e sem garantia', 'audio/mpeg',
     lambda t: edge(t, 'pt-BR-ThalitaMultilingualNeural')),
    ('Kokoro · pf_dora (local)', 'no PC, sem internet', 'audio/wav', lambda t: fala.kokoro(t, 'pt')),
]


async def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    random.seed(21112026)
    ordem = list(range(len(CANDIDATAS)))
    random.shuffle(ordem)
    letras = 'ABCDEFGHIJKLMNOP'
    mapa, dados = {}, []
    for pos, i in enumerate(ordem):
        nome, custo, tipo, f = CANDIDATAS[i]
        letra = letras[pos]
        audios, tempos, erro = [], [], None
        for k, texto in enumerate(FALAS):
            t0 = time.perf_counter()
            try:
                audio = await f(texto)
            except Exception as e:  # noqa: BLE001 — a voz que falhou aparece como falha
                erro = f'{type(e).__name__}: {e}'[:200]
                break
            tempos.append(round(time.perf_counter() - t0, 2))
            ext = 'mp3' if tipo == 'audio/mpeg' else 'wav'
            arquivo = SAIDA / f'{letra}-{k + 1}.{ext}'
            arquivo.write_bytes(audio)
            audios.append({'arquivo': arquivo.name, 'tipo': tipo,
                           'dados': base64.b64encode(audio).decode()})
        mapa[letra] = {'voz': nome, 'custo': custo, 'segundos_ate_o_audio': tempos, 'erro': erro}
        dados.append({'letra': letra, 'audios': audios, 'erro': bool(erro)})
        print(f'{letra}: {nome} — {"ERRO " + erro if erro else tempos}', flush=True)
    (SAIDA / 'mapa.json').write_text(json.dumps(mapa, indent=1, ensure_ascii=False), encoding='utf-8')
    (SAIDA / 'dados.json').write_text(json.dumps({'falas': FALAS, 'vozes': dados}, ensure_ascii=False),
                                      encoding='utf-8')
    print('ok', SAIDA)


asyncio.run(main())
