"""Busca por significado e migração do banco, com embeddings falsos.

Os vetores falsos dão uma dimensão por palavra-chave: textos sobre o mesmo
assunto ficam perto, assuntos diferentes ficam ortogonais. É o comportamento
que importa testar — quem escolhe o quê — sem depender de um modelo de verdade.
"""
import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from solis import banco, busca, main, memoria, ollama, resumo

ASSUNTOS = ['syngenta', 'nfe', 'chá', 'violão', 'python']


def vetor(texto: str) -> list[float]:
    t = texto.lower()
    # A última dimensão é um fundo fraco comum a tudo: nenhum vetor é zero, e
    # assuntos diferentes dão similaridade baixa mas não nula, como na vida real.
    return [float(t.count(a)) for a in ASSUNTOS] + [0.1]


@pytest.fixture
def embeddings_falsos(monkeypatch):
    chamadas = []

    async def falso(modelo, textos):
        chamadas.append(textos)
        return [vetor(t) for t in textos]
    monkeypatch.setattr(ollama, 'embeddings', falso)
    return chamadas


def conversa_com(*textos: str) -> int:
    cid = banco.nova_conversa()
    for i, t in enumerate(textos):
        banco.adicionar(cid, 'pessoa' if i % 2 == 0 else 'solis', t)
    return cid


def test_migracao_leva_banco_antigo_pra_versao_nova(tmp_path):
    antigo = tmp_path / 'antigo.db'
    c = sqlite3.connect(antigo)
    c.executescript(banco.ESQUEMA)  # o esquema de antes da migração 1, versão 0
    c.execute("INSERT INTO memorias (texto, tema, criada) VALUES ('Trabalha na Syngenta.', 'Trabalho', 'x')")
    c.commit()
    c.close()

    banco.usar(antigo)
    [m] = banco.memorias()
    assert (m['texto'], m['privada']) == ('Trabalha na Syngenta.', False)
    assert banco._con().execute('PRAGMA user_version').fetchone()[0] == len(banco.MIGRACOES)
    banco.usar(antigo)  # reabrir não roda a migração de novo
    assert len(banco.memorias()) == 1


def test_indexa_o_que_falta_e_so_uma_vez(embeddings_falsos):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    conversa_com('oi', 'olá')
    assert asyncio.run(busca.indexar_pendentes()) == 3
    assert asyncio.run(busca.indexar_pendentes()) == 0
    # E com o prefixo que o nomic espera pra documento.
    assert all(t.startswith(busca.DOCUMENTO) for t in embeddings_falsos[0])


def test_sem_embeddings_indexar_so_adia():
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    assert asyncio.run(busca.indexar_pendentes()) == 0
    assert len(banco.sem_vetor('memoria', 10)) == 1


def test_traz_trecho_de_conversa_antiga_e_nao_da_aberta(embeddings_falsos):
    antiga = conversa_com('vou fazer o sistema de nfe da loja', 'Boa, a nfe precisa de certificado A1.')
    conversa_com('gosto de violão', 'Que legal.')
    aberta = conversa_com('e a nfe, como faço?')
    asyncio.run(busca.indexar_pendentes())

    _, trechos = asyncio.run(busca.contexto('e a nfe, como faço?', aberta))
    assert {t['conversa'] for t in trechos} == {antiga}
    assert any('certificado A1' in t['texto'] for t in trechos)
    assert not any('violão' in t['texto'] for t in trechos)  # abaixo do piso


def test_poucas_memorias_vao_todas(embeddings_falsos):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    banco.adicionar_memoria('Gosta de chá.', 'Preferências', False, None)
    asyncio.run(busca.indexar_pendentes())
    memorias, _ = asyncio.run(busca.contexto('toco violão', conversa_com('toco violão')))
    assert len(memorias) == 2


def test_muitas_memorias_vao_as_parecidas_e_as_recentes(embeddings_falsos):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)  # a mais antiga
    for i in range(40):
        banco.adicionar_memoria(f'Estudou python no dia {i}.', 'Estudos', False, None)
    asyncio.run(busca.indexar_pendentes())

    memorias, _ = asyncio.run(busca.contexto('o que faço na syngenta?', conversa_com('x')))
    textos = [m['texto'] for m in memorias]
    assert 'Trabalha na Syngenta.' in textos           # velha, mas é a que importa
    assert 'Estudou python no dia 39.' in textos       # recente
    assert len(memorias) <= busca.MEMORIAS_PARECIDAS + busca.MEMORIAS_RECENTES


