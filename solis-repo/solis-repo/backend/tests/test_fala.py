"""O Solis falando: o texto como se fala, os pedaços, a língua, a cadeia de
vozes (nuvem → reserva → local) e o privado só na local — sem rede de verdade."""
import asyncio
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from solis import apis, banco, cofre, fala, main


@pytest.fixture
def vozes(monkeypatch):
    """Vozes falsas que anotam quem foi chamado; cada uma pode falhar."""
    chamadas = []
    falhas = {}

    def voz(nome):
        async def falar(texto, lingua):
            chamadas.append((nome, lingua, texto))
            if nome in falhas:
                raise fala.SemVoz(falhas[nome])
            return f'{nome}:{texto}'.encode()
        return falar

    monkeypatch.setattr(fala, 'NUVEM', [('gemini', 'audio/wav', voz('gemini')), ('ava', 'audio/mpeg', voz('ava'))])
    monkeypatch.setattr(fala, 'LOCAL', [('kokoro', 'audio/wav', voz('kokoro'))])
    monkeypatch.setattr(fala, '_fora_ate', {})
    monkeypatch.setattr(fala, '_cache', type(fala._cache)())
    return chamadas, falhas


def test_limpa_markdown_codigo_e_link():
    texto = ('## Resumo\n\n**Pagar** a luz e `revisar` o código:\n\n- item um\n- item dois\n\n'
             '```python\nprint(1)\n```\nVeja https://exemplo.com/x e [a doc](https://d.com).')
    assert fala.limpar(texto) == (
        'Resumo. Pagar a luz e revisar o código: item um, item dois. (um trecho de código). Veja o link e a doc.'
    )


def test_partes_juntam_frases_ate_o_limite():
    frases = ' '.join(f'Esta é a frase número {i}, com algumas palavras a mais.' for i in range(12))
    partes = fala.partes(frases)
    assert len(partes) > 1
    assert all(len(p) <= fala.PARTE_MAX for p in partes)
    assert ' '.join(partes) == fala.limpar(frases)


def test_frase_enorme_sem_ponto_e_cortada():
    longa = ', '.join(['uma coisa e mais outra coisa'] * 40)
    partes = fala.partes(longa)
    assert len(partes) > 1 and all(len(p) <= fala.PARTE_MAX * 2 for p in partes)


def test_lingua():
    assert fala.lingua('Você tem duas tarefas pra hoje, não esqueça.') == 'pt'
    assert fala.lingua('You have two tasks for today and the meeting is at nine.') == 'en'
    assert fala.lingua('Ok.') == 'pt'


def test_cadeia_usa_a_primeira_que_fala(vozes):
    chamadas, _ = vozes
    audio, tipo, quem = asyncio.run(fala.falar('Bom dia, você tem uma reunião.'))
    assert (quem, tipo, audio) == ('gemini', 'audio/wav', 'gemini:Bom dia, você tem uma reunião.'.encode())
    assert [c[0] for c in chamadas] == ['gemini']


def test_cai_pra_reserva_e_depois_pra_local(vozes):
    chamadas, falhas = vozes
    falhas['gemini'] = 'sem chave do Gemini'
    assert asyncio.run(fala.falar('Bom dia.'))[2] == 'ava'
    falhas['ava'] = 'ClientConnectorError'  # sem internet
    assert asyncio.run(fala.falar('Outra frase.'))[2] == 'kokoro'


def test_limite_ou_chave_recusada_deixa_a_voz_descansando(vozes):
    chamadas, falhas = vozes
    falhas['gemini'] = 'Gemini respondeu 429'
    asyncio.run(fala.falar('Uma.'))
    asyncio.run(fala.falar('Duas.'))
    assert [c[0] for c in chamadas].count('gemini') == 1  # na segunda nem tentou


def test_privado_so_na_voz_local(vozes):
    chamadas, _ = vozes
    # Texto de saúde ou dinheiro: local.
    assert asyncio.run(fala.falar('Sua consulta no dentista é amanhã.'))[2] == 'kokoro'
    # Conversa com algo privado: local, mesmo com texto comum.
    conversa = banco.nova_conversa()
    banco.adicionar(conversa, 'pessoa', 'isso é privado', privada=True)
    assert asyncio.run(fala.falar('Bom dia, tudo certo.', conversa))[2] == 'kokoro'
    assert all(c[0] == 'kokoro' for c in chamadas)


def test_nenhuma_voz_e_erro_com_os_motivos(vozes):
    _, falhas = vozes
    falhas.update(gemini='sem chave', ava='sem internet', kokoro='falta a Kokoro')
    with pytest.raises(fala.SemVoz, match='gemini: sem chave.*ava: sem internet.*kokoro: falta a Kokoro'):
        asyncio.run(fala.falar('Bom dia.'))


def test_mesmo_pedaco_sai_do_cache(vozes):
    chamadas, _ = vozes
    asyncio.run(fala.falar('Bom dia.'))
    asyncio.run(fala.falar('Bom dia.'))
    assert len(chamadas) == 1


def test_rotas(vozes):
    c = TestClient(main.app)
    r = c.post('/fala/partes', json={'texto': 'Bom dia! Você tem duas tarefas pra hoje.'})
    assert r.json() == {'partes': ['Bom dia! Você tem duas tarefas pra hoje.'], 'lingua': 'pt'}
    r = c.post('/fala', json={'texto': 'Bom dia!'})
    assert r.status_code == 200 and r.content == b'gemini:Bom dia!'
    assert r.headers['content-type'] == 'audio/wav' and r.headers['x-solis-voz'] == 'gemini'


