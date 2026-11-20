"""A palavra treinada (openWakeWord): um modelo pequeno que só sabe ouvir
"Solis", na CPU, sem internet e sem API — o lugar do Whisper conferindo cada
trecho de fala (ativacao.py), que erra mais com barulho e põe a placa pra
trabalhar o tempo todo com gente conversando em volta (relato do Matheus,
20/11/2026).

O caminho é o do openWakeWord (github.com/dscripka/openWakeWord), feito aqui só
com o onnxruntime e o numpy (já vêm com o faster-whisper; o pacote dele puxaria
scipy e scikit-learn): o áudio (16 kHz, 16 bits) vira melespectrograma
(melspectrogram.onnx), o melespectrograma vira um vetor de 96 números a cada 80
ms (embedding_model.onnx, a mesma "espinha" pra qualquer palavra), e o modelo
da palavra olha os últimos 16 vetores (1,28 s) e dá uma nota de 0 a 1. As duas
peças de cima são as da versão 0.5.1, baixadas da página oficial; o modelo da
palavra é treinado no Colab (o treinador só roda no Linux).
"""
from __future__ import annotations

import os
from collections import deque
from pathlib import Path

import numpy as np

PASTA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Solis' / 'voz' / 'openwakeword'
MELS = 'melspectrogram.onnx'
ESPINHA = 'embedding_model.onnx'
QUADRO = 1280          # 80 ms a 16 kHz: o passo do openWakeWord
JANELA_MEL = 76        # quadros de melespectrograma por vetor
PASSO_MEL = 8          # quadros de mel a cada 80 ms
VETORES = 16           # quantos vetores o modelo da palavra olha
LIMIAR = 0.5           # o do openWakeWord pros modelos dele; o nosso sai da medição


class SemModelo(Exception):
    pass


def _sessao(caminho: Path):
    import onnxruntime as ort
    if not caminho.is_file():
        raise SemModelo(f'falta {caminho.name} em {caminho.parent}')
    opcoes = ort.SessionOptions()
    opcoes.inter_op_num_threads = opcoes.intra_op_num_threads = 1
    return ort.InferenceSession(str(caminho), sess_options=opcoes, providers=['CPUExecutionProvider'])


class Ouvido:
    """Ouve uma palavra, quadro a quadro. `alimentar(pcm int16)` devolve as
    notas (uma a cada 80 ms de áudio que completou)."""

    def __init__(self, modelo: Path | str, pasta: Path | None = None):
        pasta = pasta or PASTA
        self._mels = _sessao(pasta / MELS)
        self._espinha = _sessao(pasta / ESPINHA)
        self._palavra = _sessao(Path(modelo) if Path(modelo).is_absolute() else pasta / modelo)
        self._entrada_mels = self._mels.get_inputs()[0].name
        self._entrada_espinha = self._espinha.get_inputs()[0].name
        self._entrada_palavra = self._palavra.get_inputs()[0].name
        self.zerar()

    def zerar(self):
        """Começa do zero (o buffer de áudio, o de mel e os vetores), como o
        openWakeWord: o começo é ruído, pra nota não nascer alta."""
        self._bruto: deque = deque(maxlen=16000 * 10)
        self._sobra = np.zeros(0, dtype=np.int16)
        self._mel = np.ones((JANELA_MEL, 32), dtype=np.float32)
        ruido = np.random.default_rng(0).integers(-1000, 1000, 16000 * 4).astype(np.int16)
        self._vetores = self._vetores_de(ruido)

    def _mel_de(self, amostras: np.ndarray) -> np.ndarray:
        x = amostras.astype(np.float32)[None, :]
        saida = self._mels.run(None, {self._entrada_mels: x})[0]
        return np.squeeze(saida) / 10 + 2  # a transformação do openWakeWord

    def _vetor_de(self, janela: np.ndarray) -> np.ndarray:
        saida = self._espinha.run(None, {self._entrada_espinha: janela[None, :, :, None].astype(np.float32)})[0]
        return np.squeeze(saida).reshape(-1, 96)

    def _vetores_de(self, amostras: np.ndarray) -> np.ndarray:
        mel = self._mel_de(amostras)
        janelas = [mel[i:i + JANELA_MEL] for i in range(0, mel.shape[0] - JANELA_MEL + 1, PASSO_MEL)]
        return np.vstack([self._vetor_de(j) for j in janelas])

    def alimentar(self, pcm: np.ndarray) -> list[float]:
        pcm = np.concatenate([self._sobra, np.asarray(pcm, dtype=np.int16)])
        inteiros = len(pcm) // QUADRO * QUADRO
        self._sobra = pcm[inteiros:]
        notas = []
        for i in range(0, inteiros, QUADRO):
            quadro = pcm[i:i + QUADRO]
            self._bruto.extend(quadro.tolist())
            # O mel do quadro novo com 3 passos (30 ms) de antes: o openWakeWord faz assim.
            contexto = np.array(list(self._bruto)[-(QUADRO + 160 * 3):], dtype=np.int16)
            self._mel = np.vstack([self._mel, self._mel_de(contexto)])[-10 * 97:]
            if self._mel.shape[0] >= JANELA_MEL:
                self._vetores = np.vstack([self._vetores, self._vetor_de(self._mel[-JANELA_MEL:])])[-120:]
            entrada = self._vetores[-VETORES:][None, :, :].astype(np.float32)
            notas.append(float(np.squeeze(self._palavra.run(None, {self._entrada_palavra: entrada})[0])))
        return notas