def test_sem_embeddings_volta_pras_recentes():
    for i in range(50):
        banco.adicionar_memoria(f'Fato {i}.', 'Geral', False, None)
    memorias, trechos = asyncio.run(busca.contexto('qualquer coisa', conversa_com('x')))
    assert memorias[0]['texto'] == 'Fato 49.' and trechos == []
    assert len(memorias) == busca.TODAS_ATE + busca.MEMORIAS_RECENTES


def test_esquecer_memoria_apaga_o_vetor(embeddings_falsos):
    banco.adicionar_memoria('Gosta de chá.', 'Preferências', False, None)
    asyncio.run(busca.indexar_pendentes())
    [m] = banco.memorias()
    banco.apagar_memoria(m['id'])
    assert banco.vetores('memoria') == []


def test_trechos_vao_no_prompt_com_data_e_autor():
    s = ollama.sistema(
        [{'texto': 'Trabalha na Syngenta.'}],
        [
            {'criada': '2026-03-14T10:00:00+00:00', 'papel': 'pessoa', 'texto': 'vou fazer a nfe'},
            {'criada': '2026-03-14T10:01:00+00:00', 'papel': 'solis', 'texto': 'Precisa de:\n- certificado\n- XML'},
        ],
    )
    assert '- Trabalha na Syngenta.' in s
    assert '- [2026-03-14] Matheus: vou fazer a nfe' in s
    # A lista da resposta antiga não pode virar itens soltos no prompt.
    assert '- [2026-03-14] Solis: Precisa de: - certificado - XML' in s
    assert '\n- certificado' not in s


def test_so_o_fim_da_conversa_vai_inteiro(monkeypatch):
    recebido = []

    async def falso(modelo, mensagens, memorias=None, trechos=None, resumo=None):
        recebido.append(mensagens)

        async def gen():
            yield 'ok'
        return gen()

    async def nada(*_):
        pass
    monkeypatch.setattr(ollama, 'conversar', falso)
    monkeypatch.setattr(memoria, 'aprender', nada)

    cid = conversa_com(*[f'mensagem {i}' for i in range(30)])
    TestClient(main.app).post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'a última'})
    # Sem resumo ainda (o modelo de resumo não respondeu): vai o teto, não tudo.
    assert len(recebido[0]) == resumo.JANELA + resumo.LOTE
    assert recebido[0][-1]['texto'] == 'a última'


def test_comeco_da_propria_conversa_volta_como_trecho_depois_de_resumido(embeddings_falsos):
    cid = conversa_com('a nfe precisa de certificado A1', 'Anotado.', 'mudando de assunto')
    asyncio.run(busca.indexar_pendentes())
    primeira, segunda, _ = banco.mensagens(cid)

    # Sem resumo, a conversa inteira já está no histórico: nada a trazer.
    _, trechos = asyncio.run(busca.contexto('e a nfe?', cid))
    assert trechos == []
    # Com as duas primeiras resumidas, o trecho exato delas pode voltar.
    _, trechos = asyncio.run(busca.contexto('e a nfe?', cid, desde=segunda['id']))
    assert [t['id'] for t in trechos] == [primeira['id']]


def test_extrator_recebe_as_memorias_do_mesmo_assunto(embeddings_falsos):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    for i in range(20):
        banco.adicionar_memoria(f'Estudou python no dia {i}.', 'Estudos', False, None)
    asyncio.run(busca.indexar_pendentes())
    banco.adicionar_memoria('Gosta de chá.', 'Preferências', False, None)  # ainda sem vetor

    parecidas = asyncio.run(busca.memorias_parecidas('saí da syngenta', 3))
    assert parecidas[0]['texto'] == 'Trabalha na Syngenta.'
    todas = asyncio.run(busca.memorias_parecidas('saí da syngenta', 30))
    assert 'Gosta de chá.' in [m['texto'] for m in todas]  # a sem vetor não some
