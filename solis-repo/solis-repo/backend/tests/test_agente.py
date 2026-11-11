"""O Claude pelo Agent SDK (agente.py), sem rede: o que é livre e o que pede o
Matheus, o cartão de aprovação, a ponte entre a thread do SDK e o servidor."""
import asyncio

import pytest

pytest.importorskip('claude_agent_sdk')

from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny  # noqa: E402

from solis import agente, banco, cerebros, pc  # noqa: E402


@pytest.fixture(autouse=True)
def pastas(tmp_path, monkeypatch):
    trabalho = tmp_path / 'trabalho'
    trabalho.mkdir()
    docs = tmp_path / 'Documentos'
    docs.mkdir()
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: trabalho)
    pc.guardar_pastas([str(docs)])
    return trabalho, docs


class Etapas:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


def test_dentro_das_pastas_autorizadas(pastas, tmp_path):
    trabalho, docs = pastas
    assert agente._dentro(str(docs / 'contrato.txt'))
    assert agente._dentro(str(trabalho / 'a' / 'b.txt'))
    assert agente._dentro('relativo.txt')  # relativo: na pasta de trabalho
    assert agente._dentro(None)
    assert not agente._dentro(str(tmp_path / 'outra' / 'x.txt'))
    assert not agente._dentro('C:/Windows/win.ini')
    # ".." não escapa da pasta autorizada.
    assert not agente._dentro(str(docs / '..' / 'segredo.txt'))


def test_resumo_do_cartao():
    assert agente.resumo('Write', {'file_path': 'C:/x/a.txt'}) == 'Criar ou reescrever C:/x/a.txt'
    assert agente.resumo('Edit', {'file_path': 'C:/x/a.txt'}) == 'Editar C:/x/a.txt'
    assert agente.resumo('Bash', {'command': 'dir'}) == 'Rodar no terminal: dir'
    assert agente.resumo('Read', {'file_path': 'C:/w.ini'}).startswith('Ler fora')
    assert agente.resumo('Outra', {}) == 'Usar Outra'


def _decidir(nome, entrada, responder=None):
    """Roda _decidir com um `por` que guarda o que mandou; `responder` responde o
    cartão (True/False) assim que ele aparece."""
    mandados = []

    def por(tipo, valor=None):
        mandados.append((tipo, valor))
        if responder is not None and tipo == 'etapa' and valor[0] == 'aprovacao':
            asyncio.get_running_loop().call_soon(agente.responder_aprovacao, valor[1]['id'], responder)

    return asyncio.run(agente._decidir(nome, entrada, por)), mandados


@pytest.mark.parametrize('nome', ['WebSearch', 'WebFetch', 'TodoWrite', 'mcp__solis__hora'])
def test_livres_nao_pedem(nome):
    resultado, mandados = _decidir(nome, {})
    assert isinstance(resultado, PermissionResultAllow) and mandados == []


def test_ler_dentro_e_livre_e_fora_pede(pastas):
    _, docs = pastas
    resultado, mandados = _decidir('Read', {'file_path': str(docs / 'a.txt')})
    assert isinstance(resultado, PermissionResultAllow) and mandados == []
    resultado, mandados = _decidir('Read', {'file_path': 'C:/Windows/win.ini'}, responder=False)
    assert isinstance(resultado, PermissionResultDeny)
    assert mandados[0][1][0] == 'aprovacao' and mandados[0][1][1]['ferramenta'] == 'Read'
    assert mandados[0][1][1]['alvo'] == 'C:/Windows/win.ini'


def test_escrever_aprovado_e_registrado():
    resultado, mandados = _decidir('Write', {'file_path': 'teste.txt', 'content': 'oi'}, responder=True)
    assert isinstance(resultado, PermissionResultAllow)
    etapas = [v[0] for t, v in mandados if t == 'etapa']
    assert etapas == ['aprovacao', 'aprovacao_resposta']
    assert mandados[-1][1][1]['aprovado'] is True
    acao = banco.acoes(5)[0]
    assert acao['ferramenta'] == 'Write' and acao['ok'] and 'aprovado' in acao['resultado']
    assert agente._pendentes == {}


def test_comando_recusado():
    resultado, _ = _decidir('Bash', {'command': 'del *'}, responder=False)
    assert isinstance(resultado, PermissionResultDeny) and 'recusou' in resultado.message
    assert banco.acoes(5)[0]['ok'] == 0


