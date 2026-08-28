#!/usr/bin/env python3
"""
Deriva os assets de marca a partir de design/solis-symbol.svg.

Tudo aqui sai do vetor — nenhum PNG e ampliado a partir de outro PNG. Rodar
depois de qualquer mudanca no SVG:

    python3 design/gerar-assets.py        # a partir da raiz do repo

Cores (tokens, nao valores avulsos):
  fundo do icone  themes.dark.canvas  #07080D  — o icone bate com o tema padrao do app
  tinta           color.warmWhite     #F5F0E7  — e a tinta medida na aplicacao
                                                 aprovada em sobre-fundo-escuro.png
"""
import os, struct, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import _svgraster as R

SVG   = 'design/solis-symbol.svg'
BG    = (0x07, 0x08, 0x0D)
INK   = (0xF5, 0xF0, 0xE7)
NIGHT = (0x07, 0x10, 0x19)

# Proporcao do simbolo dentro do quadrado. 76% e o que a aplicacao aprovada
# (referencias/brand/symbol-refinado/sobre-fundo-escuro.png) usa. Nos tamanhos
# pequenos o simbolo cresce: o Matheus validou legibilidade a partir de 24px do
# SIMBOLO, e a 16px de canvas com 76% sobrariam 12px de marca.
def escala(px):
    if px >= 64: return 0.76
    if px >= 32: return 0.84
    return 0.92

CENTRO_V = 0.47      # centro optico medido na aplicacao aprovada

def icone(px):
    canvas = Image.new('RGBA', (px, px), BG + (255,))
    w = max(1, round(px * escala(px)))
    marca = R.tinted(SVG, w, INK, ss=4 if px > 64 else 8)
    x = (px - w) // 2
    y = round(px * CENTRO_V - marca.height / 2)
    canvas.alpha_composite(marca, (x, y))
    # RGBA, nao RGB: o Tauri recusa icone sem canal alpha na hora de gerar o
    # contexto ("icon ... is not RGBA"). O fundo e opaco de qualquer jeito.
    return canvas

def escrever_ico(destino, imagens):
    """ICO com payload PNG por entrada (suportado desde o Windows Vista),
    pra manter o ajuste optico de cada tamanho em vez de reduzir tudo de um so."""
    blobs = []
    for im in imagens:
        b = io.BytesIO(); im.save(b, 'PNG'); blobs.append(b.getvalue())
    with open(destino, 'wb') as f:
        f.write(struct.pack('<HHH', 0, 1, len(blobs)))
        deslocamento = 6 + 16 * len(blobs)
        for im, b in zip(imagens, blobs):
            lado = 0 if im.width >= 256 else im.width
            f.write(struct.pack('<BBBBHHII', lado, lado, 0, 0, 1, 32, len(b), deslocamento))
            deslocamento += len(b)
        for b in blobs: f.write(b)

os.makedirs('referencias/brand/app-icon', exist_ok=True)
os.makedirs('referencias/brand/favicon', exist_ok=True)

TAMANHOS = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
feitos = {p: icone(p) for p in TAMANHOS}
feitos[1024].save('referencias/brand/app-icon/solis-app-icon.png')
for p in TAMANHOS:
    feitos[p].save('referencias/brand/app-icon/icon-%d.png' % p)
escrever_ico('referencias/brand/app-icon/solis.ico', [feitos[p] for p in (16, 24, 32, 48, 64, 128, 256)])

# favicon: mesmo icone, e um SVG proprio — nao da pra usar o solis-symbol.svg
# direto porque ele e currentColor, que num favicon resolveria pra preto.
escrever_ico('referencias/brand/favicon/favicon.ico', [feitos[p] for p in (16, 32, 48)])
for p in (16, 32, 180):
    (feitos[p] if p in feitos else icone(p)).save('referencias/brand/favicon/favicon-%d.png' % p)
subs, (vx, vy, vw, vh) = R.load(SVG)
d = open(SVG).read().split('d="')[1].split('"')[0]
lado = 100.0; s = lado * escala(64) / vw
open('referencias/brand/favicon/favicon.svg', 'w').write(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="Solis">\n'
    '  <rect width="100" height="100" fill="#%02X%02X%02X"/>\n'
    '  <g transform="translate(%.3f %.3f) scale(%.5f)" fill="#%02X%02X%02X">\n'
    '    <path fill-rule="evenodd" d="%s"/>\n  </g>\n</svg>\n'
    % (*BG, (lado - vw*s)/2, lado*CENTRO_V - vh*s/2, s, *INK, d))

# simbolo solto com alpha real, pros usos que nao aceitam SVG
R.tinted(SVG, 2048, INK,   ss=3).save('referencias/brand/symbol-refinado/solis-symbol-mono-claro.png')
R.tinted(SVG, 2048, NIGHT, ss=3).save('referencias/brand/symbol-refinado/solis-symbol-mono-escuro.png')

print('app-icon: %s' % ', '.join('%d' % p for p in TAMANHOS))
print('ico: solis.ico (16-256) · favicon.ico (16-48) · favicon.svg')
print('simbolo com alpha: mono-claro.png, mono-escuro.png (2048px)')
