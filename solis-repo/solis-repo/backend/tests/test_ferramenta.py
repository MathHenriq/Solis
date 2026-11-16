"""Quem não tem ferramenta não finge que agiu (16/11/2026: pela voz, a Groq dizia
"Música desligada." sem nada ter acontecido): responde a marca e o pedido passa
pra quem tem as ferramentas — e, com o aprendizado fora, ninguém diz que guardou."""
import asyncio

import pytest

from solis import cerebros, ollama, roteador


def falsos(monkeypatch, respostas: dict, sistemas: dict):
    """`respostas`: nome -> lista de pedaços da resposta."""
    async def abrir(nome, sistema, prompt, etapas=None, sessao=None, **_):
        sistemas[nome] = sistema

        async def gen():
            for p in respostas[nome]:
                yield p
        return gen()
    monkeypatch.setattr(cerebros, 'abrir', abrir)


def responder(ordem):
    async def rodar():
        fluxo, quem = await roteador.responder(ordem, '', 1, [], [], [], None, 'desliga a música')
        return ''.join([p async for p in fluxo]), quem
    return asyncio.run(rodar())


def test_a_marca_passa_o_pedido_pro_claude_pulando_os_outros_de_api(monkeypatch):
    sistemas = {}
    # A marca vem quebrada em pedaços, como no streaming.
    falsos(monkeypatch, {'groq': ['[FERR', 'AMENTA]'], 'gemini': ['Música desligada.'],
                         'claude': ['Pausei a ', 'música.']}, sistemas)
    assert responder(['groq', 'gemini', 'claude']) == ('Pausei a música.', 'claude')
    # O Gemini nem foi perguntado: diria o mesmo que a Groq.
    assert set(sistemas) == {'groq', 'claude'}
    assert roteador.PASSA in sistemas['groq'] and roteador.PASSA not in sistemas['claude']


@pytest.mark.parametrize('pedacos', [['**[FERRAMENTA]**'], [' [ferramenta]'], ['[', 'FERRAMENTA', ']']])
def test_a_marca_com_enfeite_tambem_passa(monkeypatch, pedacos):
    falsos(monkeypatch, {'groq': pedacos, 'claude': ['ok']}, {})
    assert responder(['groq', 'claude']) == ('ok', 'claude')


@pytest.mark.parametrize('pedacos', [['Canberra.'], ['[1] Canberra'], ['[F', 'oi um engano]'], ['Ferramenta é isso.']])
def test_resposta_normal_sai_inteira(monkeypatch, pedacos):
    falsos(monkeypatch, {'groq': pedacos, 'claude': ['não devia']}, {})
    assert responder(['groq', 'claude']) == (''.join(pedacos), 'groq')


def test_sem_quem_tenha_ferramenta_o_de_api_diz_que_nao_consegue(monkeypatch):
    sistemas = {}
    falsos(monkeypatch, {'groq': ['Não consigo desligar a música agora.']}, sistemas)
    responder(['groq'])
    assert roteador.PASSA not in sistemas['groq'] and 'não consegue fazer agora' in sistemas['groq']
    assert 'Nunca diga que fez' in sistemas['groq']


def test_a_marca_sem_ninguem_depois_e_queda(monkeypatch):
    falsos(monkeypatch, {'groq': ['[FERRAMENTA]'], 'claude': ['x']}, {})
    monkeypatch.setattr(roteador, 'notas_do_cerebro', lambda nome, depois: '')
    with pytest.raises(roteador.NinguemRespondeu):
        responder(['groq', 'gemini'])


def test_com_o_aprendizado_fora_ninguem_diz_que_guardou(monkeypatch):
    sistemas = {}
    falsos(monkeypatch, {'groq': ['[FERRAMENTA]'], 'claude': ['ok']}, sistemas)
    monkeypatch.setattr(ollama, '_fora', True)
    responder(['groq', 'claude'])
    assert 'Nunca diga que guardou' in sistemas['groq']
    assert 'mcp__solis__' in sistemas['claude'] and 'não diga que guardou' in sistemas['claude']
    sistemas.clear()
    monkeypatch.setattr(ollama, '_fora', False)
    responder(['groq', 'claude'])
    assert 'aprendizado do Solis está desligado' not in sistemas['groq']
