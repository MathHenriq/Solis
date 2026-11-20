"""Monta o pacote do treino no Colab (design/_treino-solis/solis-treino.zip):

- confere cada gravação (tem voz? alta o bastante? o Whisper pequeno ouve
  "Solis"?) e cada exemplo de TTS que sobrou da conferência;
- separa o TESTE LOCAL: todos os "com pedido" (o caso mais real, nunca no
  treino) e uns de cada jeito, de cada pessoa/microfone — ficam só neste PC,
  pra medir o modelo depois (design/_treino-solis/teste-local.txt);
- corta o resto no trecho com voz (o treinador trabalha com janelas de 2 s e
  cortaria o começo de uma gravação longa) e repete as gravações reais algumas
  vezes (são poucas perto dos milhares de vozes sintéticas; o aumento — ruído,
  eco de sala — faz cada repetição sair diferente).

Uso: backend/.venv/Scripts/python design/gravar-solis/montar_pacote.py
"""
import io
import os
import random
import sys
import wave
import zipfile
from pathlib import Path

import numpy as np

GRAVACOES = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Solis' / 'voz' / 'amostras-solis'
TREINO = Path(__file__).resolve().parents[1] / '_treino-solis'
TTS = TREINO / 'positivos-tts'
NEGATIVOS = TREINO / 'negativos-tts'
REPETIR = 8                      # cada gravação real entra 8 vezes no treino
TESTE_POR_TIPO = {'pedido': 99, 'normal': 3, 'ei': 2, 'longe': 2, 'baixo': 1, 'animado': 1, 'devagar': 1}
MARGEM = int(0.15 * 16000)


def ler(p: Path) -> np.ndarray:
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def wav(pcm: np.ndarray) -> bytes:
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return saida.getvalue()


def trecho_com_voz(pcm: np.ndarray) -> tuple[np.ndarray, float]:
    """O pedaço com voz (quadros de 20 ms até 30 dB abaixo do mais forte), com
    150 ms de cada lado; e o pico em dBFS."""
    q = 320
    n = len(pcm) // q
    if n == 0:
        return pcm, -99.0
    quadros = pcm[:n * q].astype(np.float32).reshape(n, q) / 32768
    db = 20 * np.log10(np.sqrt((quadros ** 2).mean(axis=1)) + 1e-9)
    vozes = np.where(db > db.max() - 30)[0]
    ini, fim = max(0, vozes[0] * q - MARGEM), min(len(pcm), (vozes[-1] + 1) * q + MARGEM)
    return pcm[ini:fim], float(db.max())


def main():
    random.seed(20112026)
    teste, treino, problemas = [], [], []
    for pessoa in sorted(p for p in GRAVACOES.iterdir() if p.is_dir()):
        por_tipo: dict[str, list[Path]] = {}
        for f in sorted(pessoa.glob('*.wav')):
            por_tipo.setdefault(f.stem.split('-', 1)[1], []).append(f)
        for tipo, arquivos in por_tipo.items():
            random.shuffle(arquivos)
            n = min(TESTE_POR_TIPO.get(tipo, 1), len(arquivos))
            teste += arquivos[:n]
            treino += arquivos[n:]
        # Só o volume: a conferência pelo Whisper simples (beam 1, sem o
        # vocabulário) ouvia "Só isso" e enganou; a da escuta de verdade
        # acordou em 97 das 100 (20/11/2026).
        for f in sorted(pessoa.glob('*.wav')):
            _, pico = trecho_com_voz(ler(f))
            if pico < -45:
                problemas.append(f'{pessoa.name}/{f.name}: pico {pico:.0f} dBFS, baixo demais')
    TREINO.mkdir(exist_ok=True)
    (TREINO / 'teste-local.txt').write_text('\n'.join(str(f) for f in teste), encoding='utf-8')
    tts = sorted(TTS.glob('*.wav'))
    random.shuffle(tts)
    tts_teste, tts_treino = tts[:30], tts[30:]
    destino = TREINO / 'solis-treino.zip'
    negativos = sorted(NEGATIVOS.glob('*.wav'))
    random.shuffle(negativos)
    corte_neg = len(negativos) // 10
    neg_teste, neg_treino = negativos[:corte_neg], negativos[corte_neg:]
    # As pastas com os nomes do treinador (train.py: my_custom_model/solis/...).
    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in treino:
            corte, _ = trecho_com_voz(ler(f))
            for r in range(REPETIR):
                z.writestr(f'positive_train/real-{f.parent.name}-{f.stem}-{r}.wav', wav(corte))
        for f in tts_treino:
            z.writestr(f'positive_train/tts-{f.stem}.wav', wav(trecho_com_voz(ler(f))[0]))
        for f in tts_teste:
            z.writestr(f'positive_test/tts-{f.stem}.wav', wav(trecho_com_voz(ler(f))[0]))
        for f in neg_treino:
            z.writestr(f'negative_train/tts-{f.stem}.wav', wav(trecho_com_voz(ler(f))[0]))
        for f in neg_teste:
            z.writestr(f'negative_test/tts-{f.stem}.wav', wav(trecho_com_voz(ler(f))[0]))
    print(f'gravações: {len(treino) + len(teste)} ({len(treino)} no treino x{REPETIR}, {len(teste)} no teste local)')
    print(f'tts: {len(tts_treino)} no treino, {len(tts_teste)} no teste do Colab')
    print(f'negativos: {len(neg_treino)} no treino, {len(neg_teste)} no teste')
    print(f'contagens pro Colab: positive_train {len(treino) * REPETIR + len(tts_treino)}, '
          f'positive_test {len(tts_teste)}, negative_train {len(neg_treino)}, negative_test {len(neg_teste)}')
    print(f'pacote: {destino} ({destino.stat().st_size / 1e6:.1f} MB)')
    print(f'com problema ({len(problemas)}):')
    for p in problemas:
        print('  ', p)


main()
