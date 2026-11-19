"""O corpo do Solis (solis/corpo.py): as mesmas ferramentas pra todo cérebro.
Decisão do Matheus (18/11/2026): o Solis é um corpo, o cérebro é que se troca.
Aqui, a Groq simulada pede ferramentas pelo chat/completions e o Solis roda —
com os mesmos cartões do Claude. Nada sai pra rede."""
import asyncio
import json

import httpx
import pytest

from solis import agente, apis, banco, cofre, corpo, navegador, roteador


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


def chamada(nome, argumentos, id_='c1', index=0):
    return {'choices': [{'delta': {'tool_calls': [
        {'index': index, 'id': id_, 'type': 'function', 'function': {'name': nome, 'arguments': json.dumps(argumentos)}}]}}]}


def texto(t):
    return {'choices': [{'delta': {'content': t}}]}


def com_chave():
    banco.guardar_ajuste('chave:groq', cofre.selar('gsk_x'))
    banco.guardar_ajuste('modelo:groq', 'openai/gpt-oss-120b')


def rodar(gerador):
    async def junta():
        return ''.join([p async for p in gerador])
    return asyncio.run(junta())


@pytest.fixture
def navegador_falso(monkeypatch):
    """O servidor do navegador simulado: as ferramentas dele e o que cada uma faz."""
    feitas = []
    lista = [
        {'name': n, 'description': f'faz {n}', 'inputSchema': {
            '$schema': 'http://json-schema.org/draft-07/schema#', 'type': 'object', 'additionalProperties': False,
            'properties': {'url': {'type': 'string'}, 'element': {'type': 'string'}, 'target': {'type': 'string'}},
            'required': []}}
        for n in ('browser_navigate', 'browser_snapshot', 'browser_click', 'browser_evaluate', 'browser_drag')]
    monkeypatch.setattr(navegador, 'ferramentas', lambda: lista)

    def chamar(acao, entrada):
        feitas.append((acao, entrada))
        return f'feito {acao}\n- Page URL: https://www.exemplo.com.br/x'
    monkeypatch.setattr(navegador, 'chamar', chamar)
    monkeypatch.setattr(navegador, 'segurar', lambda: None)
    return feitas


def test_a_groq_pede_a_hora_o_solis_roda_e_ela_responde():
    com_chave()
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        if len(pedidos) == 1:
            return resposta(chamada('mcp__solis__hora', {}))
        return resposta(texto('São '), texto('dez horas.'))

    g = Gravador()
    saida = rodar(apis.responder('groq', 'sis', 'que horas são?', g, httpx.MockTransport(rota),
                                 corpo=corpo.Corpo(1, g, navegar=False)))
    assert saida == 'São dez horas.'
    primeiro, segundo = pedidos
    nomes = [t['function']['name'] for t in primeiro['tools']]
    assert 'mcp__solis__hora' in nomes and 'mcp__solis__criar_lembrete' in nomes
    assert not any(n.startswith('mcp__navegador__') for n in nomes)
    # O segundo pedido leva o que o modelo pediu e o que voltou.
    assert segundo['messages'][-2]['tool_calls'][0]['function']['name'] == 'mcp__solis__hora'
    assert segundo['messages'][-1]['role'] == 'tool' and segundo['messages'][-1]['tool_call_id'] == 'c1'
    assert ('ferramenta', {'ferramenta': 'mcp__solis__hora', 'alvo': '', 'ok': True,
                           'id': g.lista[-1][1]['id']}) in g.lista


def test_lembrete_pela_ferramenta_vai_pra_tela_e_o_aprendizado_nao_repete():
    com_chave()
    n = []

    def rota(req):
        n.append(1)
        if len(n) == 1:
            return resposta(chamada('mcp__solis__criar_lembrete', {'texto': 'Ligar pro João', 'dia': '', 'hora': ''}))
        return resposta(texto('Anotei.'))

    g = Gravador()
    rodar(apis.responder('groq', 'sis', 'me lembra de ligar pro João', g, httpx.MockTransport(rota),
                         corpo=corpo.Corpo(1, g, navegar=False)))
    assert [t['texto'] for t in banco.tarefas_abertas(10)] == ['Ligar pro João']
    assert g.anotadas == [{'texto': 'Ligar pro João', 'prazo': None, 'hora': None}]


