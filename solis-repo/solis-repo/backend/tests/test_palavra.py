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
