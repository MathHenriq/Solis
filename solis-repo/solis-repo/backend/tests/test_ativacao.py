"""A palavra de ativação: o motor ouve "Solis", o que vem depois vira comando
até a pessoa parar de falar, e o WebSocket leva isso ao navegador — com um
Porcupine falso e um Whisper falso, sem nada do Matheus."""
import array
import math

import pytest
from fastapi.testclient import TestClient

from solis import ativacao, banco, cofre, main, voz

N = 512
TAXA = ativacao.TAXA
MARCA = 12345  # o quadro que começa com isto é "a palavra"


class MotorFalso:
    frame_length = N

    def __init__(self):
        self.apagado = False

    def process(self, quadro):
        return 0 if quadro[0] == MARCA else -1

    def delete(self):
        self.apagado = True


def quadros(segundos, tom=True):
    """PCM 16 bits: um tom de 300 Hz (fala) ou silêncio, em quadros inteiros."""
    n = int(segundos * TAXA) // N * N
    if not tom:
        return array.array('h', [0] * n)
    return array.array('h', [int(8000 * math.sin(2 * math.pi * 300 * i / TAXA)) for i in range(n)])


def palavra():
    q = quadros(N / TAXA)
    q[0] = MARCA
    return q


def test_sem_a_palavra_nada_acontece():
    e = ativacao.Escuta(MotorFalso())
    assert list(e.alimentar(quadros(2).tobytes())) == []
    assert e.comando is None


def test_palavra_depois_fala_e_silencio_vira_comando():
    e = ativacao.Escuta(MotorFalso())
    audio = quadros(1, tom=False) + palavra() + quadros(1.5) + quadros(1.2, tom=False)
    # O 'rascunho' (a cascata) tem teste próprio, mais abaixo.
    eventos = [ev for ev in e.alimentar(audio.tobytes()) if ev[0] != 'rascunho']
    assert [t for t, _ in eventos] == ['ativou', 'comando']
    wav = eventos[1][1]
    assert wav[:4] == b'RIFF'
    # O comando tem a fala e o silêncio do fim (até FIM_SILENCIO), não o antes da palavra.
    assert 1.5 <= (len(wav) - 44) / 2 / TAXA <= 1.5 + ativacao.FIM_SILENCIO + 0.1


def test_alimentado_aos_pedacos_da_no_mesmo():
    e = ativacao.Escuta(MotorFalso())
    audio = (palavra() + quadros(1) + quadros(1.2, tom=False)).tobytes()
    eventos = []
    for i in range(0, len(audio), 333):  # pedaços que não batem com o quadro
        eventos += [ev for ev in e.alimentar(audio[i:i + 333]) if ev[0] != 'rascunho']
    assert [t for t, _ in eventos] == ['ativou', 'comando']


def test_palavra_sem_fala_depois_desiste():
    e = ativacao.Escuta(MotorFalso())
    eventos = list(e.alimentar((palavra() + quadros(ativacao.INICIO_MAX + 0.5, tom=False)).tobytes()))
    assert eventos == [('ativou', None), ('comando', None)]


def test_fala_sem_fim_e_cortada_no_maximo():
    e = ativacao.Escuta(MotorFalso())
    eventos = list(e.alimentar((palavra() + quadros(ativacao.COMANDO_MAX + 1)).tobytes()))
    assert [t for t, _ in eventos] == ['ativou', 'comando'] and eventos[1][1] is not None


