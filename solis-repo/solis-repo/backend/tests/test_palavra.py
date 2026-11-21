"""A palavra treinada (solis/palavra.py): o caminho do openWakeWord feito só com
o onnxruntime. Conferido com o modelo pronto "hey jarvis" quando as peças estão
neste PC (baixadas da página oficial, v0.5.1); sem elas, só o que não precisa."""
import numpy as np
import pytest

from solis import palavra

TEM = all((palavra.PASTA / n).is_file() for n in (palavra.MELS, palavra.ESPINHA, 'hey_jarvis_v0.1.onnx'))


def test_sem_as_pecas_diz_o_que_falta(tmp_path):
    with pytest.raises(palavra.SemModelo, match='melspectrogram.onnx'):
        palavra.Ouvido('solis.onnx', tmp_path)


@pytest.mark.skipif(not TEM, reason='as peças do openWakeWord não estão neste PC')
def test_uma_nota_a_cada_80_ms_e_silencio_da_nota_baixa():
    o = palavra.Ouvido('hey_jarvis_v0.1.onnx')
    notas = o.alimentar(np.zeros(16000, dtype=np.int16))  # 1 s = 12 quadros de 80 ms (sobram 640 amostras)
    assert len(notas) == 12 and max(notas) < 0.1
    assert len(o.alimentar(np.zeros(640, dtype=np.int16))) == 1  # a sobra completa o 13º
    ruido = np.random.default_rng(1).integers(-3000, 3000, 32000).astype(np.int16)
    assert max(o.alimentar(ruido)) < 0.5


def test_a_camada_treinada_aqui_da_a_mesma_nota_do_treino(tmp_path):
    """O modelo do "Solis" treinado no PC (design/gravar-solis/treinar_local.py,
    numpy, .npz): a nota dentro do Solis é a mesma conta do treino."""
    rng = np.random.default_rng(3)
    pesos = {'W1': rng.standard_normal((1536, 8)).astype(np.float32), 'b1': rng.standard_normal(8).astype(np.float32),
             'W2': rng.standard_normal((8, 1)).astype(np.float32), 'b2': np.zeros(1, np.float32),
             'media': rng.standard_normal(1536).astype(np.float32), 'desvio': np.ones(1536, np.float32)}
    np.savez(tmp_path / 'solis.npz', **pesos)
    camada = palavra._Camada(tmp_path / 'solis.npz')
    x = rng.standard_normal((1, 16, 96)).astype(np.float32)
    z = x.reshape(1, -1) - pesos['media']
    esperado = 1 / (1 + np.exp(-(np.maximum(z @ pesos['W1'] + pesos['b1'], 0) @ pesos['W2'])[0, 0]))
    assert abs(camada.nota(x) - esperado) < 1e-5
    with pytest.raises(palavra.SemModelo, match='solis.npz'):
        palavra._Camada(tmp_path / 'nao' / 'solis.npz')


def test_a_escuta_sem_a_palavra_treinada_segue_sem_sombra(monkeypatch):
    from solis import main
    monkeypatch.setenv('SOLIS_PALAVRA_SOMBRA', '0')
    assert main._palavra_sombra() is None


def test_a_amostra_ao_vivo_fica_no_pc_com_teto(monkeypatch, tmp_path):
    """Autorizado pelo Matheus (21/11/2026): o trecho com o "Solis" ao vivo fica
    na pasta de voz dele, pra treinar o detector; nunca sai do PC; e tem teto."""
    import wave

    from solis import main
    monkeypatch.setattr(main, 'AMOSTRAS_VIVAS', tmp_path)
    monkeypatch.setattr(main, 'AMOSTRAS_VIVAS_MAX', 3)
    pcm = (np.sin(np.arange(16000) / 5) * 3000).astype(np.int16)
    for _ in range(5):
        main._guardar_amostra_viva('whisper', pcm, 0.0)
    guardadas = sorted((tmp_path / 'vivo-whisper').glob('*.wav'))
    assert 1 <= len(guardadas) <= 3
    with wave.open(str(guardadas[-1])) as w:
        assert (w.getframerate(), w.getnchannels(), w.getnframes()) == (16000, 1, 16000)
    monkeypatch.setenv('SOLIS_AMOSTRAS_VIVAS', '0')
    main._guardar_amostra_viva('palavra', pcm, 0.9)
    assert not (tmp_path / 'vivo-palavra').exists()
