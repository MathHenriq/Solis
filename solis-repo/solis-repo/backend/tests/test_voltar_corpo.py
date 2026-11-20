"""Voltar atrás das edições dos outros cérebros (a Groq, o Gemini... pelo corpo):
o Solis guarda o arquivo antes da primeira mudança de cada fala (editar.py,
banco.copias_volta) e o mesmo botão do Claude volta. A Groq é simulada."""
import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from solis import agente, apis, banco, cofre, corpo, main


class Gravador:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


def sse(*eventos):
    return '\n\n'.join([f'data: {json.dumps(e)}' for e in eventos] + ['data: [DONE]']) + '\n\n'


def resposta(*eventos):
    return httpx.Response(200, text=sse(*eventos), headers={'content-type': 'text/event-stream'})


def a_groq_faz(conversa, pedidos):
    """A Groq (simulada) pede as ferramentas; os cartões são aprovados."""
    banco.guardar_ajuste('chave:groq', cofre.selar('gsk_x'))
    banco.guardar_ajuste('modelo:groq', 'openai/gpt-oss-120b')
    vistos = []

    def rota(req):
        vistos.append(1)
        n = len(vistos)
        if n <= len(pedidos):
            nome, args = pedidos[n - 1]
            return resposta({'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': f'c{n}', 'type': 'function',
                                                                       'function': {'name': nome,
                                                                                    'arguments': json.dumps(args)}}]}}]})
        return resposta({'choices': [{'delta': {'content': 'Pronto.'}}]})

    g = Gravador()

    async def tudo():
        tarefa = asyncio.ensure_future(_juntar(apis.responder('groq', 'sis', 'mexe', g, httpx.MockTransport(rota),
                                                              corpo=corpo.Corpo(conversa, g, navegar=False,
                                                                                cerebro='groq'))))
        respondidos = 0
        while not tarefa.done():
            cartoes = [d for e, d in g.lista if e == 'aprovacao']
            if len(cartoes) > respondidos:
                agente.responder_aprovacao(cartoes[respondidos]['id'], True)
                respondidos += 1
            await asyncio.sleep(0.01)
        return await tarefa

    return asyncio.run(tudo())


async def _juntar(fluxo):
    return ''.join([p async for p in fluxo])


def test_a_groq_edita_e_cria_e_o_botao_volta_tudo(tmp_path):
    (tmp_path / 'conta.py').write_text('def soma(a, b):\n    return a + b\n', encoding='utf-8')
    c = banco.nova_conversa()
    banco.guardar_projeto(c, str(tmp_path), 'pedir')
    primeira = banco.adicionar(c, 'pessoa', 'troca o nome')
    a_groq_faz(c, [('Edit', {'file_path': 'conta.py', 'old_string': 'def soma', 'new_string': 'def somar'}),
                   ('Edit', {'file_path': 'conta.py', 'old_string': 'a + b', 'new_string': 'b + a'})])
    banco.adicionar(c, 'solis', 'Pronto.', cerebro='groq')
    banco.adicionar(c, 'pessoa', 'cria as notas')
    a_groq_faz(c, [('Write', {'file_path': 'notas.md', 'content': '# Notas\n'})])
    assert (tmp_path / 'conta.py').read_text(encoding='utf-8') == 'def somar(a, b):\n    return b + a\n'
    assert (tmp_path / 'notas.md').is_file()

    cliente = TestClient(main.app)
    assert cliente.get(f'/conversas/{c}/voltar').json()['ultima'] is not None
    simulado = cliente.post(f'/conversas/{c}/voltar', json={'desde': primeira, 'simular': True}).json()
    assert sorted(simulado['arquivos']) == sorted([str(tmp_path / 'conta.py'), str(tmp_path / 'notas.md')])
    assert simulado['mais'] == 2 and simulado['menos'] == 3 and (tmp_path / 'notas.md').is_file()

    r = cliente.post(f'/conversas/{c}/voltar', json={'desde': primeira}).json()
    assert not r['erros']
    # As duas edições da primeira fala voltam juntas (a cópia é a de antes da primeira), e o criado some.
    assert (tmp_path / 'conta.py').read_text(encoding='utf-8') == 'def soma(a, b):\n    return a + b\n'
    assert not (tmp_path / 'notas.md').exists()
    assert cliente.get(f'/conversas/{c}/voltar').json() == {'ultima': None}


def test_voltar_so_a_segunda_fala_deixa_a_primeira(tmp_path):
    (tmp_path / 'a.txt').write_text('um\n', encoding='utf-8')
    c = banco.nova_conversa()
    banco.guardar_projeto(c, str(tmp_path), 'pedir')
    banco.adicionar(c, 'pessoa', 'muda pra dois')
    a_groq_faz(c, [('Write', {'file_path': 'a.txt', 'content': 'dois\n'})])
    segunda = banco.adicionar(c, 'pessoa', 'muda pra três')
    a_groq_faz(c, [('Write', {'file_path': 'a.txt', 'content': 'três\n'})])
    TestClient(main.app).post(f'/conversas/{c}/voltar', json={'desde': segunda})
    assert (tmp_path / 'a.txt').read_text(encoding='utf-8') == 'dois\n'


def test_o_claude_depois_da_groq_no_mesmo_arquivo_termina_como_antes_de_tudo(tmp_path, monkeypatch):
    """A Groq mudou na fala 1, o Claude na 2: voltar da 1 tem que dar o de antes
    da Groq. Volta primeiro quem começou depois (o Claude), depois as cópias."""
    arquivo = tmp_path / 'b.txt'
    arquivo.write_text('original\n', encoding='utf-8')
    c = banco.nova_conversa()
    banco.guardar_projeto(c, str(tmp_path), 'pedir')
    primeira = banco.adicionar(c, 'pessoa', 'groq muda')
    a_groq_faz(c, [('Write', {'file_path': 'b.txt', 'content': 'da groq\n'})])
    banco.adicionar(c, 'pessoa', 'claude muda')
    banco.guardar_ponto(c, 's1', 'u1', str(tmp_path))
    banco.ponto_mudou(c, 's1')
    arquivo.write_text('do claude\n', encoding='utf-8')
    ordem = []

    async def voltar_do_claude(pontos, simular=False):
        ordem.append('claude')
        if not simular:
            arquivo.write_text('da groq\n', encoding='utf-8')  # o checkpoint do Claude: antes da fala 2
        return {'arquivos': [str(arquivo)], 'mais': 1, 'menos': 1, 'erros': []}
    monkeypatch.setattr(agente, 'voltar', voltar_do_claude)
    r = TestClient(main.app).post(f'/conversas/{c}/voltar', json={'desde': primeira}).json()
    assert ordem == ['claude'] and r['arquivos'] == [str(arquivo)] and not r['erros']
    assert arquivo.read_text(encoding='utf-8') == 'original\n'