def test_so_o_essencial_do_navegador_vai_e_o_esquema_sai_limpo(navegador_falso):
    c = corpo.Corpo(1, Gravador(), navegar=True)
    specs = asyncio.run(c.especificacoes())
    nav = {s['function']['name']: s['function']['parameters'] for s in specs
           if s['function']['name'].startswith(navegador.PREFIXO)}
    # browser_evaluate e browser_drag não estão nas essenciais.
    assert set(nav) == {'mcp__navegador__browser_navigate', 'mcp__navegador__browser_snapshot',
                        'mcp__navegador__browser_click'}
    p = nav['mcp__navegador__browser_click']
    assert '$schema' not in p and 'additionalProperties' not in p and p['type'] == 'object'


def test_abrir_pagina_e_livre_e_clicar_pede_o_mesmo_cartao_do_claude(navegador_falso):
    com_chave()
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        if len(pedidos) == 1:
            return resposta(chamada('mcp__navegador__browser_navigate', {'url': 'https://www.exemplo.com.br/x'}))
        if len(pedidos) == 2:
            return resposta(chamada('mcp__navegador__browser_click', {'element': 'botão Assistir', 'ref': 'e5'}, 'c2'))
        return resposta(texto('Pronto, cliquei.'))

    g = Gravador()

    async def tudo():
        fluxo = apis.responder('groq', 'sis', 'abre e clica', g, httpx.MockTransport(rota),
                               corpo=corpo.Corpo(7, g, navegar=True))
        tarefa = asyncio.ensure_future(_juntar(fluxo))
        # O cartão aparece; o Matheus aprova.
        while not any(e == 'aprovacao' for e, _ in g.lista):
            await asyncio.sleep(0.01)
        pedido = next(d for e, d in g.lista if e == 'aprovacao')
        assert pedido['ferramenta'] == 'mcp__navegador__browser_click'
        assert pedido['site'] == 'exemplo.com.br' and 'botão Assistir' in pedido['alvo']
        assert agente.responder_aprovacao(pedido['id'], True)
        return await tarefa

    assert asyncio.run(tudo()) == 'Pronto, cliquei.'
    assert [a for a, _ in navegador_falso] == ['browser_navigate', 'browser_click']
    passos = [d for e, d in g.lista if e == 'ferramenta']
    assert [p['alvo'] for p in passos] == ['https://www.exemplo.com.br/x', 'Cliquei em botão Assistir']


async def _juntar(fluxo):
    return ''.join([p async for p in fluxo])


def test_recusado_o_modelo_fica_sabendo_e_nada_acontece(navegador_falso):
    com_chave()
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        if len(pedidos) == 1:
            return resposta(chamada('mcp__navegador__browser_click', {'element': 'Comprar', 'ref': 'e9'}))
        return resposta(texto('Tudo bem, não cliquei.'))

    g = Gravador()

    async def tudo():
        tarefa = asyncio.ensure_future(_juntar(apis.responder(
            'groq', 'sis', 'clica', g, httpx.MockTransport(rota), corpo=corpo.Corpo(8, g, navegar=True))))
        while not any(e == 'aprovacao' for e, _ in g.lista):
            await asyncio.sleep(0.01)
        agente.responder_aprovacao(next(d for e, d in g.lista if e == 'aprovacao')['id'], False)
        return await tarefa

    assert asyncio.run(tudo()) == 'Tudo bem, não cliquei.'
    assert navegador_falso == []
    assert pedidos[1]['messages'][-1]['content'] == 'O Matheus recusou.'
    assert [d['ok'] for e, d in g.lista if e == 'ferramenta'] == [False]