def test_estado_e_chave_selada(monkeypatch, tmp_path):
    monkeypatch.setattr(ativacao, 'PASTA', tmp_path)
    monkeypatch.setattr(ativacao, 'PALAVRA', tmp_path / 'solis.ppn')
    monkeypatch.setattr(ativacao, 'IDIOMA', tmp_path / 'pt.pv')
    conferidos = []
    monkeypatch.setattr(ativacao, 'conferir', lambda k, p: conferidos.append((k, p.name)))
    monkeypatch.setattr(voz, 'disponivel', lambda: False)
    c = TestClient(main.app)
    assert c.get('/ativacao').json() == {'chave': False, 'palavra': False, 'idioma': False, 'motor': None}
    assert c.put('/ativacao/chave', json={'chave': '  minha-chave '}).json()['chave'] is True
    bruto = banco.ajuste(ativacao.CHAVE)
    if cofre.DISPONIVEL:
        assert cofre.selado(bruto)
    assert ativacao.chave() == 'minha-chave'
    # O modelo é conferido com a chave antes de ficar.
    assert c.put('/ativacao/palavra', content=b'PPN' * 100).json()['palavra'] is True
    assert conferidos == [('minha-chave', 'solis.ppn.novo')]
    assert c.get('/ativacao').json()['motor'] == 'porcupine'
    assert c.delete('/ativacao').json() == {'chave': False, 'palavra': False, 'idioma': False, 'motor': None}


def test_modelo_recusado_nao_fica(monkeypatch, tmp_path):
    tmp_path = tmp_path / 'porcupine'  # a pasta do teste também guarda o banco
    monkeypatch.setattr(ativacao, 'PASTA', tmp_path)
    monkeypatch.setattr(ativacao, 'PALAVRA', tmp_path / 'solis.ppn')
    banco.guardar_ajuste(ativacao.CHAVE, cofre.selar('k'))

    def recusa(k, p):
        raise ativacao.ModeloRecusado('ppn de outra versão')
    monkeypatch.setattr(ativacao, 'conferir', recusa)
    r = TestClient(main.app).put('/ativacao/palavra', content=b'x' * 100)
    assert r.status_code == 400 and r.json()['erro'] == 'modelo_recusado'
    assert list(tmp_path.iterdir()) == []


def test_chave_recusada(monkeypatch, tmp_path):
    monkeypatch.setattr(ativacao, 'PALAVRA', tmp_path / 'solis.ppn')
    (tmp_path / 'solis.ppn').write_bytes(b'x')

    def recusa(k, p):
        raise ativacao.ChaveRecusada('AccessKey inválida')
    monkeypatch.setattr(ativacao, 'conferir', recusa)
    r = TestClient(main.app).put('/ativacao/chave', json={'chave': 'ruim'})
    assert r.status_code == 400 and r.json()['erro'] == 'chave_recusada'
    assert ativacao.chave() is None


def test_websocket_ativa_transcreve_e_respeita_a_pausa(monkeypatch):
    motor = MotorFalso()
    original = ativacao.Escuta
    monkeypatch.setattr(ativacao, 'Escuta', lambda: original(motor))

    async def transcrever(audio, **_):
        assert audio[:4] == b'RIFF'
        return {'texto': 'me lembra de pagar a luz'}
    monkeypatch.setattr(voz, 'transcrever', transcrever)
    c = TestClient(main.app)
    with c.websocket_connect('/escuta') as ws:
        assert ws.receive_json() == {'tipo': 'pronta'}  # só agora a tela abre o microfone
        ws.send_text('{"pausa": true}')
        ws.send_bytes(palavra().tobytes())  # pausada: a palavra não conta
        ws.send_text('{"pausa": false}')
        ws.send_bytes((palavra() + quadros(1) + quadros(1.2, tom=False)).tobytes())
        assert ws.receive_json() == {'tipo': 'ativou'}
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'me lembra de pagar a luz'}
    assert motor.apagado


def test_websocket_sem_configuracao_avisa_e_fecha(monkeypatch):
    monkeypatch.setattr(voz, 'disponivel', lambda: False)
    c = TestClient(main.app)
    with c.websocket_connect('/escuta') as ws:
        msg = ws.receive_json()
    assert msg['tipo'] == 'erro' and 'falta' in msg['motivo']


# — Motor Whisper ————————————————————————————————————————————————————————————————

