"""O PC como corpo do servidor (corpo_remoto.py, 26/11/2026): o PC liga no
servidor, o cérebro do servidor ganha as ferramentas do PC, o cartão é no
servidor (no celular) e o PC executa só o que deixou."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from solis import aprovacoes, banco, corpo, corpo_remoto, main, pc

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
    # Clicar e digitar de longe: ainda não (o cartão precisa do print do PC).
    assert not nomes & {'mcp__solis__tela_clicar', 'mcp__solis__tela_digitar'}


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
