#!/usr/bin/env python3
"""
Gera design/solis-symbol.svg a partir do raster aprovado do simbolo refinado.

Nao ha ajuste manual em nenhum ponto de controle: o SVG e o traco direto do
raster. E isso que permite dizer que a curva no vetor e a curva desenhada, e
nao uma reinterpretacao. Se o raster de origem mudar, roda de novo.

    pip install pillow numpy potracer
    python3 design/vetorizar-simbolo.py        # a partir da raiz do repo

Parametros travados na validacao da Fase 2 (ver docs/MEDICOES_FASE2.md):
IoU 98,98% contra o original, 48 segmentos, 2,1 KB.
"""
import numpy as np, potrace
from PIL import Image, ImageFilter

SRC  = 'referencias/brand/symbol-refinado/mono-wordmark.png'
DST  = 'design/solis-symbol.svg'
BOX  = (83, 101, 470, 322)   # simbolo sem o wordmark — medido por perfil de tinta
PAD  = 6                     # evita que a forma encoste na borda do recorte
UP   = 3                     # supersampling antes do traco
BLUR = 1.5                   # suaviza a escada de pixel sem comer as pontas finas
TOL  = 1.0                   # opttolerance do potrace, no espaco ampliado

im = Image.open(SRC).convert('L').crop((BOX[0]-PAD, BOX[1]-PAD, BOX[2]+PAD, BOX[3]+PAD))
W, H = im.size
big = im.resize((W*UP, H*UP), Image.LANCZOS).filter(ImageFilter.GaussianBlur(BLUR))
# convencao do potracer: a tinta e o False do array
path = potrace.Bitmap(np.array(big) >= 128).trace(
    turdsize=4*UP, alphamax=1.0, opticurve=True, opttolerance=TOL)

pts = lambda p: (p.x/UP, p.y/UP)

def flatten(p0, p1, p2, p3, n=32):
    """Pontos SOBRE a curva. O bbox tem que sair daqui, nao dos pontos de
    controle: control point de bezier fica fora da curva, e usar ele infla o
    viewBox com margem morta assimetrica."""
    out = []
    for i in range(1, n+1):
        t = i/n; u = 1-t
        out.append((u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
                    u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]))
    return out

todos = []
for c in path:
    cur = pts(c.start_point); todos.append(cur)
    for seg in c:
        if seg.is_corner:
            todos += [pts(seg.c), pts(seg.end_point)]
        else:
            todos += flatten(cur, pts(seg.c1), pts(seg.c2), pts(seg.end_point))
        cur = todos[-1]
ox = min(p[0] for p in todos); oy = min(p[1] for p in todos)
Wb = max(p[0] for p in todos) - ox; Hb = max(p[1] for p in todos) - oy
P = lambda p: ((p.x/UP - ox), (p.y/UP - oy))

d = []
for c in path:
    d.append('M%.2f %.2f' % P(c.start_point))
    for seg in c:
        if seg.is_corner:
            d.append('L%.2f %.2fL%.2f %.2f' % (P(seg.c) + P(seg.end_point)))
        else:
            d.append('C%.2f %.2f %.2f %.2f %.2f %.2f' % (P(seg.c1) + P(seg.c2) + P(seg.end_point)))
    d.append('Z')

open(DST, 'w').write(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.2f %.2f" fill="currentColor" '
    'fill-rule="evenodd" role="img" aria-label="Solis">\n  <path d="%s"/>\n</svg>\n'
    % (Wb, Hb, ''.join(d)))
print('%s — %d segmentos' % (DST, ''.join(d).count('C') + ''.join(d).count('L')))