@pytest.mark.parametrize('texto, esperado', [
    ('Solis, me lembra de pagar a luz.', (True, 'Me lembra de pagar a luz.')),
    ('Sólis!', (True, '')),
    ('Ei, Solís, que horas são?', (True, 'Que horas são?')),
    ('Sollis marca dentista', (True, 'Marca dentista')),
    ('O sol está forte.', (False, 'O sol está forte.')),
    ('A solidão faz bem.', (False, 'A solidão faz bem.')),
    ('Isso é sólido.', (False, 'Isso é sólido.')),
    ('Me passa o Solis aí.', (False, 'Me passa o Solis aí.')),
    # 16/11/2026, a voz do Matheus: "Ei Solis" virou isto.
    ('É isso, Solis.', (True, '')),
    ('Olha, Solis, abre a agenda.', (True, 'Abre a agenda.')),
    ('Eu falei com o Solis ontem.', (False, 'Eu falei com o Solis ontem.')),
    ('Solidão, Solistas, Sólido.', (False, 'Solidão, Solistas, Sólido.')),
])
def test_palavra_no_inicio(texto, esperado):
    assert ativacao.palavra_no_inicio(texto) == esperado


def fala_com_silencio(segundos):
    return quadros(0.5, tom=False) + quadros(segundos) + quadros(ativacao.FIM_SILENCIO + 0.2, tom=False)


def test_whisper_trecho_curto_vai_inteiro_quando_acaba(monkeypatch):
    monkeypatch.setattr(ativacao, 'RASCUNHO_SILENCIO', 99.0)  # sem a cascata (o fim do trecho, como antes)
    e = ativacao.Escuta(whisper=True)
    eventos = list(e.alimentar(fala_com_silencio(1.0).tobytes()))
    assert [t for t, _ in eventos] == ['frase']
    # Leva um pouco do antes (o "S" de Solis começa baixo) e a fala inteira.
    seg = (len(eventos[0][1]) - 44) / 2 / TAXA
    assert 1.0 + 0.2 <= seg <= 1.0 + ativacao.ANTES + ativacao.FIM_SILENCIO + 0.1


def test_whisper_trecho_longo_manda_a_previa_e_confirmado_vira_comando():
    e = ativacao.Escuta(whisper=True)
    eventos = []
    for ev in e.alimentar(fala_com_silencio(4.0).tobytes()):
        if ev[0] == 'rascunho':
            continue
        eventos.append(ev)
        if ev[0] == 'previa':
            assert ativacao.PREVIA <= (len(ev[1]) - 44) / 2 / TAXA < ativacao.PREVIA + 0.1
            e.confirmar()
    assert [t for t, _ in eventos] == ['previa', 'comando']
    # O comando é o trecho inteiro, com o começo que já tinha ido na prévia.
    assert (len(eventos[1][1]) - 44) / 2 / TAXA >= 4.0


def test_whisper_sem_a_palavra_o_trecho_e_ignorado_ate_acabar(monkeypatch):
    monkeypatch.setattr(ativacao, 'RASCUNHO_SILENCIO', 99.0)  # sem a cascata (o fim do trecho, como antes)
    e = ativacao.Escuta(whisper=True)
    eventos = []
    for ev in e.alimentar((fala_com_silencio(4.0) + fala_com_silencio(1.0)).tobytes()):
        eventos.append(ev[0])
        e.descartar()
    # A TV falando: uma prévia por trecho, e o trecho seguinte é conferido de novo.
    assert eventos == ['previa', 'frase'] and e.comando is None and e.trechos == 2


def test_whisper_so_a_palavra_e_depois_o_comando():
    e = ativacao.Escuta(whisper=True)
    eventos = []
    audio = fala_com_silencio(0.6) + quadros(1.0) + quadros(ativacao.FIM_SILENCIO + 0.2, tom=False)
    for ev in e.alimentar(audio.tobytes()):
        if ev[0] == 'rascunho':
            continue
        eventos.append(ev[0])
        if ev[0] == 'frase':
            e.confirmar()  # só "Solis": sem o resto
    assert eventos == ['frase', 'comando']