def test_a_proibida_nem_roda(navegador_falso):
    c = corpo.Corpo(1, Gravador(), navegar=True)
    assert 'não existe' in asyncio.run(c.rodar('mcp__navegador__browser_run_code_unsafe', {'code': 'x'}))
    assert navegador_falso == []


def test_depois_de_agir_uma_falha_para_ali_em_vez_de_cair_pro_proximo(monkeypatch):
    """Se a Groq já anotou o lembrete e caiu no limite, o Claude não pode anotar de novo."""
    com_chave()
    monkeypatch.setattr(apis, 'ESPERAS_NO_MEIO', 0)
    n = []

    def rota(req):
        n.append(1)
        if len(n) == 1:
            return resposta(chamada('mcp__solis__criar_lembrete', {'texto': 'Pagar a luz', 'dia': '', 'hora': ''}))
        return httpx.Response(429, text='limite', headers={'retry-after': '30'})

    g = Gravador()
    saida = rodar(apis.responder('groq', 'sis', 'me lembra', g, httpx.MockTransport(rota),
                                 corpo=corpo.Corpo(1, g, navegar=False)))
    assert saida.startswith('\n\nParei no meio: o limite grátis acabou')
    assert len(banco.tarefas_abertas(10)) == 1


def test_sem_ter_agido_a_falha_ainda_cai_pro_proximo(monkeypatch):
    com_chave()
    monkeypatch.setattr(apis, 'ESPERAS_NO_MEIO', 0)
    n = []

    def rota(req):
        n.append(1)
        if len(n) == 1:
            return resposta(chamada('mcp__solis__hora', {}))
        return httpx.Response(429, text='limite')

    g = Gravador()
    with pytest.raises(apis.CerebroFalhou):
        rodar(apis.responder('groq', 'sis', 'que horas', g, httpx.MockTransport(rota),
                             corpo=corpo.Corpo(1, g, navegar=False)))


def test_muitas_rodadas_param(monkeypatch):
    com_chave()
    monkeypatch.setattr(corpo, 'RODADAS_MAX', 2)
    rota = lambda req: resposta(chamada('mcp__solis__hora', {}))  # noqa: E731
    g = Gravador()
    saida = rodar(apis.responder('groq', 'sis', 'x', g, httpx.MockTransport(rota), corpo=corpo.Corpo(1, g, navegar=False)))
    assert 'muitas ações seguidas' in saida


def test_resultado_grande_volta_cortado(navegador_falso, monkeypatch):
    monkeypatch.setattr(navegador, 'chamar', lambda a, e: 'x' * (corpo.RESULTADO_MAX + 500))
    saida = asyncio.run(corpo.Corpo(1, Gravador(), navegar=True).rodar('mcp__navegador__browser_snapshot', {}))
    assert len(saida) < corpo.RESULTADO_MAX + 100 and 'cortado' in saida


def test_o_claude_recebe_as_mesmas_do_solis(monkeypatch):
    """As do Solis do Claude saem do corpo: mesmo nome, mesma descrição."""
    import claude_agent_sdk
    capturado = {}
    monkeypatch.setattr(claude_agent_sdk, 'create_sdk_mcp_server', lambda name, tools: capturado.update(tools=tools))
    agente._ferramentas_solis()
    assert [t.name for t in capturado['tools']] == [f.nome for f in corpo.DO_SOLIS]
    assert [t.description for t in capturado['tools']] == [f.descricao for f in corpo.DO_SOLIS]


