"""O pedido ao vivo pela escuta (pedido_ao_vivo.py, main.escuta, 22/11/2026):
"Solis, ..." respondido pela voz do Gemini Live, com o privado conferido no PC
antes (decisão do Matheus: "Sim, conferindo antes") — vai só o texto conferido,
nenhum áudio. O Gemini é simulado."""
import json

from fastapi.testclient import TestClient

from solis import ativacao, banco, corpo, main, memoria, pedido_ao_vivo, transcricao, voz
from test_ativacao import MotorFalso, palavra, quadros

VOZ_DELE = b'\x01\x00' * 240


class GeminiFalso:
    """A sessão ao vivo simulada: `resultado(texto_local)` diz o que ela devolve."""
    criadas: list = []
    resultado = None

    def __init__(self, conversa, voz, etapas=None, quem='solis', entrou=False):
        self.conversa, self.fechada, self.abriu, self.texto = conversa, False, False, None
        self.voz, self.quem, self.entrou = voz, quem, entrou
        GeminiFalso.criadas.append(self)

    def abrir(self):
        self.abriu = True

    async def fechar(self):
        self.fechada = True

    async def responder(self, texto, enviar_audio, enviar_texto=None):
        self.texto = texto
        r = GeminiFalso.resultado(texto)
        if isinstance(r, Exception):
            raise r
        if r.disse:
            await enviar_texto(r.disse)  # o texto da voz, enquanto ela fala (a ilha mostra)
            await enviar_audio(VOZ_DELE)
        return r


def _escuta(monkeypatch, texto='qual é a cotação do dólar', resultado=None):
    motor = MotorFalso()
    original = ativacao.Escuta
    monkeypatch.setattr(ativacao, 'Escuta', lambda: original(motor))
    ouvidos = []

    async def transcrever(audio, **_):
        ouvidos.append(audio)
        return {'texto': texto}
    monkeypatch.setattr(voz, 'transcrever', transcrever)
    monkeypatch.setattr(transcricao, 'pequeno_disponivel', lambda: False)
    monkeypatch.setattr(pedido_ao_vivo, 'disponivel', lambda: True)
    GeminiFalso.criadas = []
    GeminiFalso.resultado = resultado or (lambda t: pedido_ao_vivo.Resultado(
        fala=t, disse='O dólar está R$ 5,95.', primeiro_som=0.9))
    monkeypatch.setattr(pedido_ao_vivo, 'Sessao', GeminiFalso)
    return ouvidos


def _chamar(ws):
    ws.send_bytes((palavra() + quadros(1) + quadros(1.2, tom=False)).tobytes())
    assert ws.receive_json() == {'tipo': 'ativou'}


def test_o_pedido_vai_ao_vivo_a_voz_dele_chega_e_a_troca_fica_na_conversa(monkeypatch):
    _escuta(monkeypatch)
    conversa = banco.nova_conversa()
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        assert ws.receive_json() == {'tipo': 'pronta'}
        ws.send_text(json.dumps({'conversa': conversa, 'falar': True}))
        _chamar(ws)
        assert ws.receive_json() == {'tipo': 'ao_vivo', 'pedido': 'qual é a cotação do dólar', 'quem': 'solis'}
        assert ws.receive_json() == {'tipo': 'ao_vivo_texto', 'disse': 'O dólar está R$ 5,95.'}
        assert ws.receive_bytes() == VOZ_DELE
        assert ws.receive_json() == {'tipo': 'ao_vivo_fim', 'conversa': conversa,
                                     'pedido': 'qual é a cotação do dólar', 'disse': 'O dólar está R$ 5,95.',
                                     'quem': 'solis'}
    [g] = GeminiFalso.criadas
    # A sessão abriu já no "Solis" (conecta enquanto ele fala), e fechou no fim.
    assert g.abriu and g.fechada and g.conversa == conversa and g.texto == 'qual é a cotação do dólar'
    assert [(m['papel'], m['texto']) for m in banco.mensagens(conversa)] == [
        ('pessoa', 'qual é a cotação do dólar'), ('solis', 'O dólar está R$ 5,95.')]


def test_o_privado_nao_vai_pro_google(monkeypatch):
    _escuta(monkeypatch, texto='qual é a minha senha do banco')
    monkeypatch.setattr(memoria, 'eh_privado', lambda t: 'senha' in t)
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'conversa': None, 'falar': True}))
        _chamar(ws)
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'qual é a minha senha do banco'}
    assert all(g.texto is None for g in GeminiFalso.criadas)  # nada foi pro Gemini
    assert all(g.fechada for g in GeminiFalso.criadas)


def test_o_que_precisa_de_cartao_segue_pelo_caminho_de_hoje(monkeypatch):
    _escuta(monkeypatch, texto='abre o spotify', resultado=lambda t: pedido_ao_vivo.Resultado(
        fala=t, passar='abre o spotify'))
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'falar': True}))
        _chamar(ws)
        assert ws.receive_json() == {'tipo': 'ao_vivo', 'pedido': 'abre o spotify', 'quem': 'solis'}
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'abre o spotify'}


def test_o_gemini_falhou_e_o_pedido_segue_como_hoje(monkeypatch):
    _escuta(monkeypatch, resultado=lambda t: pedido_ao_vivo.Falhou('não começou a responder a tempo'))
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'falar': True}))
        _chamar(ws)
        assert ws.receive_json()['tipo'] == 'ao_vivo'
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'qual é a cotação do dólar'}


