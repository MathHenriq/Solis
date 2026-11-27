"""O PC como corpo do servidor (corpo_remoto.py, 26/11/2026): o PC liga no
servidor, o cérebro do servidor ganha as ferramentas do PC, o cartão é no
servidor (no celular) e o PC executa só o que deixou."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from solis import agente, aprovacoes, banco, corpo, corpo_remoto, main, pc

TOKEN = 'um-token-de-teste-bem-comprido-123'
SENHA = {'Authorization': f'Bearer {TOKEN}'}


@pytest.fixture
def servidor(monkeypatch):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setenv('SOLIS_TOKEN', TOKEN)
    monkeypatch.setattr(corpo_remoto, '_pc', None)
    return TestClient(main.app, headers=SENHA)


class _Ligacao:
    capacidades = {'pc': 'PC', 'terminal': True, 'tela': True, 'arquivos': True}


class _WsFalso:
    """A ligação do PC, em filas (o mesmo laço do servidor). `None` na fila do PC = caiu."""

    def __init__(self):
        self.do_pc, self.pro_pc = asyncio.Queue(), asyncio.Queue()

    async def accept(self):
        pass

    async def receive_json(self):
        m = await self.do_pc.get()
        if m is None:
            raise WebSocketDisconnect()
        return m

    async def send_json(self, m):
        await self.pro_pc.put(m)

    async def close(self, code=1000):
        pass


def test_o_pc_liga_responde_e_quando_cai_o_pedido_falha(monkeypatch):
    monkeypatch.setattr(corpo_remoto, '_pc', None)

    async def cenario():
        ws = _WsFalso()
        await ws.do_pc.put({'tipo': 'ola', 'pc': 'PC-DO-MATHEUS', 'terminal': True, 'tela': False, 'arquivos': True})
        atendendo = asyncio.create_task(corpo_remoto.atender(ws))
        while corpo_remoto.conectado() is None:
            await asyncio.sleep(0)
        assert corpo_remoto.conectado() == {'pc': 'PC-DO-MATHEUS', 'terminal': True, 'tela': False, 'arquivos': True}
        # Um pedido: chega no PC, e a resposta volta pra quem pediu.
        pedido = asyncio.create_task(corpo_remoto.chamar('mcp__solis__listar_pasta', {'caminho': 'Documentos'}))
        msg = await ws.pro_pc.get()
        assert (msg['tipo'], msg['ferramenta'], msg['entrada']) == ('pedido', 'mcp__solis__listar_pasta', {'caminho': 'Documentos'})
        await ws.do_pc.put({'tipo': 'resposta', 'id': msg['id'], 'saida': 'contrato.pdf', 'ok': True})
        assert await pedido == ('contrato.pdf', True)
        # O pulso do PC volta (o túnel não derruba a ligação parada).
        await ws.do_pc.put({'tipo': 'pulso'})
        assert (await ws.pro_pc.get()) == {'tipo': 'pulso'}
        # O PC cai no meio de outro pedido: quem pediu fica sabendo, e ele sai da lista.
        outro = asyncio.create_task(corpo_remoto.chamar('PowerShell', {'command': 'dir'}))
        await ws.pro_pc.get()
        await ws.do_pc.put(None)
        with pytest.raises(corpo_remoto.PcFora):
            await outro
        await atendendo
        assert corpo_remoto.conectado() is None
    asyncio.run(cenario())


def test_pela_rota_le_no_pc_e_o_terminal_nao_passa(servidor, monkeypatch):
    assert servidor.get('/corpo/pc').json() == {'ligado': False}
    monkeypatch.setattr(corpo_remoto, '_pc', _Ligacao())

    async def chamar(nome, entrada, prazo=60):
        return f'lido no PC: {nome}', True
    monkeypatch.setattr(corpo_remoto, 'chamar', chamar)
    assert servidor.get('/corpo/pc').json()['ligado'] is True
    r = servidor.post('/corpo/ler', json={'ferramenta': 'mcp__solis__tela_ler', 'entrada': {}})
    assert r.json() == {'saida': 'lido no PC: mcp__solis__tela_ler', 'ok': True}
    # O terminal não vai por esta rota (sem cérebro, sem cartão).
    assert servidor.post('/corpo/ler', json={'ferramenta': 'PowerShell', 'entrada': {'command': 'dir'}}).status_code == 400


def test_sem_senha_o_pc_nao_liga(servidor):
    with pytest.raises(WebSocketDisconnect) as fechou:
        with TestClient(main.app).websocket_connect('/corpo') as ws:
            ws.receive_json()
    assert fechou.value.code == 1008


def test_sem_pc_a_leitura_diz_que_ele_esta_fora(servidor):
    r = servidor.post('/corpo/ler', json={'ferramenta': 'mcp__solis__tela_ler', 'entrada': {}})
    assert r.status_code == 503 and r.json()['erro'] == 'pc_fora'


def test_no_servidor_o_cerebro_ganha_as_ferramentas_do_pc(monkeypatch):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setattr(corpo_remoto, '_pc', _Ligacao())
    monkeypatch.setattr(corpo.os, 'name', 'posix')  # o servidor é Linux: nada disso é dele
    c = corpo.Corpo(1, navegar=False)
    nomes = {s['function']['name'] for s in asyncio.run(c.especificacoes())}
    assert {'PowerShell', 'mcp__solis__tela_ler', 'mcp__solis__ler_arquivo', 'mcp__solis__listar_pasta'} <= nomes
    # E agir na tela de longe (o cartão pega o print e o programa do PC).
    assert {'mcp__solis__tela_clicar', 'mcp__solis__tela_digitar', 'mcp__solis__tela_tecla'} <= nomes


def test_o_terminal_pede_o_cartao_aqui_e_roda_no_pc(monkeypatch):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setattr(corpo_remoto, '_pc', _Ligacao())
    monkeypatch.setattr(corpo.os, 'name', 'posix')
    decisoes, chamadas = [], []

    async def decidir(nome, entrada, por, **kw):
        decisoes.append(nome)
        return aprovacoes.Decisao(True)

    async def chamar(nome, entrada, prazo=60):
        chamadas.append((nome, entrada))
        return 'Volume in drive C', True

    async def nunca(*a, **k):
        raise AssertionError('rodou no servidor')
    monkeypatch.setattr(aprovacoes, 'decidir', decidir)
    monkeypatch.setattr(corpo_remoto, 'chamar', chamar)
    monkeypatch.setattr(corpo, '_rodar_comando', nunca)
    c = corpo.Corpo(1, navegar=False)
    assert asyncio.run(c.rodar('PowerShell', {'command': 'dir'})) == 'Volume in drive C'
    assert decisoes == ['PowerShell'] and chamadas == [('PowerShell', {'command': 'dir'})] and c.agiu


def test_pc_caiu_no_meio_o_cerebro_fica_sabendo(monkeypatch):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setattr(corpo_remoto, '_pc', _Ligacao())
    monkeypatch.setattr(corpo.os, 'name', 'posix')

    async def decidir(nome, entrada, por, **kw):
        return aprovacoes.Decisao(True)

    async def caiu(nome, entrada, prazo=60):
        raise corpo_remoto.PcFora('o PC desligou no meio')
    monkeypatch.setattr(aprovacoes, 'decidir', decidir)
    monkeypatch.setattr(corpo_remoto, 'chamar', caiu)
    saida = asyncio.run(corpo.Corpo(1, navegar=False).rodar('mcp__solis__tela_ler', {}))
    assert 'o PC desligou no meio' in saida and 'ligar o PC' in saida


# — No PC ————————————————————————————————————————————————————————————————————

def test_o_pc_so_faz_se_o_matheus_deixou_e_so_o_que_viaja(monkeypatch, tmp_path):
    (tmp_path / 'notas.txt').write_text('reunião às 14h', encoding='utf-8')
    pc.guardar_pastas([str(tmp_path)])
    monkeypatch.setattr(pc, 'ligada', lambda: True)
    ler = {'caminho': str(tmp_path / 'notas.txt')}
    assert asyncio.run(corpo_remoto.executar('mcp__solis__ler_arquivo', ler))[1] is False  # não deixou
    banco.guardar_ajuste('servidor_usa_pc', True)
    saida, ok = asyncio.run(corpo_remoto.executar('mcp__solis__ler_arquivo', ler))
    assert ok and 'reunião às 14h' in saida
    # Fora das pastas autorizadas, o próprio PC recusa.
    assert asyncio.run(corpo_remoto.executar('mcp__solis__ler_arquivo', {'caminho': 'C:/Windows/win.ini'}))[1] is False
    # O que não viaja, não roda (mesmo que o servidor peça).
    saida, ok = asyncio.run(corpo_remoto.executar('Write', {'file_path': 'x', 'content': 'y'}))
    assert not ok and 'não faz isso pelo servidor' in saida


def test_a_tela_do_pc_mostra_se_esta_ligado(monkeypatch):
    c = TestClient(main.app)
    estado = c.put('/servidor', json={'endereco': 'https://solis.exemplo.ts.net', 'token': 'senha-bem-comprida-do-servidor', 'usa_pc': True}).json()
    assert estado['usa_pc'] is True and estado['pc_ligado'] is False
    # Mudar o endereço sem mandar usa_pc mantém a chave.
    assert c.put('/servidor', json={'endereco': 'https://outro.ts.net'}).json()['usa_pc'] is True


class _Gravador:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


def test_clicar_de_longe_o_cartao_mostra_o_print_do_pc_e_o_pc_clica(monkeypatch):
    """O cartão no celular com o print e o programa do PC (a prévia); aprovado, o PC clica."""
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setattr(corpo_remoto, '_pc', _Ligacao())
    monkeypatch.setattr(corpo.os, 'name', 'posix')
    previas, chamadas = [], []

    async def previa(acao, entrada):
        previas.append((acao, entrada))
        return {'programa': ['notepad.exe', 'Sem título - Bloco de Notas'], 'imagem': 'data:image/png;base64,UFJJTlQ='}

    async def chamar(nome, entrada, prazo=60):
        chamadas.append((nome, entrada))
        return 'Arquivo  Editar  Salvar', True
    monkeypatch.setattr(corpo_remoto, 'previa', previa)
    monkeypatch.setattr(corpo_remoto, 'chamar', chamar)
    g = _Gravador()
    c = corpo.Corpo(5, g, navegar=False)

    async def tudo():
        tarefa = asyncio.ensure_future(c.rodar('mcp__solis__tela_clicar', {'x': 1155, 'y': 716}))
        while not any(e == 'aprovacao' for e, _ in g.lista):
            await asyncio.sleep(0.01)
        pedido = next(d for e, d in g.lista if e == 'aprovacao')
        assert pedido['site'] == 'Sem título - Bloco de Notas'
        assert pedido['imagem'] == 'data:image/png;base64,UFJJTlQ='  # o print veio do PC
        assert chamadas == []  # nada no PC antes do sim
        agente.responder_aprovacao(pedido['id'], True)
        return await tarefa

    saida = asyncio.run(tudo())
    assert previas == [('tela_clicar', {'x': 1155, 'y': 716})]
    assert chamadas == [('mcp__solis__tela_clicar', {'x': 1155, 'y': 716})]
    assert saida.startswith('Feito. A tela agora:') and 'Salvar' in saida and c.agiu


def test_de_longe_na_janela_do_solis_nem_pede(monkeypatch):
    monkeypatch.setenv('SOLIS_SERVIDOR', '1')
    monkeypatch.setattr(corpo_remoto, '_pc', _Ligacao())
    monkeypatch.setattr(corpo.os, 'name', 'posix')

    async def previa(acao, entrada):
        return {'programa': ['solis.exe', 'Solis'], 'imagem': None}

    async def nunca(*a, **k):
        raise AssertionError('clicou no Solis')
    monkeypatch.setattr(corpo_remoto, 'previa', previa)
    monkeypatch.setattr(corpo_remoto, 'chamar', nunca)
    saida = asyncio.run(corpo.Corpo(5, _Gravador(), navegar=False).rodar('mcp__solis__tela_clicar', {'x': 1, 'y': 1}))
    assert 'janela do próprio Solis' in saida


def test_no_pc_a_previa_e_a_acao_so_com_o_controle_da_tela(monkeypatch):
    from solis import tela
    banco.guardar_ajuste('servidor_usa_pc', True)
    monkeypatch.setattr(corpo_remoto, 'capacidades', lambda: {'tipo': 'ola', 'pc': 'PC', 'terminal': True,
                                                               'tela': False, 'arquivos': False})
    assert asyncio.run(corpo_remoto.executar('tela_previa', {'acao': 'tela_clicar', 'entrada': {'x': 1, 'y': 1}}))[1] is False
    monkeypatch.setattr(corpo_remoto, 'capacidades', lambda: {'tipo': 'ola', 'pc': 'PC', 'terminal': True,
                                                               'tela': True, 'arquivos': False})
    monkeypatch.setattr(tela, 'programa_alvo', lambda acao, e: ('notepad.exe', 'Bloco de Notas'))
    monkeypatch.setattr(tela, 'imagem_do_cartao', lambda acao, e: 'data:image/png;base64,QQ==')
    saida, ok = asyncio.run(corpo_remoto.executar('tela_previa', {'acao': 'tela_clicar', 'entrada': {'x': 1, 'y': 1}}))
    assert ok and saida == '{"programa": ["notepad.exe", "Bloco de Notas"], "imagem": "data:image/png;base64,QQ=="}'
    feitas = []
    monkeypatch.setattr(corpo, '_agir_na_tela', lambda acao, e: feitas.append((acao, e)))
    monkeypatch.setattr(tela, 'DEPOIS_S', 0)

    async def texto():
        return 'Salvar'
    monkeypatch.setattr(corpo, 'texto_da_tela', texto)
    assert asyncio.run(corpo_remoto.executar('mcp__solis__tela_digitar', {'texto': 'oi'})) == ('Salvar', True)
    assert feitas == [('tela_digitar', {'texto': 'oi'})]
