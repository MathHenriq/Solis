"""Voz: o áudio vira o som que o Whisper quer, a rota devolve o texto, e os
erros dizem o que faltou — sem carregar o Whisper de verdade."""
import io
import time
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from solis import main, voz


def wav(segundos=1.0, taxa=48000, canais=2) -> bytes:
    """Um tom de 440 Hz em estéreo a 48 kHz — o contrário do que o Whisper quer."""
    t = np.arange(int(segundos * taxa)) / taxa
    tom = (np.sin(2 * np.pi * 440 * t) * 0.5 * 32767).astype(np.int16)
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(canais)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(np.repeat(tom, canais).tobytes())
    return saida.getvalue()


class Segmento:
    def __init__(self, texto):
        self.text = texto


class Info:
    duration = 1.0


class ModeloFalso:
    def __init__(self):
        self.recebido = None

    def transcribe(self, som, **kw):
        self.recebido = (som, kw)
        return iter([Segmento(' Me lembra de pagar'), Segmento(' a luz dia 15. ')]), Info()


@pytest.fixture
def modelo(monkeypatch):
    falso = ModeloFalso()
    monkeypatch.setattr(voz, '_modelo', falso)
    # O falso é "o modelo em uso": senão o Solis trocaria pelo que está na pasta.
    monkeypatch.setattr(voz, '_carregado', voz.modelo_em_uso())
    return falso


def test_decodifica_pra_mono_16k_float():
    som = voz.decodificar(wav(segundos=1.0, taxa=48000, canais=2))
    assert som.dtype == np.float32 and som.ndim == 1
    assert abs(len(som) - 16000) <= 400  # 1 s a 16 kHz (o resampler guarda uns quadros)
    assert 0.4 < float(np.abs(som).max()) <= 1.0


def test_rota_devolve_o_texto_e_manda_o_som_certo(modelo):
    r = TestClient(main.app).post('/voz', content=wav())
    assert r.status_code == 200
    assert r.json()['texto'] == 'Me lembra de pagar a luz dia 15.'
    som, kw = modelo.recebido
    assert som.dtype == np.float32 and kw['language'] == 'pt' and kw['vad_filter'] is True


def test_audio_vazio_ou_quebrado_e_400(modelo):
    c = TestClient(main.app)
    assert c.post('/voz', content=b'').json()['erro'] == 'audio_ruim'
    assert c.post('/voz', content=b'isto nao e audio').json()['erro'] == 'audio_ruim'


def test_sem_modelo_e_503(monkeypatch, tmp_path):
    monkeypatch.setattr(voz, '_modelo', None)
    monkeypatch.setattr(voz, 'PASTA', tmp_path)
    c = TestClient(main.app)
    assert c.get('/voz').json() == {'disponivel': False, 'modelo': voz.MODELO}
    r = c.post('/voz', content=wav())
    assert r.status_code == 503 and r.json()['erro'] == 'sem_modelo'


def test_modelo_sai_da_memoria_depois_de_ocioso(modelo, monkeypatch):
    monkeypatch.setattr(voz, '_ultimo_uso', time.monotonic())
    assert voz.descarregar_se_ocioso() is False and voz._modelo is modelo
    monkeypatch.setattr(voz, '_ultimo_uso', time.monotonic() - voz.OCIOSO - 1)
    assert voz.descarregar_se_ocioso() is True and voz._modelo is None


def test_vocabulario_vem_dos_dados_do_solis():
    from solis import banco, conhecimento
    banco.adicionar_memoria('Trabalha na Syngenta como analista de dados.', 'Trabalho', False, None)
    banco.adicionar_memoria('Usa o FastAPI e o qwen3 no projeto.', 'Projeto Solis', False, None)
    conhecimento.adicionar('Anotações do TCC.md', b'texto')
    vocab = voz.vocabulario(['qwen3:8b', 'llama3.2:3b', 'embeddinggemma:latest'])
    termos = vocab.rstrip('.').split(', ')
    assert termos[:2] == ['Matheus', 'Solis']
    for t in ('Syngenta', 'FastAPI', 'qwen', 'llama', 'TCC'):
        assert t in termos, t
    # Começo de frase não é nome; modelo de embeddings não é vocabulário de fala.
    assert 'Trabalha' not in termos and 'embeddinggemma' not in termos
    assert len(termos) <= voz.VOCABULARIO_MAX


