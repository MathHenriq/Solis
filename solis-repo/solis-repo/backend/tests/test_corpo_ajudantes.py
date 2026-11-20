"""Os ajudantes nos outros cérebros (corpo.py, a ferramenta Agent): o Solis roda
um laço próprio, com o mesmo cérebro e as mesmas ferramentas, e devolve o
resultado. Antes só o Claude tinha ajudantes. A Groq é simulada. Desligados
por padrão até a medição de verdade (SOLIS_CORPO_AJUDANTES=1 liga)."""
import asyncio
import json

import httpx
import pytest

from solis import agente, apis, banco, cofre, corpo, web


@pytest.fixture(autouse=True)
def ajudantes_ligados(monkeypatch):
    monkeypatch.setenv('SOLIS_CORPO_AJUDANTES', '1')


class Gravador:
    def __init__(self):
        self.lista = []
        self.anotadas = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


def sse(*eventos):
    return '\n\n'.join([f'data: {json.dumps(e)}' for e in eventos] + ['data: [DONE]']) + '\n\n'


def resposta(*eventos):
    return httpx.Response(200, text=sse(*eventos), headers={'content-type': 'text/event-stream'})


def chamadas(*pares):
    return {'choices': [{'delta': {'tool_calls': [
        {'index': i, 'id': f'c{i}_{nome}', 'type': 'function', 'function': {'name': nome, 'arguments': json.dumps(a)}}
        for i, (nome, a) in enumerate(pares)]}}]}


def texto(t):
    return {'choices': [{'delta': {'content': t}}]}


def com_chave():
    banco.guardar_ajuste('chave:groq', cofre.selar('gsk_x'))
    banco.guardar_ajuste('modelo:groq', 'openai/gpt-oss-120b')


def rodar(rota, aprovar=True):
    g = Gravador()
    c = corpo.Corpo(banco.nova_conversa(), g, navegar=False, cerebro='groq')
    c.sistema = 'sistema do pai'

    async def tudo():
        tarefa = asyncio.ensure_future(_juntar(apis.responder('groq', c.sistema, 'pesquisa X', g,
                                                              httpx.MockTransport(rota), corpo=c)))
        respondidos = 0
        while not tarefa.done():
            cartoes = [d for e, d in g.lista if e == 'aprovacao']
            if len(cartoes) > respondidos:
                agente.responder_aprovacao(cartoes[respondidos]['id'], aprovar)
                respondidos += 1
            await asyncio.sleep(0.01)
        return await tarefa
    return asyncio.run(tudo()), g, c


async def _juntar(fluxo):
    return ''.join([p async for p in fluxo])


def _do_ajudante(pedido):
    return corpo.AJUDANTE_NOTA.strip()[:30] in pedido['messages'][0]['content']


def test_o_ajudante_le_numa_conversa_propria_e_o_pai_recebe_o_resultado(monkeypatch):
    com_chave()

    async def ler(url, transporte=None):
        return url, 'Página', 'as vendas cresceram 80%'
    monkeypatch.setattr(web, 'ler', ler)
    pedidos = {'pai': [], 'ajudante': []}

    def rota(req):
        p = json.loads(req.content)
        quem = 'ajudante' if _do_ajudante(p) else 'pai'
        pedidos[quem].append(p)
        if quem == 'ajudante':
            if len(pedidos['ajudante']) == 1:
                return resposta(chamadas(('WebFetch', {'url': 'https://exemplo.com.br/carros'})))
            return resposta(texto('Resumo: as vendas cresceram 80% (https://exemplo.com.br/carros).'))
        if len(pedidos['pai']) == 1:
            return resposta(chamadas(('Agent', {'description': 'ler sobre carros', 'prompt': 'Leia e resuma.'})))
        return resposta(texto('Relatório pronto.'))

    saida, g, c = rodar(rota)
    assert saida == 'Relatório pronto.'
    # O ajudante começou com o sistema do pai e a nota de ajudante, e não tem o Agent (não abre outro).
    assert pedidos['ajudante'][0]['messages'][0]['content'].startswith('sistema do pai')
    assert 'Agent' not in [t['function']['name'] for t in pedidos['ajudante'][0]['tools']]
    assert 'Agent' in [t['function']['name'] for t in pedidos['pai'][0]['tools']]
    devolvido = [m['content'] for m in pedidos['pai'][-1]['messages'] if m.get('role') == 'tool']
    assert devolvido[0].startswith('O ajudante terminou "ler sobre carros" (1 passos)') and '80%' in devolvido[0]
    # Na resposta: o passo do ajudante; a página que ele leu vira fonte; o WebFetch dele não se mistura.
    passos = [(d['ferramenta'], d['alvo']) for e, d in g.lista if e == 'ferramenta']
    assert passos == [('Agent', 'ler sobre carros')]
    assert [d['url'] for e, d in g.lista if e == 'fonte'] == ['https://exemplo.com.br/carros']