def test_rota_sem_voz_e_503(vozes):
    _, falhas = vozes
    falhas.update(gemini='x', ava='y', kokoro='z')
    r = TestClient(main.app).post('/fala', json={'texto': 'Bom dia!'})
    assert r.status_code == 503 and r.json()['erro'] == 'sem_voz'


def test_gemini_manda_o_pedido_certo_e_le_o_audio(monkeypatch):
    banco.guardar_ajuste('chave:gemini', cofre.selar('chave-boa'))
    wav = b'RIFF....WAVEfmt '
    recebidos = []

    def responder(pedido: httpx.Request):
        recebidos.append(pedido)
        return httpx.Response(200, json={'steps': [
            {'type': 'thought'},
            {'type': 'model_output', 'content': [{'type': 'audio', 'data': base64.b64encode(wav).decode()}]},
        ]})
    audio = asyncio.run(fala.gemini('Bom dia.', 'pt', httpx.MockTransport(responder)))
    assert audio == wav
    [pedido] = recebidos
    assert str(pedido.url) == fala.GEMINI_URL and pedido.headers['x-goog-api-key'] == 'chave-boa'
    corpo = json.loads(pedido.content)
    assert corpo['model'] == fala.GEMINI_MODELO and corpo['response_format'] == {'type': 'audio'}
    assert corpo['generation_config']['speech_config'] == [{'voice': fala.GEMINI_VOZ}]
    assert corpo['input'][0]['content'][0]['text'] == 'Bom dia.'


def test_gemini_sem_chave_ou_com_erro():
    with pytest.raises(fala.SemVoz, match='sem chave'):
        asyncio.run(fala.gemini('Oi.', 'pt'))
    banco.guardar_ajuste('chave:gemini', cofre.selar('k'))
    with pytest.raises(fala.SemVoz, match='429'):
        asyncio.run(fala.gemini('Oi.', 'pt', httpx.MockTransport(lambda r: httpx.Response(429))))


def test_primeiro_pedaco_e_curto_pra_comecar_logo():
    texto = 'Bom dia, Matheus. Você tem duas tarefas hoje. A reunião é às nove. Depois tem o treino às sete da noite.'
    partes = fala.partes(texto)
    assert partes[0] == 'Bom dia, Matheus. Você tem duas tarefas hoje. A reunião é às nove.'
    assert partes[1] == 'Depois tem o treino às sete da noite.'
    assert len(partes[0]) <= fala.PRIMEIRA_MAX and ' '.join(partes) == fala.limpar(texto)


def test_voz_e_modelo_escolhidos_vao_pro_gemini():
    banco.guardar_ajuste('chave:gemini', cofre.selar('k'))
    corpos = []

    def responder(pedido):
        corpos.append(json.loads(pedido.content))
        return httpx.Response(200, json={'steps': [{'type': 'model_output', 'content': [
            {'type': 'audio', 'data': base64.b64encode(b'wav').decode()}]}]})
    fala.ajustar(voz='Charon', modelo='gemini-3.8-flash-lite-tts')
    asyncio.run(fala.gemini('Oi.', 'pt', httpx.MockTransport(responder)))
    asyncio.run(fala.gemini('Oi.', 'pt', httpx.MockTransport(responder), voz='Iapetus'))
    assert corpos[0]['model'] == 'gemini-3.8-flash-lite-tts'
    assert [c['generation_config']['speech_config'][0]['voice'] for c in corpos] == ['Charon', 'Iapetus']
    with pytest.raises(ValueError):
        fala.ajustar(voz='Inventada')


def test_rota_de_ajustes():
    c = TestClient(main.app)
    d = c.get('/fala/ajustes').json()
    assert d['voz'] == fala.GEMINI_VOZ and 'Sulafat' in d['vozes'] and len(d['vozes']) == 30
    assert c.put('/fala/ajustes', json={'voz': 'Achird'}).json()['voz'] == 'Achird'
    assert c.put('/fala/ajustes', json={'modelo': 'gpt-4'}).status_code == 400


def test_limite_do_google_faz_a_voz_descansar_o_tempo_que_ele_mandar(vozes, monkeypatch):
    _, falhas = vozes
    falhas['gemini'] = 'Gemini respondeu 429: limit 10 requests per day. Please retry in 11h57m24s'
    agora = 1_000_000.0
    monkeypatch.setattr(fala.time, 'time', lambda: agora)
    asyncio.run(fala.falar('Uma.'))
    assert fala._fora_ate['gemini'] == agora + 11 * 3600 + 57 * 60 + 24
    assert fala.ultimos_motivos and fala.ultimos_motivos[0].startswith('gemini: Gemini respondeu 429')


def test_trocar_o_modelo_tira_o_gemini_do_descanso(vozes):
    fala._fora_ate['gemini'] = 9e18
    fala.ajustar(modelo='gemini-3.8-flash-lite-tts')
    assert 'gemini' not in fala._fora_ate


def test_motivo_com_quebra_de_linha_nao_derruba_a_resposta(vozes):
    """O erro do Google vem em JSON com quebras de linha; no cabeçalho, isso
    derrubava a resposta inteira (h11: Illegal header value)."""
    _, falhas = vozes
    falhas['gemini'] = 'Gemini respondeu 400: [{\n  "error": {\n    "message": "API key not valid. Ação"'
    r = TestClient(main.app).post('/fala', json={'texto': 'Bom dia!'})
    assert r.status_code == 200 and r.headers['x-solis-voz'] == 'ava'
    assert '\n' not in r.headers['x-solis-antes'] and 'API key not valid' in r.headers['x-solis-antes']
