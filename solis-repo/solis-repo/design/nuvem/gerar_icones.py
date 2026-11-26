"""Gera os ícones do Solis pra Tela de Início do celular (public/icone-192.png e
public/icone-512.png) a partir do public/favicon.svg, sem programa de fora: o
desenho do logo é um caminho só de curvas (M, C, Z), achatado aqui em polígonos
e pintado com o Pillow em 4× (pra borda lisa), depois reduzido.

26/11/2026, pro manifesto do Solis aberto pelo servidor (o iPhone só recebe aviso
com o Solis na Tela de Início). Rodar da raiz do app:
    backend/.venv/Scripts/python design/nuvem/gerar_icones.py
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[2]
SVG = (RAIZ / 'public' / 'favicon.svg').read_text(encoding='utf-8')
ESCALA = 4

fundo = re.search(r'<rect[^>]*fill="(#[0-9A-Fa-f]{6})"', SVG).group(1)
g = re.search(r'<g transform="translate\(([\d.]+) ([\d.]+)\) scale\(([\d.]+)\)" fill="(#[0-9A-Fa-f]{6})"', SVG)
tx, ty, s, cor = float(g.group(1)), float(g.group(2)), float(g.group(3)), g.group(4)
d = re.search(r' d="([^"]+)"', SVG).group(1)


def subcaminhos(d: str) -> list[list[tuple[float, float]]]:
    """Os pontos de cada subcaminho, com as curvas cúbicas achatadas (24 passos cada)."""
    fichas = re.findall(r'[MCZ]|-?\d+(?:\.\d+)?', d)
    todos, atual, i, comando, ponto = [], [], 0, None, (0.0, 0.0)
    while i < len(fichas):
        f = fichas[i]
        if f in 'MCZ':
            comando = f
            i += 1
            if f == 'Z':
                todos.append(atual)
                atual = []
            continue
        if comando == 'M':
            ponto = (float(fichas[i]), float(fichas[i + 1]))
            atual = [ponto]
            i += 2
            comando = 'C'  # depois do M vêm as curvas (no desenho, sempre C)
        elif comando == 'C':
            x1, y1, x2, y2, x, y = (float(v) for v in fichas[i:i + 6])
            x0, y0 = ponto
            for k in range(1, 25):
                t = k / 24
                a, b, c_, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                atual.append((a * x0 + b * x1 + c_ * x2 + e * x, a * y0 + b * y1 + c_ * y2 + e * y))
            ponto = (x, y)
            i += 6
    if atual:
        todos.append(atual)
    return todos


for tamanho in (192, 512):
    grande = tamanho * ESCALA
    img = Image.new('RGB', (grande, grande), fundo)
    desenho = ImageDraw.Draw(img)
    fator = grande / 100  # o viewBox é 0 0 100 100
    for pontos in subcaminhos(d):
        desenho.polygon([((tx + x * s) * fator, (ty + y * s) * fator) for x, y in pontos], fill=cor)
    destino = RAIZ / 'public' / f'icone-{tamanho}.png'
    img.resize((tamanho, tamanho), Image.LANCZOS).save(destino, optimize=True)
    print(destino.name, destino.stat().st_size, 'bytes')
