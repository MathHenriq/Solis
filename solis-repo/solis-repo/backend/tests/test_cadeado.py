"""O cadeado da tela (26/11/2026, decisão do Matheus pra voz do celular): sem ele,
no servidor, a fala vai direto pra Groq (sem os 2–3 s da conferida no processador);
com ele, a fala, a mensagem, a resposta e o que ela ensinar ficam no Solis."""
import io
import json
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from solis import banco, main, memoria, roteador, transcricao, voz


def wav(segundos=1.0) -> bytes:
    t = np.arange(int(segundos * 16000)) / 16000
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16).tobytes())
    return saida.getvalue()


@pytest.fixture
def ouvidos(monkeypatch):
    """Quem transcreveu: a Groq, o pequeno (a conferida) ou o daqui."""
    quem = []

    async def nuvem(audio):
        quem.append('groq')
        return 'Quanto gastei esse mês?'

    async def pequeno(audio):
        quem.append('pequeno')
        return 'quanto gastei esse mes'

    async def daqui(audio, vad=True):
        quem.append('daqui')
        return {'texto': 'Minha senha do banco é 1234.', 'segundos': 0.1, 'duracao': 1.0}
    monkeypatch.setattr(transcricao, 'online', lambda: True)
    monkeypatch.setattr(transcricao, 'pequeno_disponivel', lambda: True)
    monkeypatch.setattr(transcricao, 'nuvem', nuvem)
    monkeypatch.setattr(transcricao, 'palavra', pequeno)
    monkeypatch.setattr(voz, 'transcrever', daqui)
    return quem


def test_no_servidor_sem_cadeado_vai_direto_pra_groq(ouvidos, monkeypatch):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setenv('SOLIS_TOKEN', 'um-token-de-teste-bem-comprido-123')
    c = TestClient(main.app, headers={'Authorization': 'Bearer um-token-de-teste-bem-comprido-123'})
    assert c.post('/voz', content=wav()).json()['texto'] == 'Quanto gastei esse mês?'
    assert ouvidos == ['groq']  # sem a conferida no processador


def test_no_pc_sem_cadeado_o_pequeno_confere_antes(ouvidos):
    assert TestClient(main.app).post('/voz', content=wav()).json()['texto'] == 'Quanto gastei esse mês?'
    assert ouvidos == ['pequeno', 'groq']


@pytest.mark.parametrize('servidor', [False, True])
def test_com_cadeado_a_fala_nao_sai_daqui(ouvidos, monkeypatch, servidor):
    cabecalhos = {}
    if servidor:
        monkeypatch.setenv('SOLIS_SERVIDOR', '1')
        monkeypatch.setenv('SOLIS_TOKEN', 'um-token-de-teste-bem-comprido-123')
        cabecalhos = {'Authorization': 'Bearer um-token-de-teste-bem-comprido-123'}
    r = TestClient(main.app, headers=cabecalhos).post('/voz?privado=1', content=wav())
    assert r.json()['texto'] == 'Minha senha do banco é 1234.'
    assert ouvidos == ['daqui']


def test_no_servidor_com_a_groq_fora_vai_o_daqui(ouvidos, monkeypatch):
    async def caiu(audio):
        raise transcricao.NuvemFalhou('rede')
    monkeypatch.setattr(transcricao, 'nuvem', caiu)
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setenv('SOLIS_TOKEN', 'um-token-de-teste-bem-comprido-123')
    c = TestClient(main.app, headers={'Authorization': 'Bearer um-token-de-teste-bem-comprido-123'})
    assert c.post('/voz', content=wav()).json()['texto'] == 'Minha senha do banco é 1234.'


def _mandar(c, texto, **extra):
    conversa = c.post('/conversas').json()['id']
    r = c.post(f'/conversas/{conversa}/mensagens', json={'texto': texto, **extra})
    return conversa, [json.loads(l) for l in r.text.splitlines() if l]


def test_mensagem_com_cadeado_e_guardada_selada_e_a_resposta_tambem(monkeypatch):
    async def nao(*a, **k):
        raise AssertionError('chamou um cérebro')
    monkeypatch.setattr(roteador, 'responder', nao)
    conversa, linhas = _mandar(TestClient(main.app), 'Que horas são?', privada=True)
    assert ''.join(l.get('texto', '') for l in linhas).startswith('São ')  # o que sai em código continua
    pessoa, solis = banco.mensagens(conversa)
    assert pessoa['privada'] and solis['privada']
    # E o aprendizado sabe que a mensagem é privada (o cadeado, não as palavras).
    assert memoria._mensagem_privada(pessoa['id'])


def test_mensagem_com_cadeado_so_vai_pro_local(monkeypatch):
    ordens = []

    async def responder(ordem, *a, **k):
        ordens.append(list(ordem))
        raise roteador.NinguemRespondeu(ordem, {})
    monkeypatch.setattr(roteador, 'responder', responder)
    _, linhas = _mandar(TestClient(main.app), '/groq me conta da consulta de ontem', privada=True)
    assert ordens == [['local']]  # nem o comando na frente leva pra nuvem
    assert any(l.get('erro') == 'ollama_indisponivel' for l in linhas)


def test_no_servidor_o_privado_diz_que_so_o_pc_responde(monkeypatch):
    async def responder(ordem, *a, **k):
        raise roteador.NinguemRespondeu(ordem, {})
    monkeypatch.setattr(roteador, 'responder', responder)
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setenv('SOLIS_TOKEN', 'um-token-de-teste-bem-comprido-123')
    c = TestClient(main.app, headers={'Authorization': 'Bearer um-token-de-teste-bem-comprido-123'})
    _, linhas = _mandar(c, 'me conta da consulta de ontem', privada=True)
    assert any(l.get('erro') == 'privado_sem_local' for l in linhas)