def test_a_groq_com_corpo_sabe_do_navegador_e_ainda_passa_o_resto(monkeypatch):
    """No roteador: a Groq recebe o corpo, o sistema fala das ferramentas e do
    navegador, e o que falta a ela (terminal, arquivos) ainda passa pro Claude."""
    monkeypatch.setattr(corpo.Corpo, '__init__', lambda self, conversa, etapas: (
        setattr(self, 'navegar', True), setattr(self, 'conversa', conversa), setattr(self, 'etapas', etapas),
        setattr(self, 'agiu', False), setattr(self, '_nav', None), setattr(self, 'terminal', False))[0])
    vistos = []

    async def abrir(nome, sistema, prompt, etapas=None, sessao=None, rapido=False, corpo=None):
        vistos.append((nome, sistema, corpo))

        async def gen():
            # Leve, sem ferramenta: pede. Com o corpo: faz.
            yield 'ok' if corpo is not None else '[FERRAMENTA]'
        return gen()
    from solis import cerebros
    monkeypatch.setattr(cerebros, 'abrir', abrir)
    g = Gravador()

    async def ir():
        fluxo, quem = await roteador.responder(['groq', 'claude'], '', 1, [], [], [], None, 'abre o youtube', g)
        return ''.join([p async for p in fluxo]), quem
    assert asyncio.run(ir()) == ('ok', 'groq')
    # Primeiro leve (sem corpo, com a marca pra pedir); depois a mesma Groq com o corpo.
    (n1, leve, sem), (n2, sistema, o_corpo) = vistos
    assert n1 == n2 == 'groq' and sem is None and roteador.PASSA in leve and 'mcp__solis__' not in leve
    assert isinstance(o_corpo, corpo.Corpo)
    # Na tela é uma tentativa só: um "Escolhi Groq", nenhuma queda.
    assert [e for e, _ in g.lista if e in ('cerebro', 'queda')] == ['cerebro']
    assert 'mcp__solis__' in sistema and 'mcp__navegador__' in sistema
    assert roteador.PASSA in sistema and 'não roda comandos' in sistema
    assert 'Você não roda comandos nem acessa a internet' not in sistema


def test_desligado_volta_ao_so_texto(monkeypatch):
    monkeypatch.setattr(roteador, 'CORPO', False)
    assert not roteador.com_corpo('groq')
    assert roteador.sistema_para('groq') == roteador.SISTEMA_NUVEM


def test_no_meio_da_tarefa_o_limite_por_minuto_se_espera_e_segue():
    """Medido na Groq grátis: 8.000 tokens por minuto, ~3.000 por pedido com as
    ferramentas — a terceira rodada seguida bate no limite. Ela espera o que a
    Groq disse e continua."""
    com_chave()
    n = []

    def rota(req):
        n.append(1)
        if len(n) == 1:
            return resposta(chamada('mcp__solis__criar_lembrete', {'texto': 'Pagar a luz', 'dia': '', 'hora': ''}))
        if len(n) == 2:
            return httpx.Response(429, text='limite', headers={'retry-after': '0.05'})
        return resposta(texto('Anotei.'))

    g = Gravador()
    saida = rodar(apis.responder('groq', 'sis', 'me lembra', g, httpx.MockTransport(rota),
                                 corpo=corpo.Corpo(1, g, navegar=False)))
    assert saida == 'Anotei.' and len(n) == 3
    assert [e for e, _ in g.lista if e == 'esperando'] == ['esperando']


def test_espera_longa_demais_nao_se_espera(monkeypatch):
    com_chave()
    n = []

    def rota(req):
        n.append(1)
        if len(n) == 1:
            return resposta(chamada('mcp__solis__hora', {}))
        return httpx.Response(429, text='limite', headers={'retry-after': '120'})

    g = Gravador()
    with pytest.raises(apis.CerebroFalhou):
        rodar(apis.responder('groq', 'sis', 'que horas', g, httpx.MockTransport(rota),
                             corpo=corpo.Corpo(1, g, navegar=False)))
    assert len(n) == 2


def test_pergunta_comum_vai_leve_sem_ferramenta(monkeypatch):
    """O que a Groq responde sem ferramenta (a maioria, pela voz) não paga o peso delas."""
    vistos = []

    async def abrir(nome, sistema, prompt, etapas=None, sessao=None, rapido=False, corpo=None):
        vistos.append((nome, corpo))

        async def gen():
            yield 'Canberra.'
        return gen()
    from solis import cerebros
    monkeypatch.setattr(cerebros, 'abrir', abrir)

    async def ir():
        fluxo, quem = await roteador.responder(['groq', 'claude'], '', 1, [], [], [], None, 'capital da Austrália?')
        return ''.join([p async for p in fluxo]), quem
    assert asyncio.run(ir()) == ('Canberra.', 'groq')
    assert vistos == [('groq', None)]


