#!/usr/bin/env python3
"""
Altura do horizonte na tela — nos 3 temas e contra a referência.

    node design/capturar-telas.mjs http://localhost:4173/ /tmp 1440 930 fundo
    python3 design/medir-horizonte.py /tmp 1440 930

Dois localizadores, porque nenhum sozinho serve aos 3 temas:

  ápice  — pico de brilho na coluna central da área de conteúdo. É o número que
           compara direto com a referência (medida lá: 85,0% / 85,0% / 84,5%).
  borda  — maior queda de brilho descendo, na faixa x 1210-1380 (livre de UI).
           É a borda do planeta, mais longe do sol e por isso mais sensível a
           desalinhamento entre os temas.

Protocolos que NÃO funcionam aqui, todos testados: pico de brilho por coluna
sem restringir o y (no espacial e no claro o canvas chapado do topo é mais
claro que a foto e o argmax vai pra linha 0), detecção de crista, de gradiente
e de textura, e correlação cruzada vertical.
"""
import sys

import numpy as np
from PIL import Image

TEMAS = ('espacial', 'claro', 'dark')
REFERENCIA = {'espacial': 'tema-espacial-vinho.png',
              'claro': 'tema-claro-padrao.png',
              'dark': 'tema-dark.png'}
SIDEBAR = 200


def _lum(caminho):
    a = np.asarray(Image.open(caminho).convert('RGB')).astype(float)
    return 0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]


def apice(L, larg, sidebar):
    cx = sidebar + (larg - sidebar) // 2
    return int(np.argmax(L[:, cx - 60:cx + 60].mean(axis=1)))


def borda(L, x0, x1, alt, ini):
    return float(np.median([ini + int(np.argmin(np.gradient(L[:, x])[ini:alt - 4]))
                            for x in range(x0, x1)]))


def main(pasta, larg, alt):
    print(f'{"tema":9s} {"apice":>16s} {"borda x1210-1380":>18s}   referencia (apice / borda)')
    ap, bo = {}, {}
    for t in TEMAS:
        L = _lum(f'{pasta}/{t}-fundo-{larg}x{alt}.png')
        a = apice(L, larg, SIDEBAR)
        b = borda(L, 1210, 1381, alt, round(alt * 0.75))
        ap[t], bo[t] = a / alt, b / alt
        R = _lum('referencias/telas/' + REFERENCIA[t])
        rh, rw = R.shape
        ra = apice(R, rw, round(SIDEBAR * rw / larg))
        rb = borda(R, round(1210 * rw / larg), round(1381 * rw / larg), rh, round(rh * 0.75))
        print(f'{t:9s} {a:6d} px ({a/alt:5.1%}) {b:11.1f} px ({b/alt:5.1%})   '
              f'{ra/rh:5.1%} / {rb/rh:5.1%}')
    print(f'\nespalhamento entre temas — apice {(max(ap.values())-min(ap.values()))*alt:5.1f} px'
          f'   borda {(max(bo.values())-min(bo.values()))*alt:5.1f} px')


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
