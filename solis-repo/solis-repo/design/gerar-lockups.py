#!/usr/bin/env python3
"""
Regera os dois lockups da marca (horizontal e vertical) a partir do vetor.

    python3 design/gerar-lockups.py <pasta-com-DM-Sans-500.ttf>

Os lockups antigos foram desenhados sobre o SIMBOLO ANTIGO e ficaram travados a
Fase 2 inteira: refazer exigia compor o wordmark como texto, e nao se sabia qual
era a fonte. Fechada a fonte (DM Sans 500, escolhida na folha gerada por
design/comparar-wordmark.py), o caminho abriu.

Nada aqui e ampliado de PNG: o simbolo sai de design/solis-symbol.svg e o
wordmark e texto de verdade, entao os dois escalam pra qualquer tamanho.

PROPORCOES. Vem da folha do simbolo refinado
(referencias/brand/symbol-refinado/mono-wordmark.png), que e a apresentacao
aprovada da marca nova — nao dos lockups antigos, cujo simbolo era outro
(cupula baixa de aspecto 2,33 contra o arco de 1,75 de hoje), e por isso tinham
outro equilibrio entre arco e letra.

  vertical    cap do wordmark = 10,34% da largura do simbolo
              folga vertical  =  8,53%
              largura do wordmark = 74,94%  (o tracking sai disso)

  horizontal  a folha nao tem arranjo horizontal. A razao vem do lockup antigo,
              unica leitura que existe do arranjo lado a lado, e sai da LARGURA
              do simbolo: cap = 24,74%, folga = 23,26%. Escalar pela altura
              estoura a moldura — o simbolo novo e proporcionalmente mais alto
              que o antigo (0,571 contra 0,429), e o wordmark saia 20% mais
              largo que a arte inteira do lockup antigo.

Cores: tokens, nunca valores avulsos — themes.dark.canvas no fundo e
color.warmWhite na tinta, os mesmos de design/gerar-assets.py.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _svgraster as R

SVG = 'design/solis-symbol.svg'
TEXTO = 'SOLIS'
SS = 4                      # supersampling do wordmark

T = json.load(open('docs/solis-tokens.json'))
BG = tuple(int(T['themes']['dark']['canvas'][i:i+2], 16) for i in (1, 3, 5))
INK = tuple(int(T['color']['warmWhite'][i:i+2], 16) for i in (1, 3, 5))

# medidos em mono-wordmark.png: simbolo 387x221, wordmark 290 de largura e cap 40,
# folga de 33 entre a base do simbolo e o topo do wordmark
CAP_V, FOLGA_V, LARG_WM = 40/387, 33/387, 290/387
# medidos no lockup antigo (unica leitura do arranjo lado a lado)
CAP_H, FOLGA_H = 117/473, 110/473


def wordmark(ttf, cap, cor, larg_alvo=None):
    """Compoe SOLIS com o tracking ajustado pra largura alvo. Devolve RGBA."""
    tam = cap * SS * 3
    f = ImageFont.truetype(ttf, tam)
    alvo = (larg_alvo / cap) if larg_alvo else 7.250     # largura/cap da referencia
    lo, hi, melhor = 0.0, float(tam), None
    for _ in range(40):
        t = (lo + hi) / 2
        largura = sum(f.getlength(c) for c in TEXTO) + t * (len(TEXTO) - 1)
        im = Image.new('L', (int(largura) + tam * 2, tam * 3), 255)
        d = ImageDraw.Draw(im)
        x = tam
        for c in TEXTO:
            d.text((x, tam), c, font=f, fill=0)
            x += f.getlength(c) + t
        m = np.asarray(im) < 128
        ys, xs = np.where(m)
        m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        if m.shape[1] / m.shape[0] < alvo:
            lo = t
        else:
            hi = t
        melhor = m
    grande = Image.fromarray((~melhor * 255).astype('uint8'))
    fim = grande.resize((max(1, round(melhor.shape[1] * cap / melhor.shape[0])), cap), Image.LANCZOS)
    a = 255 - np.asarray(fim).astype(np.uint8)
    arr = np.zeros((*a.shape, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3] = INK[0], INK[1], INK[2], a
    return Image.fromarray(arr), hi / tam


def _cola(lona, im, x, y):
    lona.paste(im, (int(x), int(y)), im)


def vertical(ttf, lado=1254):
    sim_larg = round(lado * 663 / 1254)                 # mesma presenca do lockup antigo
    sim = R.tinted(SVG, sim_larg, INK, ss=4)
    cap = max(1, round(sim_larg * CAP_V))
    folga = round(sim_larg * FOLGA_V)
    wm, tr = wordmark(ttf, cap, INK, larg_alvo=round(sim_larg * LARG_WM))
    alt = sim.height + folga + wm.height
    # centro optico: o bloco antigo ficava levemente alto (333 de topo contra 425 de base)
    topo = round((lado - alt) * 333 / (333 + 425))
    lona = Image.new('RGBA', (lado, lado), BG + (255,))
    _cola(lona, sim, (lado - sim.width) / 2, topo)
    _cola(lona, wm, (lado - wm.width) / 2, topo + sim.height + folga)
    return lona.convert('RGB'), tr


def horizontal(ttf, larg=1774, alt=887):
    sim_larg = round(larg * 473 / 1774)
    sim = R.tinted(SVG, sim_larg, INK, ss=4)
    cap = max(1, round(sim_larg * CAP_H))
    folga = round(sim_larg * FOLGA_H)
    wm, tr = wordmark(ttf, cap, INK)
    total = sim.width + folga + wm.width
    # a arte nao pode encostar na moldura: o lockup antigo deixava 146-162px de
    # respiro dos dois lados, e sem esta checagem uma mudanca de proporcao do
    # simbolo corta o wordmark sem avisar.
    assert total <= larg * 0.90, f'arte de {total}px nao cabe em {larg}px'
    x = (larg - total) / 2
    lona = Image.new('RGBA', (larg, alt), BG + (255,))
    cy = alt / 2
    _cola(lona, sim, x, cy - sim.height / 2)
    _cola(lona, wm, x + sim.width + folga, cy - wm.height / 2)
    return lona.convert('RGB'), tr


def main(pasta):
    ttf = f'{pasta}/DM-Sans-500.ttf'
    v, trv = vertical(ttf)
    h, trh = horizontal(ttf)
    v.save('referencias/brand/logo/solis-logo-vertical.png')
    h.save('referencias/brand/logo/solis-logo-horizontal.png')
    print(f'vertical   {v.size}  tracking {trv:.3f}em')
    print(f'horizontal {h.size}  tracking {trh:.3f}em')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'design/_fontes-candidatas')
