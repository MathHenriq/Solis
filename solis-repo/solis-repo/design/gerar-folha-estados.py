#!/usr/bin/env python3
"""
Folha de validacao dos 5 estados do simbolo (Camada 3).

    npm run build && python3 design/gerar-folha-estados.py

Monta uma pagina que carrega o CSS REAL do bundle (dist/assets/*.css) — os
keyframes e as camadas sob teste sao os que o app usa, nao uma copia. A marcacao
espelha src/components/SolisEstado.tsx; ela e trivial, o risco todo esta no CSS
e no filtro.

Sai em design/_estados.html, pra ser fotografada por design/capturar-estados.mjs.
"""
import glob
import json
import re

T = json.load(open('docs/solis-tokens.json'))
G = T['states']['glow']
D = re.search(r'd="([^"]+)"', open('design/solis-symbol.svg').read()).group(1)
CSS = sorted(glob.glob('dist/assets/*.css'))[-1]
ROTULOS = T['states']['labelsPtBr']


def simbolo(estado, i):
    return f'''
  <div class="cel">
    <div class="solis-estado" style="width:190px">
      <svg class="solis-brilho" data-estado="{estado}" viewBox="0 0 384.91 220.85" fill-rule="evenodd">
        <defs><filter id="b{i}" x="-140%" y="-140%" width="380%" height="380%" color-interpolation-filters="sRGB">
          <feGaussianBlur in="SourceGraphic" stdDeviation="{G['nearBlur']}" result="p"/>
          <feGaussianBlur in="SourceGraphic" stdDeviation="{G['farBlur']}" result="l"/>
          <feFlood flood-color="{G['nearColor']}" result="c1"/>
          <feComposite in="c1" in2="p" operator="in" result="pt"/>
          <feFlood flood-color="{G['farColor']}" result="c2"/>
          <feComposite in="c2" in2="l" operator="in" result="lt"/>
          <feComponentTransfer in="pt" result="pg"><feFuncA type="linear" slope="{G['nearGain']}"/></feComponentTransfer>
          <feComponentTransfer in="lt" result="lg"><feFuncA type="linear" slope="{G['farGain']}"/></feComponentTransfer>
          <feMerge><feMergeNode in="lg"/><feMergeNode in="pg"/></feMerge>
        </filter></defs>
        <g filter="url(#b{i})"><path d="{D}" fill="currentColor"/></g>
      </svg>
      <svg class="solis-arte" viewBox="0 0 384.91 220.85" fill-rule="evenodd"><path d="{D}" fill="currentColor"/></svg>
    </div>
    <span>{ROTULOS[estado]}<br><i>{estado}</i></span>
  </div>'''


html = f'''<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="../{CSS}">
<style>
 html,body{{margin:0;background:var(--canvas);font:13px system-ui}}
 .grade{{display:grid;grid-template-columns:repeat(5,300px);align-items:center;height:100vh}}
 .cel{{display:flex;flex-direction:column;align-items:center;gap:34px}}
 .cel span{{color:var(--text-secondary);text-align:center;line-height:1.5}}
 .cel i{{opacity:.6;font-style:normal;font-size:11px}}
</style>
<html data-theme="dark">
<div class="grade">
{''.join(simbolo(e, i) for i, e in enumerate(T['states']['order']))}
</div>
'''
open('design/_estados.html', 'w').write(html)
print(f'design/_estados.html  (CSS: {CSS})')
