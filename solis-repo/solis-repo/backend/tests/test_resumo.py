"""Conversa longa: o começo vira resumo, sem buraco entre o resumo e o fim."""
import asyncio

from solis import banco, ollama, resumo


def conversa_de(n: int) -> int:
    cid = banco.nova_conversa()
    for i in range(n):
        banco.adicionar(cid, 'pessoa' if i % 2 == 0 else 'solis', f'mensagem {i}')
    return cid


def resume_com(monkeypatch, texto='- resumo'):
    pedidos = []

    async def falso(modelo, instrucao, pedido):
        pedidos.append(pedido)
        return texto
    monkeypatch.setattr(ollama, 'responder_texto', falso)
    return pedidos


def test_conversa_curta_nao_resume(monkeypatch):
    pedidos = resume_com(monkeypatch)
    cid = conversa_de(resumo.JANELA + resumo.LOTE)
    asyncio.run(resumo.resumir('m', cid))
    assert pedidos == [] and banco.resumo(cid) == (None, 0)


def test_passou_do_lote_resume_as_velhas_e_deixa_a_janela(monkeypatch):
    pedidos = resume_com(monkeypatch, '- decidiram usar SQLite')
    cid = conversa_de(resumo.JANELA + resumo.LOTE + 1)
    asyncio.run(resumo.resumir('m', cid))

    texto, mensagens, ate = resumo.para_o_modelo(cid)
    assert texto == '- decidiram usar SQLite'
    assert len(mensagens) == resumo.JANELA
    # Sem buraco: a primeira que vai inteira é a seguinte à última resumida.
    assert mensagens[0]['id'] == ate + 1
    # 31 mensagens: as 11 mais velhas (0 a 10) vão pro resumo, as 20 seguintes não.
    assert 'mensagem 0' in pedidos[0]
    assert pedidos[0].endswith(f'mensagem {resumo.LOTE}')
    assert f'mensagem {resumo.LOTE + 1}' not in pedidos[0]


def test_o_resumo_seguinte_parte_do_anterior(monkeypatch):
    pedidos = resume_com(monkeypatch, '- primeiro')
    cid = conversa_de(resumo.JANELA + resumo.LOTE + 1)
    asyncio.run(resumo.resumir('m', cid))
    for i in range(resumo.LOTE + 1):
        banco.adicionar(cid, 'pessoa', f'nova {i}')
    asyncio.run(resumo.resumir('m', cid))
    assert len(pedidos) == 2 and '- primeiro' in pedidos[1]
    assert 'mensagem 0' not in pedidos[1]  # o que já está no resumo não volta


def test_resumo_falhando_nao_deixa_o_historico_crescer_sem_fim():
    cid = conversa_de(100)
    asyncio.run(resumo.resumir('m', cid))  # o conftest deixa o modelo "indisponível"
    texto, mensagens, _ = resumo.para_o_modelo(cid)
    assert texto is None and len(mensagens) == resumo.JANELA + resumo.LOTE


def test_resumo_vai_no_prompt():
    s = ollama.sistema([], None, '- decidiram usar SQLite')
    assert 'Resumo do começo desta conversa' in s and '- decidiram usar SQLite' in s
