"""A voz G (fala._gemini_aos_pedacos): o Gemini Flash TTS · Aoede, a primeira
do teste cego do Matheus (21/11/2026), em pedaços pelo streamGenerateContent,
virando mp3 enquanto chega. Sem rede: o Gemini e a Fish são simulados."""
import asyncio
import base64
import io
import json

import httpx
import numpy as np

from solis import banco, cofre, fala


def _sse_de_pcm(segundos=1.0, pedacos=5):
    """O que o Gemini manda: linhas SSE com PCM 24 kHz (uma senoide)."""
    t = np.arange(int(24000 * segundos)) / 24000
    pcm = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16).tobytes()
    tam = len(pcm) // pedacos // 2 * 2
    linhas = []
    for i in range(pedacos):
        parte = pcm[i * tam:(i + 1) * tam]
        linhas.append('data: ' + json.dumps({'candidates': [{'content': {'parts': [
            {'inlineData': {'mimeType': 'audio/L16;rate=24000', 'data': base64.b64encode(parte).decode()}}]}}]}))
    return ('\n\n'.join(linhas) + '\n\n').encode()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def cache_limpo():
    """Outros testes deixam frases no cache da voz (a mesma frase sairia de lá)."""
    fala._cache.clear()
    fala._fora_ate.clear()
    yield
    fala._cache.clear()
    fala._fora_ate.clear()


def _falar(texto):
    """(o áudio inteiro, tipo, quem): pedir e ler no MESMO laço, como a rota faz."""
    async def ir():
        pedacos, tipo, quem = await fala.falar_aos_pedacos(texto)
        return b''.join([p async for p in pedacos]), tipo, quem
    return asyncio.run(ir())


def test_a_voz_g_vem_primeiro_em_pedacos_e_vira_mp3(monkeypatch):
    banco.guardar_ajuste('chave:gemini', cofre.selar('chave-boa'))
    pedidos = []

    def gemini(req):
        pedidos.append(req)
        return httpx.Response(200, content=_sse_de_pcm(), headers={'content-type': 'text/event-stream'})
    monkeypatch.setattr(fala, '_transporte_gemini', httpx.MockTransport(gemini))
    mp3, tipo, quem = _falar('Pronto, abri o YouTube pra você.')
    assert (tipo, quem) == ('audio/mpeg', 'gemini-flash')
    req = pedidos[0]
    assert str(req.url).startswith(f'https://generativelanguage.googleapis.com/v1beta/models/{fala.GEMINI_FLUXO_MODELO}:'
                                   'streamGenerateContent')
    corpo = json.loads(req.content)
    assert corpo['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'] == 'Aoede'
    assert req.headers['x-goog-api-key'] == 'chave-boa'
    # Um mp3 de verdade, com a duração do que veio (1 s).
    import av
    c = av.open(io.BytesIO(mp3))
    assert c.streams.audio[0].codec_context.name.startswith('mp3')
    duracao = sum(f.samples for f in c.decode(audio=0)) / 24000
    assert 0.9 < duracao < 1.2


def test_sem_cota_do_gratis_cai_pra_fish_e_a_voz_g_descansa(monkeypatch):
    banco.guardar_ajuste('chave:gemini', cofre.selar('chave-boa'))
    banco.guardar_ajuste('chave:fish', cofre.selar('fk-teste'))
    fala._fora_ate.clear()
    vezes = []

    def gemini(req):
        vezes.append(1)
        return httpx.Response(429, json={'error': {'message': 'Quota exceeded. Please retry in 3600s.'}})
    monkeypatch.setattr(fala, '_transporte_gemini', httpx.MockTransport(gemini))
    monkeypatch.setattr(fala, '_transporte_fish', httpx.MockTransport(lambda req: httpx.Response(200, content=b'ID3fish')))
    audio, _, quem = _falar('Bom dia, Matheus.')
    assert quem == 'fish' and audio == b'ID3fish'
    assert fala._fora_ate['gemini-flash'] > 0
    # Na próxima, nem tenta (descansando).
    _, _, quem = _falar('Outra frase.')
    assert quem == 'fish' and len(vezes) == 1
    fala._fora_ate.clear()


def test_o_privado_nao_vai_pra_voz_g(monkeypatch):
    banco.guardar_ajuste('chave:gemini', cofre.selar('chave-boa'))
    vezes = []
    monkeypatch.setattr(fala, '_transporte_gemini', httpx.MockTransport(lambda req: vezes.append(1)))
    monkeypatch.setattr(fala, 'privado', lambda texto, conversa: True)

    async def local(texto, lingua_):
        return b'RIFFlocal'
    monkeypatch.setattr(fala, 'LOCAL', [('kokoro', 'audio/wav', local)])
    _, _, quem = asyncio.run(fala.falar_aos_pedacos('Meu saldo é cem reais.'))
    assert quem == 'kokoro' and vezes == []
