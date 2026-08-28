#!/usr/bin/env python3
"""
Acha qual fonte desenha o wordmark SOLIS da folha do simbolo refinado.

O wordmark da referencia tem so 40px de altura de tinta — pequeno demais pra
vetorizar sem estragar a tipografia (foi por isso que os lockups de
brand/logo/ ficaram travados). O caminho certo e compor o wordmark como TEXTO,
e pra isso primeiro e preciso saber (ou escolher) a fonte.

    # 1. baixar as candidatas em TTF (precisa de rede; a API v1 do Google Fonts
    #    entrega TTF quando o User-Agent e antigo, a v2 so entrega woff2, que o
    #    PIL nao le)
    curl -A "Mozilla/4.0" "https://fonts.googleapis.com/css?family=DM+Sans:400,500"
    # 2. comparar
    python3 design/comparar-wordmark.py <pasta-com-ttfs>

Gera design/wordmark-candidatas.png (sobreposicao letra a letra) e
design/wordmark-lockups.png (as 4 primeiras montadas com o simbolo refinado).

METODO. Cada candidata e composta com um tracking ajustado por busca binaria
ate a largura total bater com a da referencia — sem isso a comparacao mediria
espacejamento, nao desenho de letra. Depois cada letra e recentrada na letra
correspondente da referencia, pelo mesmo motivo.

O ranking e por erro de forma, nao por IoU: com tracking largo o IoU premia
peso de traco e ignora proporcao, e chega a por na frente fontes de O visivelmente
estreito (Rubik 400 ficou em 1o no IoU com O de 0,775 contra 0,940 da referencia).

O numero NAO decide sozinho. A Lexend 400 ganha no erro de forma e perde no olho:
o I dela tem terminais alargados e o da referencia e haste reta — aparece na
sobreposicao como duas barras azuis, uma em cima e outra embaixo do I. Por isso
esta ferramenta gera folha pra olhar, e nao um vencedor.

INCERTEZA. A referencia tem cap de 40px, entao 1px de erro de leitura vale 2,5%.
Diferencas menores que isso entre candidatas nao significam nada.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CAP = 200          # altura de caixa alta normalizada pra comparacao
TEXTO = 'SOLIS'
FOLHA = 'referencias/brand/symbol-refinado/mono-wordmark.png'
WM_CAIXA = (133, 354, 423, 394)   # o wordmark dentro da folha
SIMBOLO = (83, 101, 470, 322)     # o simbolo dentro da folha
ALVO_LARGURA = 7.250              # largura total / cap, medido na referencia
# pesos do erro de forma: a proporcao do O separa geometrica de humanista e e o
# sinal mais forte; o peso do traco e o mais ruidoso na leitura de 40px.
PESOS = {'O': 3.0, 'S': 2.0, 'L': 2.0, 'haste': 1.5}
TINTA, FUNDO = (26, 26, 28), (250, 249, 247)


def referencia():
    a = np.asarray(Image.open(FOLHA).convert('L')).astype(float)
    x0, y0, x1, y1 = WM_CAIXA
    im = Image.fromarray(np.clip(a[y0:y1, x0:x1], 0, 255).astype('uint8'))
    return np.asarray(im.resize((round(im.width * CAP / im.height), CAP), Image.LANCZOS)) < 128


def grupos(m):
    """Faixas horizontais de tinta — uma por letra."""
    cols = m.any(axis=0)
    g, ini = [], None
    for x in range(m.shape[1]):
        if cols[x] and ini is None:
            ini = x
        elif not cols[x] and ini is not None:
            g.append((ini, x - 1)); ini = None
    if ini is not None:
        g.append((ini, m.shape[1] - 1))
    return g


def metricas(m):
    g = grupos(m)
    if len(g) != 5:
        return None
    cap = m.shape[0]
    larg = lambda i: (g[i][1] - g[i][0] + 1) / cap
    x0, x1 = g[3]                                   # o I e a leitura limpa da haste
    col = m[:, x0:x1 + 1]
    haste = min(np.where(col[y])[0].max() - np.where(col[y])[0].min() + 1
                for y in range(col.shape[0]) if col[y].any())
    x0, x1 = g[1]                                   # o O da a proporcao
    co = m[:, x0:x1 + 1]
    ys = np.where(co.any(axis=1))[0]
    return dict(haste=haste / cap, O=larg(1) / ((ys.max() - ys.min() + 1) / cap),
                S=larg(0), L=larg(2))


def compoe(ttf, tracking, tam=400):
    f = ImageFont.truetype(ttf, tam)
    larg = sum(f.getlength(c) for c in TEXTO) + tracking * (len(TEXTO) - 1)
    im = Image.new('L', (int(larg) + tam, tam * 2), 255)
    d = ImageDraw.Draw(im)
    x = tam // 2
    for c in TEXTO:
        d.text((x, tam // 2), c, font=f, fill=0)
        x += f.getlength(c) + tracking
    m = np.asarray(im) < 128
    if not m.any():
        return None
    ys, xs = np.where(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def normaliza(m, cap=CAP):
    im = Image.fromarray((~m * 255).astype('uint8'))
    return np.asarray(im.resize((max(1, round(im.width * cap / im.height)), cap),
                                Image.LANCZOS)) < 128


def ajusta_tracking(ttf, tam=400):
    """Busca o tracking que faz a largura total bater com a da referencia."""
    lo, hi, saida = 0.0, float(tam), None
    for _ in range(40):
        t = (lo + hi) / 2
        m = compoe(ttf, t, tam)
        if m is None:
            return None, None
        n = normaliza(m)
        if n.shape[1] / CAP < ALVO_LARGURA:
            lo = t
        else:
            hi = t
        saida = n
    return saida, hi / tam


def alinha_por_letra(cand, ref, gref):
    gc = grupos(cand)
    if len(gc) != 5:
        return None
    out = np.zeros_like(ref)
    for (rx0, rx1), (cx0, cx1) in zip(gref, gc):
        bloco = cand[:, cx0:cx1 + 1]
        x0 = (rx0 + rx1) // 2 - bloco.shape[1] // 2
        a, b = max(x0, 0), min(x0 + bloco.shape[1], out.shape[1])
        if b > a:
            out[:, a:b] |= bloco[:, a - x0:b - x0]
    return out


def _fontes_ui():
    base = '/usr/share/fonts/truetype/dejavu/'
    def carrega(arq, tam):
        try:
            return ImageFont.truetype(base + arq, tam)
        except OSError:
            return ImageFont.load_default()
    return (carrega('DejaVuSans-Bold.ttf', 22), carrega('DejaVuSans.ttf', 15),
            carrega('DejaVuSansMono.ttf', 13))


def folha_candidatas(ref, res, saida='design/wordmark-candidatas.png', esc=0.62):
    ft, fp, fm = _fontes_ui()
    gref = grupos(ref)
    def pinta(m):
        arr = np.full((CAP, m.shape[1], 3), FUNDO, np.uint8); arr[m] = TINTA
        return Image.fromarray(arr)
    def sobrepoe(c):
        arr = np.full((CAP, ref.shape[1], 3), 255, np.uint8)
        arr[ref & ~c] = (226, 62, 62)
        arr[c & ~ref] = (48, 130, 230)
        arr[ref & c] = TINTA
        return Image.fromarray(arr)
    E = lambda im: im.resize((round(im.width * esc), round(im.height * esc)), Image.LANCZOS)
    lm = max([ref.shape[1]] + [r[4].shape[1] for r in res])
    W = 60 + round(lm * esc) + 40 + round(ref.shape[1] * esc) + 60
    lin = round(CAP * esc) + 48
    lona = Image.new('RGB', (W, 122 + lin * (len(res) + 1) + 50), FUNDO)
    d = ImageDraw.Draw(lona)
    d.text((60, 28), 'Wordmark SOLIS — candidatas contra a referencia', font=ft, fill=(20, 20, 22))
    d.text((60, 60), 'Esquerda: a fonte com o tracking ajustado pra bater a largura total da referencia.',
           font=fp, fill=(90, 90, 95))
    d.text((60, 80), 'Direita: sobreposicao letra a letra.  preto = coincide,  '
                     'vermelho = so a referencia,  azul = so a candidata', font=fp, fill=(90, 90, 95))
    y = 122
    d.text((60, y), 'REFERENCIA  (mono-wordmark.png, cap 40px ampliado 5x)', font=fp, fill=(20, 20, 22))
    lona.paste(E(pinta(ref)), (60, y + 24))
    y += lin
    for erro, nome, m, tr, msk in res:
        d.text((60, y), nome.replace('-', ' '), font=fp, fill=(20, 20, 22))
        d.text((60 + 340, y), f'erro {erro:.3f}   tracking {tr:.3f}em   O {m["O"]:.3f}  '
                              f'S {m["S"]:.3f}  L {m["L"]:.3f}  haste {m["haste"]:.3f}',
               font=fm, fill=(120, 120, 125))
        lona.paste(E(pinta(msk)), (60, y + 24))
        al = alinha_por_letra(msk, ref, gref)
        if al is not None:
            lona.paste(E(sobrepoe(al)), (60 + round(lm * esc) + 40, y + 24))
        y += lin
    r = metricas(ref)
    d.text((60, y + 8), f'referencia:  O {r["O"]:.3f}   S {r["S"]:.3f}   L {r["L"]:.3f}   '
                        f'haste {r["haste"]:.3f}   (fracoes da altura de caixa alta)',
           font=fm, fill=(120, 120, 125))
    lona.save(saida)
    return saida


def folha_lockups(pasta, res, saida='design/wordmark-lockups.png', simb_larg=560):
    sys.path.insert(0, 'design')
    import _svgraster as sr
    ft, fp, _ = _fontes_ui()
    sx0, sy0, sx1, sy1 = SIMBOLO
    wx0, wy0, wx1, wy1 = WM_CAIXA
    # proporcoes da propria folha do simbolo
    cap = round(simb_larg * (wy1 - wy0) / (sx1 - sx0))
    folga = round(simb_larg * (wy0 - sy1) / (sx1 - sx0))
    sim = sr.tinted('design/solis-symbol.svg', simb_larg, TINTA)
    col = simb_larg + 120
    # uma familia por coluna: duas variantes da mesma fonte nao ajudam a escolher
    quatro, vistas = [], set()
    for r in res:
        fam = r[1].rsplit('-', 1)[0]
        if fam in vistas:
            continue
        vistas.add(fam); quatro.append(r)
        if len(quatro) == 4:
            break
    lona = Image.new('RGB', (60 + len(quatro) * col + 60,
                             136 + sim.height + folga + cap + 60), FUNDO)
    d = ImageDraw.Draw(lona)
    d.text((60, 30), 'Lockup vertical com o simbolo refinado — as 4 primeiras familias', font=ft, fill=(20, 20, 22))
    d.text((60, 62), f'Proporcoes da propria folha do simbolo: cap do wordmark = '
                     f'{(wy1-wy0)/(sy1-sy0):.1%} da altura do simbolo, folga vertical = '
                     f'{(wy0-sy1)/(sy1-sy0):.1%}.', font=fp, fill=(90, 90, 95))
    for i, (_, nome, _, _, _) in enumerate(quatro):
        x = 60 + i * col
        d.text((x, 110), nome.replace('-', ' '), font=fp, fill=(20, 20, 22))
        lona.paste(sim, (x, 136), sim)
        msk, _ = ajusta_tracking(f'{pasta}/{nome}.ttf')
        wm = normaliza(msk, cap)
        arr = np.zeros((*wm.shape, 4), np.uint8); arr[wm] = (*TINTA, 255)
        wmi = Image.fromarray(arr)
        lona.paste(wmi, (x + (simb_larg - wmi.width) // 2, 136 + sim.height + folga), wmi)
    lona.save(saida)
    return saida


def main(pasta):
    ref = referencia()
    R = metricas(ref)
    res = []
    for ttf in sorted(glob.glob(f'{pasta}/*.ttf')):
        msk, tr = ajusta_tracking(ttf)
        if msk is None:
            continue
        m = metricas(msk)
        if m is None:
            continue
        erro = sum(p * abs(m[k] - R[k]) for k, p in PESOS.items())
        res.append((erro, os.path.basename(ttf)[:-4], m, tr, msk))
    res.sort(key=lambda r: r[0])

    print(f'{"fonte":22s} {"erro":>6s} {"O":>6s} {"S":>6s} {"L":>6s} {"haste":>6s} {"tracking":>9s}')
    print(f'{"REFERENCIA":22s} {"—":>6s} {R["O"]:6.3f} {R["S"]:6.3f} {R["L"]:6.3f} {R["haste"]:6.3f}')
    for erro, nome, m, tr, _ in res[:12]:
        print(f'{nome:22s} {erro:6.3f} {m["O"]:6.3f} {m["S"]:6.3f} {m["L"]:6.3f} '
              f'{m["haste"]:6.3f} {tr:8.3f}em')
    print()
    print(folha_candidatas(ref, res[:8]))
    print(folha_lockups(pasta, res))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'design/_fontes-candidatas')