def test_whisper_estalo_nao_vai_pro_whisper():
    e = ativacao.Escuta(whisper=True)
    assert list(e.alimentar(fala_com_silencio(0.1).tobytes())) == []


def test_websocket_whisper_acha_a_palavra_e_manda_o_comando(monkeypatch):
    original = ativacao.Escuta
    monkeypatch.setattr(ativacao, 'Escuta', lambda: original(whisper=True))
    # A fala sem "Solis" vai duas vezes pro Whisper: cedo e, inteira, no fim (RECONFERIR).
    respostas = iter(['O sol está forte.', 'O sol está forte.', 'Solis, que horas são?', 'Solis',
                      'me lembra de pagar a luz'])

    async def transcrever(audio, **_):
        return {'texto': next(respostas)}
    monkeypatch.setattr(voz, 'transcrever', transcrever)
    c = TestClient(main.app)
    with c.websocket_connect('/escuta') as ws:
        assert ws.receive_json() == {'tipo': 'pronta'}
        ws.send_bytes(fala_com_silencio(1.0).tobytes())  # sem a palavra: nada volta
        ws.send_bytes(fala_com_silencio(1.0).tobytes())  # "Solis, que horas são?" de uma vez
        assert ws.receive_json() == {'tipo': 'ativou'}
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'Que horas são?'}
        ws.send_bytes(fala_com_silencio(0.6).tobytes())  # "Solis" e uma pausa
        assert ws.receive_json() == {'tipo': 'ativou'}
        ws.send_bytes(fala_com_silencio(1.0).tobytes())
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'me lembra de pagar a luz'}


def test_eco_do_vocabulario_nao_e_fala():
    vocab = 'Matheus, Solis, Ollama, Claude, Codex.'
    assert voz.eco_do_vocabulario('Matheus, Solis, Ollama, Claude, Ollama.', vocab)
    assert not voz.eco_do_vocabulario('Solis.', vocab)
    assert not voz.eco_do_vocabulario('Solis, pergunta pro Claude o que ele acha.', vocab)
    assert not voz.eco_do_vocabulario('Matheus Solis Ollama', None)


