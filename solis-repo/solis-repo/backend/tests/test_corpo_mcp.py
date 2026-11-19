"""Os servidores MCP do Matheus no corpo do Solis (19/11/2026): as mesmas
ferramentas do Claude pra todo cérebro — o que só lê é livre, o resto pede o
cartão de conector. Com um servidor MCP de verdade (tests/dados/mcp_teste.py,
por stdio) e a conferida de verdade; o cérebro é simulado."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

from solis import agente, apis, banco, cofre, corpo, servidores_mcp

SERVIDOR = Path(__file__).with_name('dados') / 'mcp_teste.py'


class Gravador:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


@pytest.fixture
def caderno(tmp_path, monkeypatch):
    arquivo = tmp_path / 'caderno.txt'
    config = {'tipo': 'comando', 'url': '', 'comando': [sys.executable, str(SERVIDOR)],
              'env': {'CADERNO': str(arquivo)}}
    monkeypatch.setattr(servidores_mcp, '_do_claude', lambda: {'teste': config, 'solis': config})
    monkeypatch.setattr(servidores_mcp, '_do_codex', lambda: {})
    # A conferida de verdade: sobe o servidor e guarda as ferramentas com o esquema.
    r = asyncio.run(servidores_mcp.conferir('teste'))
    assert r['erro'] is None and r['total'] == 2
    return arquivo


def test_a_conferida_guarda_a_descricao_e_o_esquema(caderno):
    lista = {t['nome']: t for t in servidores_mcp._cache()['teste']['lista']}
    assert lista['ver_saldo']['so_le'] and not lista['anotar']['so_le']
    assert 'saldo' in lista['ver_saldo']['descricao'] and 'conta' in lista['ver_saldo']['esquema']['properties']


def test_as_do_servidor_vao_pro_corpo_e_a_da_memoria_do_solis_nao(caderno):
    nomes = [s['function']['name'] for s in asyncio.run(corpo.Corpo(1, Gravador(), navegar=False).especificacoes())]
    assert 'mcp__teste__ver_saldo' in nomes and 'mcp__teste__anotar' in nomes
    assert not any(n.startswith('mcp__solis__') and 'memoria' in n and n != 'mcp__solis__buscar_memoria' for n in nomes)


def test_o_que_so_le_e_livre_e_roda_no_servidor(caderno):
    g = Gravador()
    saida = asyncio.run(corpo.Corpo(1, g, navegar=False).rodar('mcp__teste__ver_saldo', {'conta': '42'}))
    assert 'R$ 1.234,56' in saida and '<<<INÍCIO DA FERRAMENTA>>>' in saida
    assert not any(e == 'aprovacao' for e, _ in g.lista)
    assert [d['ok'] for e, d in g.lista if e == 'ferramenta'] == [True]


def test_o_que_muda_pede_o_cartao_de_conector_e_so_roda_aprovado(caderno):
    g = Gravador()
    c = corpo.Corpo(2, g, navegar=False, cerebro='groq')

    async def tudo(aprovar):
        tarefa = asyncio.ensure_future(c.rodar('mcp__teste__anotar', {'texto': 'comprar pão'}))
        while sum(1 for e, _ in g.lista if e == 'aprovacao') < (1 if aprovar is False else 2):
            await asyncio.sleep(0.01)
        pedido = [d for e, d in g.lista if e == 'aprovacao'][-1]
        agente.responder_aprovacao(pedido['id'], aprovar)
        return pedido, await tarefa

    pedido, saida = asyncio.run(tudo(False))
    assert pedido['resumo'] == 'Usar o teste: anotar' and '"comprar pão"' in pedido['entrada']
    assert pedido['cerebro'] == 'groq' and saida == 'O Matheus recusou.' and not caderno.exists()
    pedido, saida = asyncio.run(tudo(True))
    assert 'Anotado.' in saida and caderno.read_text(encoding='utf-8') == 'comprar pão\n' and c.agiu


def test_a_groq_simulada_usa_a_ferramenta_do_servidor(caderno):
    banco.guardar_ajuste('chave:groq', cofre.selar('gsk_x'))
    banco.guardar_ajuste('modelo:groq', 'openai/gpt-oss-120b')
    pedidos = []

    def sse(*eventos):
        return '\n\n'.join([f'data: {json.dumps(e)}' for e in eventos] + ['data: [DONE]']) + '\n\n'

    def rota(req):
        pedidos.append(json.loads(req.content))
        if len(pedidos) == 1:
            corpo_ = sse({'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'c1', 'type': 'function',
                         'function': {'name': 'mcp__teste__ver_saldo', 'arguments': '{"conta": "7"}'}}]}}]})
        else:
            corpo_ = sse({'choices': [{'delta': {'content': 'O saldo é R$ 1.234,56.'}}]})
        return httpx.Response(200, text=corpo_, headers={'content-type': 'text/event-stream'})

    g = Gravador()

    async def ir():
        fluxo = apis.responder('groq', 'sis', 'meu saldo da conta 7?', g, httpx.MockTransport(rota),
                               corpo=corpo.Corpo(1, g, navegar=False))
        return ''.join([p async for p in fluxo])
    assert asyncio.run(ir()) == 'O saldo é R$ 1.234,56.'
    assert 'R$ 1.234,56' in pedidos[1]['messages'][-1]['content']


def test_servidor_que_cai_vira_texto_pro_modelo(caderno, monkeypatch):
    async def caiu(c, f, a):
        return 'O servidor não respondeu: demorou demais pra responder', False
    monkeypatch.setattr(servidores_mcp, 'chamar', caiu)
    g = Gravador()
    saida = asyncio.run(corpo.Corpo(1, g, navegar=False).rodar('mcp__teste__ver_saldo', {'conta': '1'}))
    assert saida.startswith('O servidor não respondeu') and [d['ok'] for e, d in g.lista if e == 'ferramenta'] == [False]


def test_desligado_ou_sem_conferida_nao_vai(caderno, monkeypatch):
    c = corpo.Corpo(1, Gravador(), navegar=False)
    c.mcp = False
    assert not any('mcp__teste__' in s['function']['name'] for s in asyncio.run(c.especificacoes()))
    banco.guardar_ajuste('mcp_ferramentas', {})
    assert servidores_mcp.do_corpo() == []


def test_pedido_que_cita_o_servidor_ja_vai_com_o_corpo(caderno, monkeypatch):
    """Medido com a Groq: sem as ferramentas, "anota no caderno" voltou "Anotado!" sem anotar."""
    from solis import cerebros, roteador
    vistos = []

    async def abrir(nome, sistema, prompt, etapas=None, sessao=None, rapido=False, corpo=None):
        vistos.append((nome, corpo is not None, sistema))

        async def gen():
            yield 'ok'
        return gen()
    monkeypatch.setattr(cerebros, 'abrir', abrir)

    async def ir(msg):
        fluxo, _ = await roteador.responder(['groq'], '', 1, [], [], [], None, msg)
        return ''.join([p async for p in fluxo])
    asyncio.run(ir('Anota no Teste: comprar pão.'))
    assert vistos[-1][:2] == ('groq', True)
    # Sem citar o servidor, vai leve, mas sabendo que ele existe.
    asyncio.run(ir('Qual a capital da Austrália?'))
    assert vistos[-1][:2] == ('groq', False) and 'servidores MCP): teste' in vistos[-1][2]
