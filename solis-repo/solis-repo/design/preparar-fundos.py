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
# Calibrado medindo a linha mais brilhante por coluna na faixa x 1210-1420 do
# render (livre de UI), em 4 colunas. O desvio se mantem estavel entre colunas,
# entao e offset real e nao ruido de deteccao.
#   0,01 sobe o horizonte ~9,7px na janela de 930. AUMENTAR sobe.
HORIZONTE = {
    'espacial': 0.742,   # baseline
    'claro':    0.752,   # era 0.732; +0.020 pra subir os ~20px que estava abaixo
    'dark':     0.752,   # era 0.719; +0.033 pra subir os 32px que estava abaixo
}
ALVO   = 0.740      # onde o horizonte fica no arquivo final, igual pros três
# Fração da altura da fonte que sobrevive ao recorte. É por tema porque quanto
# mais o horizonte precisa subir, mais margem o recorte consome: o limite é
# ALTURA <= (1 - HORIZONTE) / (1 - ALVO). Com o dark em 0,752 o teto é 0,9538,
# então 0,96 estourava o arquivo. Só o dark mudou; espacial e claro seguem em
# 0,96 pra que os arquivos deles não sejam tocados.
ALTURA = {'espacial': 0.96, 'claro': 0.95, 'dark': 0.95}
ASPECTO = 1.6       # 16:10, comum aos três
SAIDA = (2880, 1800)

raiz = '../../'
temas = list(FONTES)
for arg in sys.argv[1:]:
    if arg in FONTES: temas = [arg]          # regenerar so um tema
    else: raiz = arg
os.makedirs('public/fundos', exist_ok=True)

for tema in temas:
    arquivo = FONTES[tema]
    caminho = os.path.join(raiz, arquivo)
    if not os.path.exists(caminho):
        print('FALTA: %s — veja o cabeçalho deste arquivo' % caminho); continue
    im = Image.open(caminho).convert('RGB')
    W, H = im.size
    altura = ALTURA[tema]
    h = round(altura * H)
    o = round(H * (HORIZONTE[tema] - ALVO * altura))   # leva o horizonte pro ALVO
    w = round(ASPECTO * h)
    x = round((W - w) / 2)
    if not (0 <= o <= H - h and 0 <= x <= W - w):
        print('FALTA MARGEM em %s: recorte sairia do arquivo (o=%d, x=%d)' % (tema, o, x)); continue
    dest = 'public/fundos/bg-%s.webp' % tema
    im.crop((x, o, x + w, o + h)).resize(SAIDA, Image.LANCZOS).save(dest, 'WEBP', quality=88, method=6)
    print('%-9s %dx%d recortado em (%d,%d) -> %s (%.0f KB)'
          % (tema, w, h, x, o, dest, os.path.getsize(dest) / 1024))


# NOTA — alinhamento entre os tres, medido em 2026-08-27
#
# Medindo a linha mais brilhante por coluna na faixa x 1210-1420 do render (a
# unica larga o bastante e livre de composer e chips), com a animacao de 90s
# congelada:
#
#            x1240  x1300  x1360  x1410   vs espacial
#   espacial   701    711    723    733   baseline
#   claro      719    730    743    754   +19,5px
#   dark       731    743    755    767   +32,0px   -> corrigido para 0.752
#
# O `claro` continua ~19,5px abaixo do espacial. NAO foi mexido porque a
# instrucao foi explicita em nao alterar espacial nem claro. Se for pra alinhar,
# o valor e 0.752 - nao: claro passaria de 0.732 para 0.752 tambem? Nao — o
# ajuste do claro seria 0.732 + 0.0201 = 0.752 por coincidencia aritmetica dos
# desvios. Confirmar antes de aplicar.
#
# Protocolos que NAO funcionam aqui, ja testados: pico de brilho na coluna
# central x=720 (no espacial acha o clarao do ceu, nao o horizonte, e a coluna
# atravessa o composer), deteccao de crista, de gradiente e de textura, e
# correlacao cruzada vertical. Cada um trava num traco fisico diferente porque
# espacial e dark tem arco fino e nitido e o claro tem transicao difusa.