def test_sem_a_resposta_falada_e_como_sempre(monkeypatch):
    """A tela antiga (que não manda "falar") e o "Responder falando" desligado: o texto."""
    _escuta(monkeypatch)
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        ws.receive_json()
        _chamar(ws)
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'qual é a cotação do dólar'}
    assert GeminiFalso.criadas == []


def test_ao_vivo_vao_so_as_ferramentas_sem_cartao_e_o_passar():
    c = corpo.Corpo(1, None, navegar=False, cerebro='gemini-live')
    c.voz = True
    import asyncio
    nomes = [s['function']['name'] for s in pedido_ao_vivo.ferramentas(c, asyncio.run(c.especificacoes()))]
    assert {'mcp__solis__cotacao', 'mcp__solis__clima', 'mcp__solis__jogos', 'mcp__solis__datas',
            'mcp__solis__criar_lembrete', 'WebFetch', pedido_ao_vivo.PASSAR} <= set(nomes)
    assert 'PowerShell' not in nomes and corpo.MAIS not in nomes and 'mcp__solis__agendar_tarefa' not in nomes


def test_vamos_conversar_vai_pro_modo_conversa_e_nao_ao_vivo(monkeypatch):
    _escuta(monkeypatch, texto='vamos conversar')
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'falar': True}))
        _chamar(ws)
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'vamos conversar'}


# --- o registro de cada chamada (registro_voz.py) ------------------------------

def _ate(ws, tipo):
    """Lê (texto e a voz em binário) até a mensagem `tipo`."""
    while True:
        m = ws.receive()
        if m.get('text') and json.loads(m['text'])['tipo'] == tipo:
            return

def test_cada_pedido_fica_no_registro_so_com_numeros_e_o_caminho(monkeypatch):
    from solis import registro_voz
    _escuta(monkeypatch)
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'falar': True}))
        _chamar(ws)
        _ate(ws, 'ao_vivo_fim')
    eventos = registro_voz.ler()
    assert [e['evento'] for e in eventos] == ['acordou', 'pedido']
    acordou, pedido = eventos
    assert acordou['por'] == 'motor'
    assert pedido['caminho'] == 'ao_vivo' and pedido['primeiro_som_s'] == 0.9 and 'texto_s' in pedido
    # Nunca o que foi dito.
    assert 'dólar' not in registro_voz.arquivo().read_text(encoding='utf-8')
    # O arquivo é o do banco do teste, não o dos dados do Matheus.
    assert registro_voz.arquivo().parent == banco.arquivo().parent


def test_o_registro_anota_o_privado_a_falha_e_o_que_passou(monkeypatch):
    from solis import registro_voz
    casos = [('qual é a minha senha do banco', None, 'privado'),
             ('qual é a cotação do dólar', lambda t: pedido_ao_vivo.Falhou('não começou a responder a tempo'), 'falhou'),
             ('abre o spotify', lambda t: pedido_ao_vivo.Resultado(fala=t, passar=t), 'passou')]
    monkeypatch.setattr(memoria, 'eh_privado', lambda t: 'senha' in t)
    _escuta(monkeypatch)
    atual = {}

    async def transcrever(audio, **_):
        return {'texto': atual['texto']}
    monkeypatch.setattr(voz, 'transcrever', transcrever)
    GeminiFalso.resultado = lambda t: atual['resultado'](t)
    for texto, resultado, _ in casos:
        atual.update(texto=texto, resultado=resultado)
        with TestClient(main.app).websocket_connect('/escuta') as ws:
            ws.receive_json()
            ws.send_text(json.dumps({'falar': True}))
            _chamar(ws)
            _ate(ws, 'texto')
    pedidos = [e for e in registro_voz.ler() if e['evento'] == 'pedido']
    assert [p['caminho'] for p in pedidos] == [c for _, _, c in casos]
    assert pedidos[1]['motivo'] == 'demorou'


def test_o_resumo_mede_o_pronto_quando_da_voz():
    from solis import registro_voz
    registro_voz.anotar('sombra', nota=0.97)          # junto de uma chamada: não conta como falso
    registro_voz.anotar('acordou', por='whisper', sombra=True, decisao_s=0.8)
    registro_voz.anotar('pedido', caminho='ao_vivo', texto_s=1.0, primeiro_som_s=1.4)
    registro_voz.anotar('acordou', por='whisper', sombra=False, decisao_s=1.2)
    registro_voz.anotar('pedido', caminho='texto', texto_s=1.2)
    r = registro_voz.resumo()
    assert r['chamadas'] == 2 and r['detector_tambem_ouviu'] == '1 de 2'
    assert r['detector_disparos_sem_chamada'] == 0
    assert r['caminhos'] == {'ao_vivo': 1, 'texto': 1} and r['ao_vivo_primeiro_som_s'] == 1.4
    assert TestClient(main.app).get('/voz/chamadas').json()['chamadas'] == 2


def test_o_motivo_da_falha_nao_leva_a_mensagem_do_gemini():
    from solis import registro_voz
    assert registro_voz.motivo_da_falha('ClientError: 429 RESOURCE_EXHAUSTED quota') == 'limite'
    assert registro_voz.motivo_da_falha('não começou a responder a tempo') == 'demorou'
    assert registro_voz.motivo_da_falha('não abriu (ConnectionError: ...)') == 'nao_abriu'
