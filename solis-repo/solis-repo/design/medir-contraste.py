#!/usr/bin/env python3
"""
Contraste WCAG de cada texto da tela contra o fundo que o app REALMENTE pinta.

    node design/medir-caixas.mjs   http://localhost:4173/ /tmp/caixas.json
    node design/capturar-telas.mjs http://localhost:4173/ /tmp 1440 930 fundo
    python3 design/medir-contraste.py /tmp/caixas.json /tmp 1440 930

Mede pixel a pixel dentro da caixa do texto, não contra o token de canvas: se a
cena voltar a invadir a área de texto, o pior caso cai na hora e aparece aqui.
Quando "pior" e "melhor" dão o mesmo número, o fundo debaixo daquele texto é
chapado — que é exatamente o que se quer depois de ancorar a cena embaixo.

Critério: 4,5:1. Não existe a saída "AA só pra texto grande" — todos os outros
tokens de texto do sistema já cumprem 4,5:1 e abrir exceção baixaria o padrão.
"""
import json
import re
import sys

import numpy as np
from PIL import Image

CRITERIO = 4.5


def _srgb_linear(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminancia(rgb):
    r, g, b = _srgb_linear(np.asarray(rgb, float)).T
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cor(txt):
    txt = txt.strip()
    if txt.startswith('#'):
        return [int(txt[i:i + 2], 16) for i in (1, 3, 5)]
    n = re.findall(r'[\d.]+', txt)
    return [float(n[0]), float(n[1]), float(n[2])]


def contraste(l1, l2):
    return (np.maximum(l1, l2) + 0.05) / (np.minimum(l1, l2) + 0.05)


def main(caixas_json, pasta, larg, alt):
    caixas = json.load(open(caixas_json))
    piores = {}
    print(f'{"tema":9s} {"alvo":14s} {"y":>4s} {"cor":>9s} {"pior":>7s} {"melhor":>7s}  ')
    for tema, lista in caixas.items():
        fundo = np.asarray(Image.open(f'{pasta}/{tema}-fundo-{larg}x{alt}.png').convert('RGB')).astype(float)
        pior_tema = (float('inf'), '')
        for a in lista:
            x0, y0 = max(int(round(a['x'])), 0), max(int(round(a['y'])), 0)
            x1, y1 = min(int(round(a['x'] + a['w'])), larg), min(int(round(a['y'] + a['h'])), alt)
            if x1 <= x0 or y1 <= y0:
                continue
            c = contraste(luminancia(cor(a['cor'])),
                          luminancia(fundo[y0:y1, x0:x1].reshape(-1, 3)))
            pior, melhor = c.min(), c.max()
            print(f'{tema:9s} {a["nome"]:14s} {y0:4d} {a["cor"][:9]:>9s} '
                  f'{pior:7.2f} {melhor:7.2f}  {"ok" if pior >= CRITERIO else "REPROVA"}')
            if pior < pior_tema[0]:
                pior_tema = (pior, a['nome'])
        piores[tema] = pior_tema
        print()
    print('pior caso por tema:')
    for t, (v, n) in piores.items():
        print(f'  {t:9s} {v:6.2f}:1  ({n})  {"ok" if v >= CRITERIO else "REPROVA"}')
    return 0 if all(v >= CRITERIO for v, _ in piores.values()) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])))