def test_com_o_corpo_e_ainda_faltando_ferramenta_passa_pro_claude(monkeypatch):
    """Terminal e arquivos a Groq ainda não tem: com o corpo, ela passa de novo, e vai pro Claude."""
    monkeypatch.setattr(corpo.Corpo, '__init__', lambda self, conversa, etapas: (
        setattr(self, 'navegar', False), setattr(self, 'conversa', conversa), setattr(self, 'etapas', etapas),
        setattr(self, 'agiu', False), setattr(self, '_nav', None), setattr(self, 'terminal', False))[0])
    vistos = []

    async def abrir(nome, sistema, prompt, etapas=None, sessao=None, rapido=False, corpo=None):
        vistos.append((nome, corpo is not None))

        async def gen():
            yield 'Rodei.' if nome == 'claude' else '[FERRAMENTA]'
        return gen()
    from solis import cerebros
    monkeypatch.setattr(cerebros, 'abrir', abrir)

    async def ir():
        fluxo, quem = await roteador.responder(['groq', 'gemini', 'claude'], '', 1, [], [], [], None, 'roda o git status')
        return ''.join([p async for p in fluxo]), quem
    assert asyncio.run(ir()) == ('Rodei.', 'claude')
    # A Groq leve, a Groq com o corpo, e o Gemini nem foi (diria o mesmo).
    assert vistos == [('groq', False), ('groq', True), ('claude', False)]


def test_rodou_ferramenta_e_ficou_calado_pede_a_resposta_sem_ferramentas():
    com_chave()
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        if len(pedidos) == 1:
            return resposta(chamada('mcp__solis__hora', {}))
        if len(pedidos) == 2:
            return resposta({'choices': [{'delta': {'reasoning': 'pensei'}}]})
        return resposta(texto('São dez horas.'))

    g = Gravador()
    saida = rodar(apis.responder('groq', 'sis', 'que horas', g, httpx.MockTransport(rota),
                                 corpo=corpo.Corpo(1, g, navegar=False)))
    assert saida == 'São dez horas.'
    assert 'tools' in pedidos[1] and 'tools' not in pedidos[2]
    assert pedidos[2]['messages'][-1] == {'role': 'user', 'content': 'Responda ao Matheus agora, com o que você já viu.'}


def test_o_navegador_vai_enxuto(navegador_falso):
    """Só os parâmetros do dia a dia, descrições curtas, e o elemento obrigatório (o cartão mostra)."""
    c = corpo.Corpo(1, Gravador(), navegar=True)
    specs = {s['function']['name']: s['function'] for s in asyncio.run(c.especificacoes())}
    clique = specs['mcp__navegador__browser_click']['parameters']
    assert set(clique['properties']) == {'element', 'target'}  # o falso não tem doubleClick
    assert clique['required'] == ['element']
    assert 'ref' not in clique['properties']


# --- o terminal ---------------------------------------------------------------

def _ate_o_cartao(g, aprovar, sempre=False):
    """Espera o cartão do terminal e responde (o Matheus)."""
    async def esperar():
        while not any(e == 'aprovacao' for e, _ in g.lista):
            await asyncio.sleep(0.01)
        pedido = next(d for e, d in g.lista if e == 'aprovacao')
        agente.responder_aprovacao(pedido['id'], aprovar, sempre)
        return pedido
    return esperar()


