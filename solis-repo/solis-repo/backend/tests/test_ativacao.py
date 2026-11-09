"""A palavra de ativação: o motor ouve "Solis", o que vem depois vira comando
até a pessoa parar de falar, e o WebSocket leva isso ao navegador — com um
motor falso, sem a chave nem o modelo do Matheus."""
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
    assert e.alimentar(quadros(2).tobytes()) == []
    assert e.comando is None


def test_palavra_depois_fala_e_silencio_vira_comando():
    e = ativacao.Escuta(MotorFalso())
    audio = quadros(1, tom=False) + palavra() + quadros(1.5) + quadros(1.2, tom=False)
    eventos = e.alimentar(audio.tobytes())
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
        eventos += e.alimentar(audio[i:i + 333])
    assert [t for t, _ in eventos] == ['ativou', 'comando']


def test_palavra_sem_fala_depois_desiste():
    e = ativacao.Escuta(MotorFalso())
    eventos = e.alimentar((palavra() + quadros(ativacao.INICIO_MAX + 0.5, tom=False)).tobytes())
    assert eventos == [('ativou', None), ('comando', None)]


def test_fala_sem_fim_e_cortada_no_maximo():
    e = ativacao.Escuta(MotorFalso())
    eventos = e.alimentar((palavra() + quadros(ativacao.COMANDO_MAX + 1)).tobytes())
    assert [t for t, _ in eventos] == ['ativou', 'comando'] and eventos[1][1] is not None


def test_estado_e_chave_selada(monkeypatch, tmp_path):
    monkeypatch.setattr(ativacao, 'PASTA', tmp_path)
    monkeypatch.setattr(ativacao, 'PALAVRA', tmp_path / 'solis.ppn')
    monkeypatch.setattr(ativacao, 'IDIOMA', tmp_path / 'pt.pv')
    conferidos = []
    monkeypatch.setattr(ativacao, 'conferir', lambda k, p: conferidos.append((k, p.name)))
    c = TestClient(main.app)
    assert c.get('/ativacao').json() == {'chave': False, 'palavra': False, 'idioma': False}
    assert c.put('/ativacao/chave', json={'chave': '  minha-chave '}).json()['chave'] is True
    bruto = banco.ajuste(ativacao.CHAVE)
    if cofre.DISPONIVEL:
        assert cofre.selado(bruto)
    assert ativacao.chave() == 'minha-chave'
    # O modelo é conferido com a chave antes de ficar.
    assert c.put('/ativacao/palavra', content=b'PPN' * 100).json()['palavra'] is True
    assert conferidos == [('minha-chave', 'solis.ppn.novo')]
    assert c.delete('/ativacao').json() == {'chave': False, 'palavra': False, 'idioma': False}


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


def test_websocket_sem_configuracao_avisa_e_fecha():
    c = TestClient(main.app)
    with c.websocket_connect('/escuta') as ws:
        msg = ws.receive_json()
    assert msg['tipo'] == 'erro' and 'falta' in msg['motivo']
