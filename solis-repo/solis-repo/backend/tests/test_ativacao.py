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
    eventos = list(e.alimentar(audio.tobytes()))
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
        eventos += list(e.alimentar(audio[i:i + 333]))
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

    async def transcrever(audio):
        assert audio[:4] == b'RIFF'
        return {'texto': 'me lembra de pagar a luz'}
    monkeypatch.setattr(voz, 'transcrever', transcrever)
    c = TestClient(main.app)
    with c.websocket_connect('/escuta') as ws:
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
])
def test_palavra_no_inicio(texto, esperado):
    assert ativacao.palavra_no_inicio(texto) == esperado


def fala_com_silencio(segundos):
    return quadros(0.5, tom=False) + quadros(segundos) + quadros(ativacao.FIM_SILENCIO + 0.2, tom=False)


def test_whisper_trecho_curto_vai_inteiro_quando_acaba():
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
        eventos.append(ev)
        if ev[0] == 'previa':
            assert ativacao.PREVIA <= (len(ev[1]) - 44) / 2 / TAXA < ativacao.PREVIA + 0.1
            e.confirmar()
    assert [t for t, _ in eventos] == ['previa', 'comando']
    # O comando é o trecho inteiro, com o começo que já tinha ido na prévia.
    assert (len(eventos[1][1]) - 44) / 2 / TAXA >= 4.0


def test_whisper_sem_a_palavra_o_trecho_e_ignorado_ate_acabar():
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
        eventos.append(ev[0])
        if ev[0] == 'frase':
            e.confirmar()
    assert eventos == ['frase', 'comando']


def test_whisper_estalo_nao_vai_pro_whisper():
    e = ativacao.Escuta(whisper=True)
    assert list(e.alimentar(fala_com_silencio(0.1).tobytes())) == []


def test_websocket_whisper_acha_a_palavra_e_manda_o_comando(monkeypatch):
    original = ativacao.Escuta
    monkeypatch.setattr(ativacao, 'Escuta', lambda: original(whisper=True))
    respostas = iter(['O sol está forte.', 'Solis, que horas são?', 'Solis', 'me lembra de pagar a luz'])

    async def transcrever(audio):
        return {'texto': next(respostas)}
    monkeypatch.setattr(voz, 'transcrever', transcrever)
    c = TestClient(main.app)
    with c.websocket_connect('/escuta') as ws:
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
