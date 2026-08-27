#!/usr/bin/env python3
"""
Gera public/fundos/bg-{espacial,claro,dark}.webp a partir das fotos originais.

    python3 design/preparar-fundos.py [pasta-das-fontes]

As fontes NÃO estão versionadas nesta branch — elas foram subidas na raiz do
repo em `main` (commit 2ed3ded) com nomes genéricos, e o mapeamento pra tema
está na tabela FONTES abaixo. Recuperar com:

    git checkout origin/main -- "upscalemedia-transformed (4).png" ...

## Por que recortar em vez de compensar por CSS

As três fotos têm o horizonte em alturas diferentes dentro do arquivo. A ideia
original era corrigir isso com um `background-position-y` por tema, mas isso
não funciona nesta geometria: com `background-size: cover` e imagem de aspecto
1,60 numa janela de 1,55, o `cover` escala pela ALTURA — a imagem cobre a
altura exata e a folga sobra só na horizontal. Sem folga vertical, `position-y`
não move nada. Então o alinhamento tem que estar no arquivo.

## Como ajustar

`HORIZONTE` diz onde está o horizonte em cada fonte, como fração da altura.
`ALVO` diz onde ele deve ficar no arquivo final, igual pros três. Se um tema
parecer desalinhado na tela, **mexer só no número dele em HORIZONTE**: aumentar
empurra o horizonte pra cima no arquivo final, diminuir empurra pra baixo. Cada
0,01 vale ~9px numa janela de 930px de altura.

Medir isso automaticamente não é confiável nestas imagens: espacial e dark têm
um arco fino e nítido, o claro tem uma transição difusa sem linha, e todo
detector que testei (crista, gradiente, textura) trava num traço físico
diferente em cada foto. A calibração é visual, por isso os números ficam aqui
como constantes editáveis e não como resultado de medição.
"""
import os, sys
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

FONTES = {
    'espacial': 'upscalemedia-transformed (4).png',
    'claro':    'upscalemedia-transformed (3).png',
    'dark':     'upscalemedia-transformed (1) (1).png',
}
HORIZONTE = {'espacial': 0.742, 'claro': 0.732, 'dark': 0.719}
ALVO   = 0.740      # onde o horizonte fica no arquivo final, igual pros três
ALTURA = 0.96       # fração da altura da fonte que sobrevive ao recorte
ASPECTO = 1.6       # 16:10, comum aos três
SAIDA = (2880, 1800)

raiz = sys.argv[1] if len(sys.argv) > 1 else '../../'
os.makedirs('public/fundos', exist_ok=True)

for tema, arquivo in FONTES.items():
    caminho = os.path.join(raiz, arquivo)
    if not os.path.exists(caminho):
        print('FALTA: %s — veja o cabeçalho deste arquivo' % caminho); continue
    im = Image.open(caminho).convert('RGB')
    W, H = im.size
    h = round(ALTURA * H)
    o = round(H * (HORIZONTE[tema] - ALVO * ALTURA))   # leva o horizonte pro ALVO
    w = round(ASPECTO * h)
    x = round((W - w) / 2)
    if not (0 <= o <= H - h and 0 <= x <= W - w):
        print('FALTA MARGEM em %s: recorte sairia do arquivo (o=%d, x=%d)' % (tema, o, x)); continue
    dest = 'public/fundos/bg-%s.webp' % tema
    im.crop((x, o, x + w, o + h)).resize(SAIDA, Image.LANCZOS).save(dest, 'WEBP', quality=88, method=6)
    print('%-9s %dx%d recortado em (%d,%d) -> %s (%.0f KB)'
          % (tema, w, h, x, o, dest, os.path.getsize(dest) / 1024))