def test_o_cartao_do_ajudante_diz_que_e_ele(tmp_path):
    com_chave()
    pedidos = {'pai': 0, 'ajudante': 0}
    alvo = tmp_path / 'notas.md'

    def rota(req):
        p = json.loads(req.content)
        quem = 'ajudante' if _do_ajudante(p) else 'pai'
        pedidos[quem] += 1
        if quem == 'ajudante':
            if pedidos['ajudante'] == 1:
                return resposta(chamadas(('Write', {'file_path': str(alvo), 'content': '# Notas\n'})))
            return resposta(texto('Escrevi as notas.'))
        if pedidos['pai'] == 1:
            return resposta(chamadas(('Agent', {'description': 'escrever as notas', 'prompt': 'Crie o notas.md.'})))
        return resposta(texto('Feito.'))

    saida, g, c = rodar(rota)
    cartao = next(d for e, d in g.lista if e == 'aprovacao')
    assert cartao['ferramenta'] == 'Write' and cartao['ajudante'] == 'escrever as notas'
    assert alvo.read_text(encoding='utf-8') == '# Notas\n' and c.agiu  # o que o ajudante fez conta pro pai


def test_varios_ajudantes_na_mesma_rodada_trabalham_juntos(monkeypatch):
    com_chave()
    ao_mesmo_tempo = {'agora': 0, 'max': 0}
    original = corpo.Corpo._ajudar

    async def ajudar(self, entrada):
        ao_mesmo_tempo['agora'] += 1
        ao_mesmo_tempo['max'] = max(ao_mesmo_tempo['max'], ao_mesmo_tempo['agora'])
        await asyncio.sleep(0.05)
        ao_mesmo_tempo['agora'] -= 1
        return f'resultado de {entrada["description"]}', True
    monkeypatch.setattr(corpo.Corpo, '_ajudar', ajudar)
    vez = []

    def rota(req):
        vez.append(1)
        if len(vez) == 1:
            return resposta(chamadas(('Agent', {'description': 'A', 'prompt': 'a'}),
                                     ('Agent', {'description': 'B', 'prompt': 'b'})))
        return resposta(texto('Juntei.'))

    saida, g, c = rodar(rota)
    assert saida == 'Juntei.' and ao_mesmo_tempo['max'] == 2
    assert [d['alvo'] for e, d in g.lista if e == 'ferramenta'] == ['A', 'B']
    assert original is not None


def test_desligados_por_padrao(monkeypatch):
    monkeypatch.delenv('SOLIS_CORPO_AJUDANTES')
    assert not corpo.Corpo(1, navegar=False, cerebro='groq').tem('Agent')


def test_o_local_e_o_ajudante_nao_abrem_ajudante():
    assert not corpo.Corpo(1, navegar=False, cerebro='local').tem('Agent')
    sub = corpo.Corpo(1, navegar=False, cerebro='groq')
    sub.ajudante = 'uma tarefa'
    assert not sub.tem('Agent') and corpo.Corpo(1, navegar=False, cerebro='groq').tem('Agent')
