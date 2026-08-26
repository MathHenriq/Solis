#!/usr/bin/env python3
"""
Calcula o caminho do icone de Configuracoes (roseta de 8 lobulos).

Existe porque acertar 16 pontos de controle no olho nao chega no mesmo lugar:
o icone da referencia tem lobulos macios e simetricos, e simetria de 8 eixos e
coisa pra calcular, nao pra ajustar a mao. Os raios e a tensao foram escolhidos
comparando contra a ampliacao do glifo em referencias/telas/tema-dark.png.

    python3 design/gerar-engrenagem.py     # imprime o path pra colar em icons.tsx
"""
import math

N, R_EXT, R_INT, TENSAO = 8, 9.5, 7.6, 0.78

pontos = []
for i in range(N * 2):
    r = R_EXT if i % 2 == 0 else R_INT
    ang = math.pi / 2 + i * math.pi / N          # comeca no topo
    pontos.append((12 + r * math.cos(ang), 12 - r * math.sin(ang)))

def catmull_rom(p, t):
    """Catmull-Rom fechada -> beziers cubicas. A tensao controla o quanto o
    lobulo fica redondo: perto de 0 vira estrela pontuda, perto de 1 incha."""
    n = len(p)
    for i in range(n):
        p0, p1, p2, p3 = p[(i-1) % n], p[i], p[(i+1) % n], p[(i+2) % n]
        yield ((p1[0] + (p2[0]-p0[0])*t/3, p1[1] + (p2[1]-p0[1])*t/3),
               (p2[0] - (p3[0]-p1[0])*t/3, p2[1] - (p3[1]-p1[1])*t/3), p2)

d = 'M%.2f %.2f' % pontos[0]
for c1, c2, p in catmull_rom(pontos, TENSAO):
    d += 'C%.2f %.2f %.2f %.2f %.2f %.2f' % (c1[0], c1[1], c2[0], c2[1], p[0], p[1])
d += 'Z M12 14.8a2.8 2.8 0 1 0 0-5.6 2.8 2.8 0 0 0 0 5.6z'   # anel central
print(d)
