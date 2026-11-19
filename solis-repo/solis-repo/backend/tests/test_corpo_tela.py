"""A tela no corpo do Solis (corpo.py): pra quem não vê imagem (a Groq e os de
API), o texto da tela com a posição de cada linha, e as mesmas ações do Claude
com o mesmo cartão. Numa tela inventada: nada aqui olha nem mexe na tela de
verdade."""
import asyncio

import pytest

from solis import agente, corpo, ocr, tela


class Gravador:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


class Imagem:
    width, height = 2732, 1536  # o dobro do print: escala 0,5


@pytest.fixture
def tela_falsa(monkeypatch):
    feitas = []
    monkeypatch.setattr(tela, 'ligada', lambda: True)
    monkeypatch.setattr(tela, '_print', lambda: Imagem())
    monkeypatch.setattr(tela, '_png', lambda imagem: b'png')
    monkeypatch.setattr(tela, 'escala', lambda: 0.5)
    monkeypatch.setattr(tela, 'janela_ativa', lambda: ('notepad.exe', 'Sem título - Bloco de Notas'))
    monkeypatch.setattr(tela, 'programa_alvo', lambda acao, e: ('notepad.exe', 'Sem título - Bloco de Notas'))
    monkeypatch.setattr(tela, 'imagem_do_cartao', lambda acao, e: 'data:image/png;base64,eA==')
    monkeypatch.setattr(tela, 'DEPOIS_S', 0)

    async def linhas(png):
        return [(80, 60, 400, 26, 'Arquivo Editar Exibir'), (2260, 1420, 100, 26, 'Salvar')]
    monkeypatch.setattr(ocr, 'linhas_com_posicao', linhas)
    monkeypatch.setattr(tela, 'clicar', lambda x, y, botao='esquerdo', duplo=False: feitas.append(('clicar', x, y)))
    monkeypatch.setattr(tela, 'digitar', lambda texto: feitas.append(('digitar', texto)))
    return feitas


def test_tela_ler_da_o_texto_com_o_centro_nas_coordenadas_do_print(tela_falsa):
    c = corpo.Corpo(1, Gravador(), navegar=False)
    texto = asyncio.run(c.rodar('mcp__solis__tela_ler', {}))
    assert texto.startswith('Tela 1366x768; na frente: Sem título - Bloco de Notas.')
    # (2260 + 100/2) * 0,5 = 1155; (1420 + 26/2) * 0,5 = 716,5 → 716 (arredonda pro par)
    assert '[1155,716] Salvar' in texto and '[140,36] Arquivo Editar Exibir' in texto
    assert not any(e == 'aprovacao' for e, _ in c.etapas.lista)  # ler é livre


def test_clicar_pede_o_mesmo_cartao_do_claude_e_volta_a_tela_de_depois(tela_falsa):
    g = Gravador()
    c = corpo.Corpo(5, g, navegar=False)

    async def tudo():
        tarefa = asyncio.ensure_future(c.rodar('mcp__solis__tela_clicar', {'x': 1155, 'y': 716}))
        while not any(e == 'aprovacao' for e, _ in g.lista):
            await asyncio.sleep(0.01)
        pedido = next(d for e, d in g.lista if e == 'aprovacao')
        assert pedido['ferramenta'] == 'mcp__solis__tela_clicar' and pedido['site'] == 'Sem título - Bloco de Notas'
        assert pedido['imagem'].startswith('data:image/png')  # o Matheus vê o print marcado
        agente.responder_aprovacao(pedido['id'], True)
        return await tarefa

    saida = asyncio.run(tudo())
    assert tela_falsa == [('clicar', 1155.0, 716.0)]
    assert saida.startswith('Feito. A tela agora:') and 'Salvar' in saida
    assert c.agiu


def test_recusado_nao_clica(tela_falsa):
    g = Gravador()
    c = corpo.Corpo(6, g, navegar=False)

    async def tudo():
        tarefa = asyncio.ensure_future(c.rodar('mcp__solis__tela_digitar', {'texto': 'oi'}))
        while not any(e == 'aprovacao' for e, _ in g.lista):
            await asyncio.sleep(0.01)
        agente.responder_aprovacao(next(d for e, d in g.lista if e == 'aprovacao')['id'], False)
        return await tarefa

    assert asyncio.run(tudo()) == 'O Matheus recusou.'
    assert tela_falsa == []


def test_na_janela_do_solis_nem_pede(tela_falsa, monkeypatch):
    monkeypatch.setattr(tela, 'programa_alvo', lambda acao, e: ('solis.exe', 'Solis'))
    g = Gravador()
    saida = asyncio.run(corpo.Corpo(7, g, navegar=False).rodar('mcp__solis__tela_clicar', {'x': 10, 'y': 10}))
    assert 'janela do próprio Solis' in saida
    assert tela_falsa == [] and not any(e == 'aprovacao' for e, _ in g.lista)


def test_com_a_tela_desligada_nao_vai(monkeypatch):
    monkeypatch.setattr(tela, 'ligada', lambda: False)
    c = corpo.Corpo(1, Gravador(), navegar=False)
    nomes = [s['function']['name'] for s in asyncio.run(c.especificacoes())]
    assert not any('tela_' in n for n in nomes)
    assert 'não existe' in asyncio.run(c.rodar('mcp__solis__tela_ler', {}))


def test_ligada_as_seis_vao_e_o_sistema_fala_da_tela(tela_falsa):
    from solis import roteador
    c = corpo.Corpo(1, Gravador(), navegar=False)
    nomes = {s['function']['name'] for s in asyncio.run(c.especificacoes())}
    assert {f'mcp__solis__tela_{a}' for a in ('ler', 'clicar', 'digitar', 'tecla', 'rolar', 'mover')} <= nomes
    s = roteador.sistema_para('groq', False, True, True, True, True) + roteador.notas_do_cerebro(
        'groq', ['claude'], False, True, True, True, True)
    assert 'tela_ler' in s and 'não controla a tela' not in s


def test_linhas_do_ocr_com_posicao(monkeypatch):
    async def windows(png, posicoes=False):
        assert posicoes
        return '10,20,30,8\tOlá\nlixo sem caixa\n5,5,1,1\t  \n100,200,50,10\tSalvar\n'
    monkeypatch.setattr(ocr, 'windows', windows)
    assert asyncio.run(ocr.linhas_com_posicao(b'')) == [(10, 20, 30, 8, 'Olá'), (100, 200, 50, 10, 'Salvar')]