def test_cartao_sem_resposta_vira_recusa(monkeypatch):
    monkeypatch.setattr(agente, 'APROVACAO_MAX_S', 0.05)
    resultado, mandados = _decidir('Bash', {'command': 'dir'})
    assert isinstance(resultado, PermissionResultDeny)
    assert mandados[-1][1][1]['aprovado'] is False


def test_responder_pedido_que_nao_existe():
    assert agente.responder_aprovacao('nao-existe', True) is False


def test_rota_de_aprovacao():
    from fastapi.testclient import TestClient
    from solis import main
    c = TestClient(main.app)
    r = c.post('/aprovacoes/nao-existe', json={'aprovar': True})
    assert r.status_code == 404 and r.json()['erro'] == 'aprovacao_inexistente'


# — A ponte: a sessão roda noutra thread, o texto e as etapas chegam aqui ————————

def _rodar(monkeypatch, sessao):
    monkeypatch.setattr(agente, '_sessao', sessao)
    etapas = Etapas()

    async def tudo():
        return [p async for p in agente.claude('s', 'p', etapas)]
    return asyncio.run(tudo()), etapas


def test_ponte_texto_e_etapas(monkeypatch):
    async def sessao(sistema, prompt, por, retomar=None, **_):
        por('texto', 'Olá, ')
        por('etapa', ('ferramenta', {'ferramenta': 'Read', 'alvo': 'a.txt', 'ok': True}))
        por('texto', 'Matheus.')
        por('custo', {'usd': 0.01, 'turnos': 2, 'sessao': 'x'})
    pedacos, etapas = _rodar(monkeypatch, sessao)
    assert ''.join(pedacos) == 'Olá, Matheus.'
    assert etapas.lista == [('ferramenta', {'ferramenta': 'Read', 'alvo': 'a.txt', 'ok': True})]


def test_ponte_erro_vira_agente_falhou(monkeypatch):
    async def sessao(sistema, prompt, por, retomar=None, **_):
        raise RuntimeError('sem login')
    with pytest.raises(agente.AgenteFalhou, match='sem login'):
        _rodar(monkeypatch, sessao)


def test_cota_acabada_pausa_o_claude(monkeypatch):
    pausas = []
    monkeypatch.setattr(cerebros, 'pausar', lambda nome, ate=None, motivo='': pausas.append((nome, ate, motivo)))

    async def sessao(sistema, prompt, por, retomar=None, **_):
        por('cota', 1_900_000_000)
    _rodar(monkeypatch, sessao)
    assert pausas == [('claude', 1_900_000_000, 'a cota acabou')]


def test_cerebro_claude_usa_o_agente(monkeypatch):
    async def falso(sistema, prompt, etapas, **_):
        yield 'pelo agente'
    monkeypatch.setattr(agente, 'claude', falso)

    async def tudo():
        return [p async for p in cerebros.claude('s', 'p')]
    assert asyncio.run(tudo()) == ['pelo agente']


def test_falha_do_agente_vira_falha_do_cerebro(monkeypatch):
    async def falso(sistema, prompt, etapas, **_):
        raise agente.AgenteFalhou('caiu')
        yield  # pragma: no cover

    monkeypatch.setattr(agente, 'claude', falso)

    async def tudo():
        return [p async for p in cerebros.claude('s', 'p')]
    with pytest.raises(cerebros.CerebroFalhou):
        asyncio.run(tudo())


# — A sessão continua entre mensagens (docs/PARIDADE.md) ——————————————————————

from solis import roteador  # noqa: E402


def _msg(id_, papel, texto, cerebro=None, privada=False):
    return {'id': id_, 'papel': papel, 'texto': texto, 'cerebro': cerebro, 'privada': privada}


def test_banco_guarda_troca_e_esquece_a_sessao():
    c = banco.nova_conversa()
    assert banco.sessao_claude(c) is None
    banco.guardar_sessao_claude(c, 'a')
    banco.guardar_sessao_claude(c, 'b')
    assert banco.sessao_claude(c) == 'b'
    banco.esquecer_sessao_claude(c)
    assert banco.sessao_claude(c) is None


def test_sem_sessao_vai_o_pedido_inteiro():
    c = banco.nova_conversa()
    s = roteador.sessao_claude(c, [_msg(1, 'pessoa', 'oi')], [], [], 'oi')
    assert s == {'conversa': c, 'id': None, 'prompt': None}


