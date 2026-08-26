#!/usr/bin/env python3
"""
Deriva uma cor de texto a partir da MEDIDA na referencia ate ela atingir um
contraste alvo, mexendo o minimo possivel.

Metodo: converte pra OKLCh e mexe SO no L (lightness perceptual), mantendo
croma e matiz travados. E o que separa "derivar do medido" de "trocar por
outra cor" — a cor final tem exatamente o mesmo tom e a mesma saturacao
perceptual da amostrada na referencia, so mais clara ou mais escura.

    python3 design/derivar-cor.py
"""
import math

# ---------- sRGB <-> OKLab (Bjorn Ottosson) ----------
def _s2l(c):
    c /= 255.0
    return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
def _l2s(c):
    v = 12.92*c if c <= 0.0031308 else 1.055*(c**(1/2.4)) - 0.055
    return max(0.0, min(255.0, v*255.0))

def rgb_para_oklab(rgb):
    r, g, b = (_s2l(v) for v in rgb)
    l = (0.4122214708*r + 0.5363325363*g + 0.0514459929*b) ** (1/3)
    m = (0.2119034982*r + 0.6806995451*g + 0.1073969566*b) ** (1/3)
    s = (0.0883024619*r + 0.2817188376*g + 0.6299787005*b) ** (1/3)
    return (0.2104542553*l + 0.7936177850*m - 0.0040720468*s,
            1.9779984951*l - 2.4285922050*m + 0.4505937099*s,
            0.0259040371*l + 0.7827717662*m - 0.8086757660*s)

def oklab_para_rgb(lab):
    L, a, bb = lab
    l = (L + 0.3963377774*a + 0.2158037573*bb) ** 3
    m = (L - 0.1055613458*a - 0.0638541728*bb) ** 3
    s = (L - 0.0894841775*a - 1.2914855480*bb) ** 3
    return tuple(_l2s(v) for v in (
        +4.0767416621*l - 3.3077115913*m + 0.2309699292*s,
        -1.2684380046*l + 2.6097574011*m - 0.3413193965*s,
        -0.0041960863*l - 0.7034186147*m + 1.7076147010*s))

def para_lch(rgb):
    L, a, b = rgb_para_oklab(rgb)
    return L, math.hypot(a, b), math.atan2(b, a)
def de_lch(L, C, h):
    return oklab_para_rgb((L, C*math.cos(h), C*math.sin(h)))

# ---------- WCAG ----------
def lum(rgb):
    r, g, b = (_s2l(v) for v in rgb)
    return 0.2126*r + 0.7152*g + 0.0722*b
def contraste(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi+0.05)/(lo+0.05)

def dE(rgb1, rgb2):
    """Distancia perceptual em OKLab (deltaEOK). ~0,02 e o limiar em que a
    maioria das pessoas comeca a perceber diferenca lado a lado."""
    a, b = rgb_para_oklab(rgb1), rgb_para_oklab(rgb2)
    return math.dist(a, b)

def hexa(rgb): return '#%02X%02X%02X' % tuple(round(v) for v in rgb)
def de_hexa(s): return tuple(int(s[i:i+2], 16) for i in (1, 3, 5))

def derivar(medido, fundo, alvo=4.5, margem=0.02):
    """Move so o L, no sentido que aumenta o contraste, ate cruzar o alvo."""
    m = de_hexa(medido) if isinstance(medido, str) else medido
    f = de_hexa(fundo) if isinstance(fundo, str) else fundo
    L0, C, h = para_lch(m)
    escurecer = lum(m) < lum(f)
    lo, hi = (0.0, L0) if escurecer else (L0, 1.0)
    melhor = None
    for _ in range(60):
        L = (lo+hi)/2
        cand = de_lch(L, C, h)
        if contraste(cand, f) >= alvo + margem:
            melhor = (L, cand)
            if escurecer: lo = L
            else: hi = L
        else:
            if escurecer: hi = L
            else: lo = L
    if melhor is None: return None
    # arredonda pro hex de 8 bits e confere que o alvo sobreviveu
    final = de_hexa(hexa(melhor[1]))
    if contraste(final, f) < alvo:
        L = melhor[0] - 0.004 if escurecer else melhor[0] + 0.004
        final = de_hexa(hexa(de_lch(L, C, h)))
    return final

if __name__ == '__main__':
    casos = [
        ('claro',    '#888480', '#FCF7F2'),
        ('dark',     '#746A5F', '#07080D'),
        ('espacial', '#894D43', '#FAE7D0'),
    ]
    print('%-9s %-9s %-9s %8s %8s %7s  %s' % (
        'tema', 'medido', 'final', 'antes', 'depois', 'dEOK', 'matiz/croma'))
    for nome, medido, fundo in casos:
        m = de_hexa(medido); f = de_hexa(fundo)
        antes = contraste(m, f)
        if antes >= 4.5:
            print('%-9s %-9s %-9s %7.2f:1 %7s %7s  %s' % (nome, medido, '(mantido)', antes, '—', '—', 'ja passa'))
            continue
        final = derivar(medido, fundo)
        Lm, Cm, hm = para_lch(m); Lf, Cf, hf = para_lch(final)
        print('%-9s %-9s %-9s %7.2f:1 %6.2f:1 %7.4f  C %.4f->%.4f  h %.1f°->%.1f°' % (
            nome, medido, hexa(final), antes, contraste(final, f), dE(m, final),
            Cm, Cf, math.degrees(hm) % 360, math.degrees(hf) % 360))
