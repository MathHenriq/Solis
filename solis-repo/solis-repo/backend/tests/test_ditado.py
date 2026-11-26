"""O ditado pelo microfone direto do Windows (main.ditado, 22/11/2026): aberto na
janela, o microfone estragava o som do Discord, como já tinha acontecido com a
escuta. O microfone é simulado: nenhum teste abre o do PC."""
import time

import numpy as np
from fastapi.testclient import TestClient

from solis import ativacao, main, microfone, microfone_nativo, transcricao


class MicrofoneFalso:
    abertos, fechados = [], []
    segundos = 1.0

    def abrir(self, laco, fila):
        MicrofoneFalso.abertos.append(self)
        som = (np.sin(np.arange(int(ativacao.TAXA * self.segundos)) / 8) * 8000).astype(np.int16).tobytes()
        for k in range(0, len(som), 2048):
            laco.call_soon_threadsafe(fila.put_nowait, som[k:k + 2048])

    def fechar(self):
        MicrofoneFalso.fechados.append(self)


def _com_nativo(monkeypatch, segundos=1.0):
    MicrofoneFalso.abertos, MicrofoneFalso.fechados, MicrofoneFalso.segundos = [], [], segundos
    monkeypatch.setattr(microfone, 'NATIVO', True)
    monkeypatch.setattr(microfone_nativo, 'Gravador', MicrofoneFalso)
    ouvidos = []

    async def escuta(tipo, audio):
        ouvidos.append((tipo, audio))
        return '  Me lembra de pagar a luz amanhã.  '
    monkeypatch.setattr(transcricao, 'escuta', escuta)
    return ouvidos


def test_o_ditado_grava_pelo_windows_e_transcreve_online_primeiro(monkeypatch):
    ouvidos = _com_nativo(monkeypatch)
    with TestClient(main.app).websocket_connect('/voz/ditado') as ws:
        assert ws.receive_json() == {'tipo': 'ouvindo'}
        ws.send_json({'parar': True})
        assert ws.receive_json() == {'tipo': 'texto', 'texto': 'Me lembra de pagar a luz amanhã.'}
    # O caminho da escuta: o privado conferido aqui, o resto pela Groq, o turbo sem internet.
    [(tipo, audio)] = ouvidos
    assert tipo == 'comando' and audio[:4] == b'RIFF' and len(audio) > ativacao.TAXA * 2 * 0.9
    assert len(MicrofoneFalso.abertos) == 1 and len(MicrofoneFalso.fechados) == 1


def test_desistir_fecha_o_microfone_sem_mandar_nada(monkeypatch):
    ouvidos = _com_nativo(monkeypatch)
    with TestClient(main.app).websocket_connect('/voz/ditado') as ws:
        assert ws.receive_json()['tipo'] == 'ouvindo'
        ws.send_json({'cancelar': True})
    # Quem fecha o microfone é o servidor, logo depois da conexão: no Linux do
    # GitHub (26/11/2026) o teste conferia antes de ele chegar lá. Espera até 2 s.
    fim = time.monotonic() + 2
    while not MicrofoneFalso.fechados and time.monotonic() < fim:
        time.sleep(0.02)
    assert ouvidos == [] and len(MicrofoneFalso.fechados) == 1


def test_curto_demais_e_nao_ouvi_nada(monkeypatch):
    ouvidos = _com_nativo(monkeypatch, segundos=0.1)
    with TestClient(main.app).websocket_connect('/voz/ditado') as ws:
        ws.receive_json()
        ws.send_json({'parar': True})
        assert ws.receive_json() == {'tipo': 'erro', 'estado': 'vazio'}
    assert ouvidos == []


def test_sem_o_microfone_do_windows_a_tela_grava_pela_dela():
    # O conftest desliga o nativo (microfone.NATIVO = False), como fora do Windows.
    with TestClient(main.app).websocket_connect('/voz/ditado') as ws:
        assert ws.receive_json() == {'tipo': 'sem_nativo'}