def test_vocabulario_vai_pro_whisper(modelo):
    from solis import banco
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    TestClient(main.app).post('/voz', content=wav())
    _, kw = modelo.recebido
    assert 'Syngenta' in kw['initial_prompt'] and kw['initial_prompt'].startswith('Matheus, Solis')


def test_gpu_que_falha_na_hora_de_transcrever_cai_pra_cpu(monkeypatch):
    """A cuBLAS só é carregada na primeira transcrição: é ali que a GPU falha."""
    class GpuQuebrada(ModeloFalso):
        def transcribe(self, som, **kw):
            raise RuntimeError('Library cublas64_12.dll is not found or cannot be loaded')

    criados = []

    class WhisperFalso:
        def __new__(cls, caminho, device, compute_type):
            criados.append((device, compute_type))
            return GpuQuebrada() if device == 'cuda' else ModeloFalso()

    import faster_whisper
    monkeypatch.setattr(faster_whisper, 'WhisperModel', WhisperFalso)
    monkeypatch.setattr(voz, 'disponivel', lambda: True)
    monkeypatch.setattr(voz, 'modelo_em_uso', lambda: voz.MODELO)  # "baixado", em qualquer máquina
    monkeypatch.setattr(voz, 'DISPOSITIVO', 'auto')
    monkeypatch.setattr(voz, '_modelo', None)
    monkeypatch.setattr(voz, '_sem_gpu', False)
    r = voz.transcrever_agora(wav())
    assert r['texto'] == 'Me lembra de pagar a luz dia 15.' and r['onde'] == 'cpu'
    assert criados == [('cuda', 'int8_float16'), ('cpu', 'int8')]
    # Daqui pra frente vai direto pra CPU.
    monkeypatch.setattr(voz, '_modelo', None)
    voz.transcrever_agora(wav())
    assert criados[-1] == ('cpu', 'int8')


def test_sem_o_escolhido_usa_a_melhor_reserva(monkeypatch, tmp_path):
    """16/11/2026: o turbo não estava no PC de verdade e a escuta nem começava."""
    from solis import voz
    monkeypatch.setattr(voz, 'PASTA', tmp_path)
    monkeypatch.setattr(voz, 'MODELO', 'faster-whisper-large-v3-turbo-ct2')
    assert voz.modelo_em_uso() is None
    for m in ('faster-whisper-small', 'faster-whisper-medium'):
        (tmp_path / m).mkdir()
        (tmp_path / m / 'model.bin').write_bytes(b'x')
    assert voz.modelo_em_uso() == 'faster-whisper-medium'
    (tmp_path / 'faster-whisper-large-v3-turbo-ct2').mkdir()
    (tmp_path / 'faster-whisper-large-v3-turbo-ct2' / 'model.bin').write_bytes(b'x')
    assert voz.modelo_em_uso() == 'faster-whisper-large-v3-turbo-ct2'


def test_modelo_segurado_nao_sai_da_memoria(modelo, monkeypatch):
    monkeypatch.setattr(voz, '_ultimo_uso', time.monotonic() - voz.OCIOSO - 1)
    voz.segurar()
    assert voz.descarregar_se_ocioso() is False and voz._modelo is modelo
    voz.soltar()
    # Solto, os 10 min contam a partir de agora.
    assert voz.descarregar_se_ocioso() is False
    monkeypatch.setattr(voz, '_ultimo_uso', time.monotonic() - voz.OCIOSO - 1)
    assert voz.descarregar_se_ocioso() is True


def test_aquecer_carrega_e_transcreve_silencio(monkeypatch):
    transcritos = []

    class Falso:
        def transcribe(self, som, **_):
            transcritos.append(len(som))
            return iter([]), None
    monkeypatch.setattr(voz, '_modelo', None)

    def carregar():
        voz._modelo = Falso()
        voz._carregado = voz.modelo_em_uso()
    monkeypatch.setattr(voz, '_carregar', carregar)
    voz._aquecer_de_verdade()
    assert isinstance(voz._modelo, Falso) and transcritos == [16000]
    voz._aquecer_de_verdade()  # já quente: não transcreve de novo
    assert transcritos == [16000]
