"""Rasterizador minimo pro subconjunto de SVG que design/*.svg usa (M, L, C, Z).

Existe pra que os assets derivados saiam do SVG versionado — e nao de um estado
intermediario do script de vetorizacao. O que esta no arquivo e o que vira PNG.
"""
import re
import numpy as np
from PIL import Image, ImageDraw

def parse_path(d):
    """Devolve lista de subcaminhos, cada um uma lista de pontos ja achatados."""
    tokens = re.findall(r'([MLCZ])([^MLCZ]*)', d)
    subs, cur, pos = [], [], (0.0, 0.0)
    def nums(s): return [float(v) for v in re.findall(r'-?\d+\.?\d*', s)]
    for cmd, arg in tokens:
        v = nums(arg)
        if cmd == 'M':
            if cur: subs.append(cur)
            pos = (v[0], v[1]); cur = [pos]
        elif cmd == 'L':
            for i in range(0, len(v), 2):
                pos = (v[i], v[i+1]); cur.append(pos)
        elif cmd == 'C':
            for i in range(0, len(v), 6):
                p1, p2, p3 = (v[i], v[i+1]), (v[i+2], v[i+3]), (v[i+4], v[i+5])
                cur += _bez(pos, p1, p2, p3); pos = p3
        elif cmd == 'Z':
            if cur: subs.append(cur); cur = []
    if cur: subs.append(cur)
    return subs

def _bez(p0, p1, p2, p3, n=32):
    out = []
    for i in range(1, n+1):
        t = i/n; u = 1-t
        out.append((u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
                    u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]))
    return out

def load(svg_path):
    s = open(svg_path).read()
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', s).group(1).split()]
    d = re.search(r'\sd="([^"]+)"', s).group(1)
    return parse_path(d), vb

def mask(svg_path, width, ss=4):
    """Mascara alpha (uint8) do simbolo, com `width` px de largura e antialias."""
    subs, (vx, vy, vw, vh) = load(svg_path)
    height = max(1, round(width * vh / vw))
    k = width * ss / vw
    acc = np.zeros((height*ss, width*ss), bool)      # fill-rule evenodd = XOR
    for pts in subs:
        im = Image.new('L', (width*ss, height*ss), 0)
        ImageDraw.Draw(im).polygon([((x-vx)*k, (y-vy)*k) for x, y in pts], fill=255)
        acc ^= (np.array(im) > 128)
    return np.array(Image.fromarray((acc*255).astype('uint8')).resize((width, height), Image.LANCZOS))

def tinted(svg_path, width, rgb, ss=4):
    """RGBA do simbolo numa cor solida, fundo transparente."""
    a = mask(svg_path, width, ss)
    h, w = a.shape
    out = np.zeros((h, w, 4), np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = rgb
    out[..., 3] = a
    return Image.fromarray(out, 'RGBA')
