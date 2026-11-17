"""Quem transcreve a escuta (transcricao.py), online primeiro: o "Solis" conferido
aqui pelo Whisper pequeno; o pedido na Groq; o privado e o offline no turbo daqui."""
import asyncio

import httpx
import pytest

from solis import banco, cofre, conexoes, transcricao, voz


@pytest.fixture(autouse=True)
def caminho_limpo(monkeypatch, tmp_path):
    monkeypatch.setattr(transcricao, '_fora_ate', 0.0)
    monkeypatch.setattr(transcricao, 'pequeno_disponivel', lambda: True)
    feitos = {'pequeno': [], 'local': [], 'nuvem': []}

    async def pequeno(audio):
        feitos['pequeno'].append(audio)
        return feitos.get('ouve_pequeno', '')

    async def local(audio):
        feitos['local'].append(audio)
        return 'texto do turbo local'
    monkeypatch.setattr(transcricao, 'palavra', pequeno)
    monkeypatch.setattr(transcricao, '_local', local)
    return feitos


def com_groq():
    banco.guardar_ajuste('chave:groq', cofre.selar('gsk_x'))


def nuvem_falsa(monkeypatch, feitos, rota):
    def responder(req):
        feitos['nuvem'].append(req)
        return rota(req)
    cliente = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    monkeypatch.setattr(conexoes, 'cliente', lambda nome: cliente)


def ok(texto):
    return lambda req: httpx.Response(200, json={'text': texto})


def escuta(tipo):
    return asyncio.run(transcricao.escuta(tipo, b'RIFFwav'))


def test_sem_a_chave_da_groq_tudo_fica_no_computador(caminho_limpo):
    assert escuta('frase') == 'texto do turbo local'
    assert caminho_limpo['local'] and not caminho_limpo['pequeno']


def test_fala_sem_solis_nunca_vai_pra_nuvem(monkeypatch, caminho_limpo):
    com_groq()
    nuvem_falsa(monkeypatch, caminho_limpo, ok('nao devia'))
    caminho_limpo['ouve_pequeno'] = 'O sol está forte hoje.'
    assert escuta('frase') == 'O sol está forte hoje.'
    assert caminho_limpo['nuvem'] == [] and caminho_limpo['local'] == []


def test_com_solis_o_pedido_vem_da_groq_so_com_o_vocabulario_fixo(monkeypatch, caminho_limpo):
    com_groq()
    banco.adicionar_memoria('Trabalha na Zentrix com a Fernanda.', 'Trabalho', False, None)
    nuvem_falsa(monkeypatch, caminho_limpo, ok('Solis, que horas são?'))
    caminho_limpo['ouve_pequeno'] = 'Solis, que oras são.'
    assert escuta('frase') == 'Solis, que horas são?'
    [req] = caminho_limpo['nuvem']
    corpo = req.content.decode('latin-1')
    assert 'whisper-large-v3' in corpo and 'Solis' in corpo
    # Os nomes das memórias ajudam o Whisper daqui, mas não saem do computador.
    assert 'Zentrix' not in corpo and 'Fernanda' not in corpo


def test_o_pedido_privado_fica_no_computador(monkeypatch, caminho_limpo):
    com_groq()
    nuvem_falsa(monkeypatch, caminho_limpo, ok('nao devia'))
    caminho_limpo['ouve_pequeno'] = 'Solis, isso é privado: minha senha do banco é tal.'
    assert escuta('frase') == 'texto do turbo local'
    assert caminho_limpo['nuvem'] == []
    caminho_limpo['ouve_pequeno'] = 'isso é privado, anota meu exame'
    assert escuta('comando') == 'texto do turbo local' and caminho_limpo['nuvem'] == []


def test_a_groq_falhando_cai_pro_turbo_e_fica_de_lado(monkeypatch, caminho_limpo):
    com_groq()
    nuvem_falsa(monkeypatch, caminho_limpo, lambda req: httpx.Response(500))
    caminho_limpo['ouve_pequeno'] = 'Solis, que horas são?'
    assert escuta('frase') == 'texto do turbo local'
    assert not transcricao.online()
    # De lado: o próximo nem tenta a nuvem, vai direto pro turbo.
    antes = len(caminho_limpo['nuvem'])
    assert escuta('comando') == 'texto do turbo local' and len(caminho_limpo['nuvem']) == antes


def test_o_limite_da_groq_espera_o_que_ela_disse(monkeypatch, caminho_limpo):
    com_groq()
    nuvem_falsa(monkeypatch, caminho_limpo, lambda req: httpx.Response(429, headers={'retry-after': '7'}))
    caminho_limpo['ouve_pequeno'] = 'Solis, que horas são?'
    escuta('frase')
    assert 5 < transcricao._fora_ate - transcricao.time.monotonic() <= 7


def test_a_palavra_e_do_pequeno_se_a_nuvem_nao_ouvir_solis(monkeypatch, caminho_limpo):
    com_groq()
    nuvem_falsa(monkeypatch, caminho_limpo, ok('Que horas são?'))
    caminho_limpo['ouve_pequeno'] = 'Solis, que horas são?'
    assert escuta('previa') == 'Solis, que horas são?'


def test_o_pedido_depois_da_palavra_vai_pra_groq(monkeypatch, caminho_limpo):
    com_groq()
    nuvem_falsa(monkeypatch, caminho_limpo, ok('Me lembra de pagar a luz.'))
    caminho_limpo['ouve_pequeno'] = 'me lembra de pagar a lus'
    assert escuta('rascunho') == 'Me lembra de pagar a luz.'
    assert escuta('comando') == 'Me lembra de pagar a luz.'


def test_chamada_torta_no_pequeno_a_nuvem_decide(monkeypatch, caminho_limpo):
    """17/11/2026, a gravação do Matheus: "Ei Solis, quanto é..." virou "É isso aí,
    Solis" no pequeno (3 palavras antes do nome). Quem decide é a nuvem."""
    com_groq()
    nuvem_falsa(monkeypatch, caminho_limpo, ok('Ei, Solis, quanto é quinze vezes três?'))
    caminho_limpo['ouve_pequeno'] = 'É isso aí, Solis.'
    assert escuta('frase') == 'Ei, Solis, quanto é quinze vezes três?'
    # E se a nuvem também não ouvir a chamada, não acorda (vale o que o pequeno ouviu).
    nuvem_falsa(monkeypatch, caminho_limpo, ok('Me passa o Solis aí.'))
    caminho_limpo['ouve_pequeno'] = 'Me passa o Solis aí.'
    assert escuta('frase') == 'Me passa o Solis aí.'