def test_com_sessao_vai_so_o_que_ele_nao_viu():
    c = banco.nova_conversa()
    banco.guardar_sessao_claude(c, 'sessao-1')
    historico = [
        _msg(1, 'pessoa', 'leia o contrato'),
        _msg(2, 'solis', 'li, o aluguel é 2300', 'claude'),
        _msg(3, 'pessoa', 'que horas são'),
        _msg(4, 'solis', 'são 10h', 'local'),
        _msg(5, 'pessoa', 'segredo', privada=True),
        _msg(6, 'pessoa', 'e a multa?'),
    ]
    s = roteador.sessao_claude(c, historico, [], [], 'e a multa?')
    assert s['id'] == 'sessao-1'
    assert 'são 10h' in s['prompt'] and 'que horas são' in s['prompt']
    assert 'leia o contrato' not in s['prompt'] and 'aluguel' not in s['prompt']
    assert 'segredo' not in s['prompt']
    assert s['prompt'].rstrip().endswith('e a multa?')


def test_sessao_sem_resposta_dele_no_historico_recomeca():
    c = banco.nova_conversa()
    banco.guardar_sessao_claude(c, 'velha')
    historico = [_msg(1, 'pessoa', 'oi'), _msg(2, 'solis', 'oi', 'local'), _msg(3, 'pessoa', 'e aí')]
    assert roteador.sessao_claude(c, historico, [], [], 'e aí')['id'] is None


def _cerebro_claude(sessao):
    async def tudo():
        return [p async for p in cerebros.claude('s', 'pedido inteiro', sessao=sessao)]
    return asyncio.run(tudo())


def test_continua_a_sessao_e_guarda_a_nova(monkeypatch):
    c = banco.nova_conversa()
    chamadas = []

    async def falso(sistema, prompt, etapas, retomar=None, ao_sessao=None):
        chamadas.append((prompt, retomar))
        ao_sessao('sessao-2')
        yield 'ok'
    monkeypatch.setattr(agente, 'claude', falso)
    assert _cerebro_claude({'conversa': c, 'id': 'sessao-1', 'prompt': 'pedido curto'}) == ['ok']
    assert chamadas == [('pedido curto', 'sessao-1')]
    assert banco.sessao_claude(c) == 'sessao-2'


def test_sessao_que_nao_continua_recomeca_com_o_pedido_inteiro(monkeypatch):
    c = banco.nova_conversa()
    banco.guardar_sessao_claude(c, 'sumiu')
    chamadas = []

    async def falso(sistema, prompt, etapas, retomar=None, ao_sessao=None):
        chamadas.append((prompt, retomar))
        if retomar:
            raise agente.AgenteFalhou('No conversation found')
        ao_sessao('nova')
        yield 'ok'
    monkeypatch.setattr(agente, 'claude', falso)
    assert _cerebro_claude({'conversa': c, 'id': 'sumiu', 'prompt': 'pedido curto'}) == ['ok']
    assert chamadas == [('pedido curto', 'sumiu'), ('pedido inteiro', None)]
    assert banco.sessao_claude(c) == 'nova'


# — O modelo e o quanto ele pensa ————————————————————————————————————————————————

def test_ajustes_do_claude_pela_rota():
    from fastapi.testclient import TestClient
    from solis import main
    c = TestClient(main.app)
    assert c.get('/cerebros/claude/ajustes').json()['modelo'] is None
    r = c.put('/cerebros/claude/ajustes', json={'modelo': 'opus', 'esforco': 'high'}).json()
    assert (r['modelo'], r['esforco']) == ('opus', 'high') and 'haiku' in r['modelos']
    assert c.put('/cerebros/claude/ajustes', json={'modelo': 'gpt', 'esforco': None}).status_code == 400
    assert c.put('/cerebros/claude/ajustes', json={'modelo': None, 'esforco': 'turbo'}).status_code == 400
    assert c.get('/cerebros/claude/ajustes').json()['modelo'] == 'opus'


def test_o_modelo_escolhido_vai_pra_sessao(monkeypatch):
    agente.guardar_ajustes('haiku', 'low')
    recebido = {}

    async def sessao(sistema, prompt, por, retomar=None, **kw):
        recebido.update(kw)
        por('texto', 'ok')
    _rodar(monkeypatch, sessao)
    assert (recebido['modelo'], recebido['esforco']) == ('haiku', 'low')


def test_caminho_longo_guarda_o_nome_do_arquivo():
    longo = 'C:/' + 'pasta/' * 40 + 'placa.png'
    alvo = agente._alvo('Read', {'file_path': longo})
    assert alvo.endswith('placa.png') and len(alvo) == 160
    assert agente._alvo('Bash', {'command': 'x' * 300}) == 'x' * 160