def test_o_terminal_vai_com_o_mesmo_cartao_do_claude_e_roda_na_pasta_do_projeto(tmp_path):
    com_chave()
    conversa = banco.nova_conversa()
    banco.guardar_projeto(conversa, str(tmp_path), 'pedir')
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        if len(pedidos) == 1:
            return resposta(chamada('PowerShell', {'command': 'Write-Output "olá"; (Get-Location).Path',
                                                   'description': 'diz olá e a pasta'}))
        return resposta(texto('Feito.'))

    g = Gravador()

    async def tudo():
        tarefa = asyncio.ensure_future(_juntar(apis.responder(
            'groq', 'sis', 'roda', g, httpx.MockTransport(rota), corpo=corpo.Corpo(conversa, g, navegar=False))))
        pedido = await _ate_o_cartao(g, True)
        return pedido, await tarefa

    pedido, saida = asyncio.run(tudo())
    assert saida == 'Feito.'
    assert pedido['ferramenta'] == 'PowerShell' and pedido['resumo'].startswith('Rodar no terminal: Write-Output')
    resultado = pedidos[1]['messages'][-1]['content']
    assert resultado.startswith('(código de saída 0)') and 'olá' in resultado
    assert str(tmp_path.resolve()).lower() in resultado.lower()
    passo = next(d for e, d in g.lista if e == 'ferramenta')
    assert passo['ok'] is True and 'olá' in passo['saida']


def test_terminal_recusado_nao_roda(tmp_path):
    com_chave()
    marca = tmp_path / 'nao-devia.txt'
    n = []

    def rota(req):
        n.append(1)
        if len(n) == 1:
            return resposta(chamada('PowerShell', {'command': f'New-Item "{marca}"', 'description': 'cria'}))
        return resposta(texto('Não rodei.'))

    g = Gravador()

    async def tudo():
        tarefa = asyncio.ensure_future(_juntar(apis.responder(
            'groq', 'sis', 'cria', g, httpx.MockTransport(rota), corpo=corpo.Corpo(1, g, navegar=False))))
        await _ate_o_cartao(g, False)
        return await tarefa

    assert asyncio.run(tudo()) == 'Não rodei.'
    assert not marca.exists()


def test_sempre_este_comando_vale_so_pro_mesmo_comando():
    c = corpo.Corpo(42, Gravador(), navegar=False)
    g = c.etapas

    async def tudo():
        primeiro = asyncio.ensure_future(c.rodar('PowerShell', {'command': 'Write-Output 1', 'description': 'x'}))
        await _ate_o_cartao(g, True, sempre=True)
        await primeiro
        antes = sum(1 for e, _ in g.lista if e == 'aprovacao')
        await c.rodar('PowerShell', {'command': 'Write-Output 1', 'description': 'x'})  # o mesmo: sem cartão
        assert sum(1 for e, _ in g.lista if e == 'aprovacao') == antes
        outro = asyncio.ensure_future(c.rodar('PowerShell', {'command': 'Write-Output 2', 'description': 'y'}))
        while sum(1 for e, _ in g.lista if e == 'aprovacao') == antes:
            await asyncio.sleep(0.01)
        agente.responder_aprovacao([d for e, d in g.lista if e == 'aprovacao'][-1]['id'], False)
        return await outro

    assert asyncio.run(tudo()) == 'O Matheus recusou.'


def test_terminal_desligado_nao_vai(monkeypatch):
    monkeypatch.setenv('SOLIS_CORPO_TERMINAL', '0')
    c = corpo.Corpo(1, Gravador(), navegar=False)
    nomes = [s['function']['name'] for s in asyncio.run(c.especificacoes())]
    assert 'PowerShell' not in nomes
    assert 'não existe' in asyncio.run(c.rodar('PowerShell', {'command': 'Write-Output 1'}))


def test_com_terminal_o_sistema_fala_dele_e_nao_diz_que_nao_roda_comandos():
    s = roteador.sistema_para('groq', False, True, True) + roteador.notas_do_cerebro('groq', ['claude'], False, True, True)
    assert 'PowerShell' in s and 'não roda comandos' not in s and 'não controla a tela' in s
    s = roteador.sistema_para('groq', False, True, False) + roteador.notas_do_cerebro('groq', ['claude'], False, True, False)
    assert 'PowerShell' not in s and 'não roda comandos' in s