def test_trecho_baixo_e_normalizado_pro_whisper():
    baixo = array.array('h', [int(1000 * math.sin(2 * math.pi * 300 * i / TAXA)) for i in range(TAXA // 2)])
    alto = ativacao._normalizar(baixo)
    assert max(abs(a) for a in alto) == pytest.approx(ativacao.PICO_ALVO * 32767, rel=0.02)
    # O que já está alto não muda, e o silêncio absoluto também não.
    forte = array.array('h', [30000, -30000])
    assert ativacao._normalizar(forte) == forte
    assert ativacao._normalizar(array.array('h', [0, 0])) == array.array('h', [0, 0])


def test_whisper_decisao_demorada_estica_o_prazo_do_pedido():
    """16/11/2026: o Whisper frio levou ~7 s pra decidir. O áudio desse tempo
    fica na fila, e quem chamou só fala depois do bipe: o prazo pra começar o
    pedido conta a partir dele."""
    atraso = 6.0
    # Silêncio até 2 s depois do prazo de sempre (e antes do prazo esticado), e o pedido.
    audio = fala_com_silencio(0.6) + quadros(ativacao.INICIO_MAX + 2.0, tom=False) \
        + quadros(1.0) + quadros(ativacao.FIM_SILENCIO + 0.2, tom=False)
    for demora, esperado in ((0.0, None), (atraso, 'pedido')):
        e = ativacao.Escuta(whisper=True)
        comando = 'sem'
        for tipo, wav in e.alimentar(audio.tobytes()):
            if tipo == 'frase':
                e.confirmar(atraso=demora)
            elif tipo == 'comando':
                comando = wav
                break
        if esperado is None:
            assert comando is None  # desistiu antes do pedido chegar
        else:
            assert comando not in (None, 'sem') and (len(comando) - 44) / 2 / TAXA >= 1.0


def test_whisper_o_atraso_tem_teto():
    e = ativacao.Escuta(whisper=True)
    e.confirmar(atraso=120.0)
    assert e.espera_extra == ativacao.ATRASO_MAX


def test_websocket_segura_o_whisper_enquanto_a_escuta_esta_aberta(monkeypatch):
    original = ativacao.Escuta
    monkeypatch.setattr(ativacao, 'Escuta', lambda: original(whisper=True))
    aquecidos = []
    monkeypatch.setattr(voz, 'aquecer', lambda: aquecidos.append(1))
    c = TestClient(main.app)
    with c.websocket_connect('/escuta') as ws:
        assert ws.receive_json() == {'tipo': 'pronta'}
        assert voz._segurando == 1
    import time as _t
    fim = _t.monotonic() + 2
    while voz._segurando and _t.monotonic() < fim:
        _t.sleep(0.02)
    assert voz._segurando == 0 and aquecidos == [1]


# — A cascata (16/11/2026) ————————————————————————————————————————————————————

def _rodar(e, audio, transcreve):
    """Como o laço do /escuta: cada evento com o momento (em s de áudio) em que saiu."""
    eventos, t = [], 0.0
    for ev in e.alimentar(audio.tobytes()):
        tipo, wav = ev
        t = (len(e.comando or []) / TAXA)  # só pra depurar
        eventos.append(tipo)
        if tipo in ('previa', 'frase'):
            achou, resto = ativacao.palavra_no_inicio(transcreve(tipo, wav))
            if not achou:
                e.descartar()
                continue
            pronto = e.confirmar(resto=resto if tipo == 'frase' else '')
            if pronto:
                eventos.append(('texto', pronto))
        elif tipo == 'rascunho':
            e.guardar_rascunho(ativacao.palavra_no_inicio(transcreve(tipo, wav))[1])
        elif tipo == 'comando':
            eventos.append(('pronto', e.pronto))
    return eventos


def _seg(wav):
    return (len(wav) - 44) / 2 / TAXA


def test_cascata_pergunta_inteira_sai_no_fim_cedo_sem_transcrever_de_novo():
    """"Solis, que horas são?" e silêncio: conferido com RASCUNHO_SILENCIO, o
    texto já é o comando, e por ser pergunta acaba em FIM_CEDO."""
    e = ativacao.Escuta(whisper=True)
    pedidos = []

    def transcreve(tipo, wav):
        pedidos.append((tipo, round(_seg(wav), 1)))
        return 'Solis, que horas são?'
    audio = quadros(0.5, tom=False) + quadros(1.2) + quadros(2.0, tom=False)
    comandos = []
    for ev in e.alimentar(audio.tobytes()):
        if ev[0] == 'frase':
            assert e.confirmar(resto=ativacao.palavra_no_inicio(transcreve(*ev))[1]) is None
        elif ev[0] == 'comando':
            comandos.append((ev[1], e.pronto))
        else:
            raise AssertionError(ev[0])
    # Um Whisper só, no trecho conferido cedo.
    assert [t for t, _ in pedidos] == ['frase']
    [(wav, pronto)] = comandos
    assert pronto == 'Que horas são?'
    # O comando acabou em FIM_CEDO de silêncio, não em FIM_SILENCIO.
    fala = 1.2 + 0.5  # o antes guardado é o meio segundo de silêncio que havia
    assert fala + ativacao.FIM_CEDO - 0.1 <= _seg(wav) <= fala + ativacao.FIM_CEDO + 0.1


def test_cascata_sem_pergunta_espera_o_silencio_inteiro_mas_nao_transcreve_de_novo():
    e = ativacao.Escuta(whisper=True)
    pedidos = []

    def transcreve(tipo, wav):
        pedidos.append(tipo)
        return 'Solis, me lembra de pagar a luz.'
    audio = quadros(0.5, tom=False) + quadros(1.5) + quadros(2.0, tom=False)
    eventos = _rodar(e, audio, transcreve)
    assert eventos == ['frase', 'comando', ('pronto', 'Me lembra de pagar a luz.')]
    assert pedidos == ['frase']


def test_cascata_voltou_a_falar_o_rascunho_nao_vale():
    """"Solis, me lembra..." (pausa) "...de pagar a luz": o rascunho da pausa
    fica velho, e o comando inteiro vai pro Whisper no fim."""
    e = ativacao.Escuta(whisper=True)
    pedidos = []

    def transcreve(tipo, wav):
        pedidos.append(tipo)
        return 'Solis, me lembra' if tipo == 'frase' else 'Solis, me lembra de pagar a luz.'
    audio = (quadros(0.5, tom=False) + quadros(1.0) + quadros(0.6, tom=False) + quadros(1.0)
             + quadros(2.0, tom=False))
    eventos = _rodar(e, audio, transcreve)
    # A pausa de 0,6 s não encerra; depois, o rascunho da fala inteira vale.
    assert eventos == ['frase', 'rascunho', 'comando', ('pronto', 'Me lembra de pagar a luz.')]
    assert pedidos == ['frase', 'rascunho']


def test_cascata_so_solis_espera_o_pedido_depois_do_bipe():
    e = ativacao.Escuta(whisper=True)

    def transcreve(tipo, wav):
        return 'Solis.' if tipo == 'frase' else 'Que horas são?'
    audio = quadros(0.5, tom=False) + quadros(0.6) + quadros(1.5, tom=False) + quadros(1.0) + quadros(2.0, tom=False)
    eventos = _rodar(e, audio, transcreve)
    assert eventos == ['frase', 'rascunho', 'comando', ('pronto', 'Que horas são?')]


def test_cascata_conferido_cedo_sem_a_palavra_confere_de_novo_se_ele_continuar():
    """"Bom dia" (pausa curta) "Solis, que horas são?": a conferência cedo não
    acha a palavra, mas ele continuou — o trecho inteiro é conferido no fim."""
    e = ativacao.Escuta(whisper=True)
    pedidos = []

    def transcreve(tipo, wav):
        pedidos.append(tipo)
        return 'Bom dia.' if len(pedidos) == 1 else 'Bom dia, Solis, que horas são?'
    audio = (quadros(0.5, tom=False) + quadros(0.6) + quadros(0.5, tom=False) + quadros(1.0)
             + quadros(2.0, tom=False))
    eventos = _rodar(e, audio, transcreve)
    # Continuou: a prévia (já com 2 s) acha a palavra, e o pedido sai inteiro.
    assert eventos == ['frase', 'previa', 'rascunho', 'comando', ('pronto', 'Que horas são?')]


def test_cascata_sem_a_palavra_confere_de_novo_no_fim(monkeypatch):
    """16/11/2026, a voz do Matheus: "Solis, desliga a música" virou "Sani,
    Zizlega" na conferência cedo; no fim, inteiro, o Whisper acerta."""
    e = ativacao.Escuta(whisper=True)
    pedidos = []

    def transcreve(tipo, wav):
        pedidos.append(tipo)
        return 'Sani, Zizlega, Muzica.' if len(pedidos) == 1 else 'Solis, desliga a música.'
    eventos = _rodar(e, quadros(0.5, tom=False) + quadros(1.0) + quadros(2.0, tom=False), transcreve)
    assert eventos == ['frase', 'frase', ('texto', 'Desliga a música.')] and pedidos == ['frase', 'frase']
    # Sem reconferir: uma conferência só, e a chamada se perdia.
    monkeypatch.setattr(ativacao, 'RECONFERIR', False)
    e, pedidos[:] = ativacao.Escuta(whisper=True), []
    assert _rodar(e, quadros(0.5, tom=False) + quadros(1.0) + quadros(2.0, tom=False), transcreve) == ['frase']


@pytest.mark.parametrize('silencio', [0.0, 0.35, 0.352, 0.3520000001, 1 / 3, 0.8999999, 0.9, 1.2])
def test_completar_o_silencio_sempre_termina_e_no_tamanho_certo(silencio):
    """16/11/2026: em segundos float, uma sobra de fração de amostra virou laço
    sem fim e travou o servidor de verdade."""
    amostras = array.array('h', [5] * int(1.0 * TAXA))
    saida = ativacao._completado(amostras, silencio)
    falta = max(0, round((ativacao.FIM_SILENCIO - silencio) * TAXA)) if int(silencio * TAXA) else 0
    assert len(saida) == len(amostras) + falta


def test_o_limiar_da_fala_vale_o_de_agora(monkeypatch):
    """16/11/2026: o limiar era o valor padrão do argumento, congelado quando o
    módulo carregou — o teste da escuta mudava ACIMA_DO_PISO e nada mudava."""
    e = ativacao.Escuta(whisper=True)
    e.piso = -50.0
    assert not e._e_fala(-44.0)  # 6 dB acima do piso, com o limiar de 7
    monkeypatch.setattr(ativacao, 'ACIMA_DO_PISO', 5.0)
    assert e._e_fala(-44.0)


def test_escuta_rapida_desligada_nao_segura_o_whisper(monkeypatch):
    """17/11/2026: com a escuta rápida desligada (Configurações → Voz), o Whisper
    não fica preso na placa (1,2 GB) — sai depois de 10 min parado, como antes."""
    original = ativacao.Escuta
    monkeypatch.setattr(ativacao, 'Escuta', lambda: original(whisper=True))
    aquecidos = []
    monkeypatch.setattr(voz, 'aquecer', lambda: aquecidos.append(1))
    c = TestClient(main.app)
    with c.websocket_connect('/escuta?segurar=0') as ws:
        assert ws.receive_json() == {'tipo': 'pronta'}
        assert voz._segurando == 0
    assert voz._segurando == 0 and aquecidos == [1]  # aquece igual: a primeira chamada já acha ele


def test_depois_de_uma_pergunta_o_pedido_abre_sem_a_palavra():
    """17/11/2026: o Solis perguntou "qual música?", o Matheus respondeu, e a
    escuta esperava o "Solis" de novo. Agora a resposta dele já é o pedido."""
    e = ativacao.Escuta(whisper=True)
    assert e.seguir() and e.ativacoes == 1
    assert not e.seguir()  # pedido já aberto: nada muda
    eventos = [ev for ev in e.alimentar((quadros(1.0) + quadros(ativacao.FIM_SILENCIO + 0.2, tom=False)).tobytes())
               if ev[0] != 'rascunho']
    assert [t for t, _ in eventos] == ['comando'] and (len(eventos[0][1]) - 44) / 2 / TAXA >= 1.0
    # Calado depois da pergunta: desiste no prazo de sempre, e volta a esperar o "Solis".
    e.seguir()
    eventos = list(e.alimentar(quadros(ativacao.INICIO_MAX + 0.5, tom=False).tobytes()))
    assert eventos == [('comando', None)] and e.comando is None


def test_websocket_seguir_abre_o_pedido_e_pausado_nao(monkeypatch):
    original = ativacao.Escuta
    monkeypatch.setattr(ativacao, 'Escuta', lambda: original(whisper=True))
    respostas = iter(['Toca Legião Urbana.'])

    async def transcrever(audio, **_):
        return {'texto': next(respostas)}
    monkeypatch.setattr(voz, 'transcrever', transcrever)
    c = TestClient(main.app)
    with c.websocket_connect('/escuta') as ws:
        assert ws.receive_json() == {'tipo': 'pronta'}
        ws.send_text('{"pausa": true, "seguir": true}')  # ainda falando: não abre
        ws.send_text('{"pausa": false, "seguir": true}')
        assert ws.receive_json() == {'tipo': 'ativou'}
        ws.send_bytes((quadros(1.0) + quadros(ativacao.FIM_SILENCIO + 0.2, tom=False)).tobytes())
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'Toca Legião Urbana.'}
