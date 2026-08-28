#!/usr/bin/env python3
"""
Gera src/styles/tokens.css a partir de docs/solis-tokens.json.

Existe pra fazer valer a regra do HANDOFF ("o Tailwind nao deve ter nenhum valor
que nao venha do JSON"). Enquanto o CSS for gerado, nao ha como um hex entrar na
interface sem passar pela fonte de verdade primeiro.

    python3 design/gerar-tokens-css.py        # a partir da raiz do repo
"""
import json

T = json.load(open('docs/solis-tokens.json'))
PAPEIS = [('canvas', '--canvas'), ('divider', '--divider'),
          ('textPrimary', '--text-primary'), ('textSecondary', '--text-secondary'),
          ('textPlaceholder', '--text-placeholder'), ('accent', '--accent')]
TEMAS = [t for t in T['themes'] if not t.startswith('_')]
PADRAO = T['appearance']['theme']['defaultOnFirstInstall']

CENA = T['scenes']

def _frac(v):
    return float(str(v).replace('%', '').replace('vh', '')) / 100.0

# A banda vive colada na base: topo dela = 1 - altura. Converter um ponto dado em
# fracao da JANELA pra fracao da BANDA e so tirar o topo e dividir pela altura.
_ALT = _frac(CENA['height'])
_TOPO = 1.0 - _ALT
def _naBanda(v):
    return (_frac(v) - _TOPO) / _ALT

_S, _E = _naBanda(CENA['fadeFromViewport']), _naBanda(CENA['fadeToViewport'])
# smoothstep amostrado em 9 pontos — rampa linear crua deixa banding de Mach nas
# duas pontas, e o gradiente e grande na tela (15% da altura da janela).
_PARADAS = []
for _i in range(9):
    _t = _i / 8.0
    _a = _t * _t * (3 - 2 * _t)
    _pos = _S + _t * (_E - _S)
    _PARADAS.append('rgb(0 0 0 / %.3f) %.2f%%' % (_a, _pos * 100))
_PARADAS.append('rgb(0 0 0 / 1) 100%')
MASCARA = ', '.join(_PARADAS)

L = []
w = L.append
w('/* GERADO por design/gerar-tokens-css.py — nao editar a mao.')
w(' * Fonte de verdade: docs/solis-tokens.json. Mexeu no token, roda o script.')
w(' *')
w(' * O tema e trocado por [data-theme] no elemento raiz, nunca por Context de')
w(' * React distribuindo cor: a Camada 1 do SOLIS_SIGNATURE.md e montada uma vez')
w(' * no shell e nao pode remontar na troca de tema. Trocar um atributo so')
w(' * repinta; trocar o valor de um Context re-renderiza a arvore. */')
w('')

w(':root {')
w('  /* escala — independente de tema */')
for k, v in T['radius'].items():   w('  --radius-%s: %s;' % (k, v))
for k, v in T['spacing'].items():  w('  --space-%s: %s;' % (k.replace('2xl','2xl'), v))
for k, v in T['icon']['size'].items(): w('  --icon-%s: %s;' % (k, v))
w('')
w('  /* medidos na Fase 2 — ver docs/MEDICOES_FASE2.md */')
sb, cp = T['layout']['sidebar'], T['layout']['composer']
w('  --sidebar-width: %s;'      % sb['width'])
w('  --sidebar-icon: %s;'       % sb['iconSize'])
w('  --sidebar-logo: %s;'       % sb['logoWidth'])
w('  --sidebar-pitch: %s;'      % sb['itemPitch'])
w('  --sidebar-label: %s;'      % sb['labelSize'])
w('  --sidebar-icon-inset: %s;' % sb['iconInset'])
w('  --sidebar-label-inset: %s;'% sb['labelInset'])
w('  --composer-height: %s;'    % cp['height'])
w('  --composer-width: %s;'     % cp['width'])
w('')
w('  /* A cena e uma BANDA ancorada na base da area de conteudo, nao um fundo de')
w('   * tela cheia. Ver solis-tokens.json -> scenes._ancoragem e ._geometria. */')
w('  --solis-cena-altura: %s;' % CENA['height'])
w('  --solis-bg-position-y: %s;' % CENA['positionY'])
w('  /* Mascara do topo da banda: alpha 0 -> 1 entre %s e %s da altura da JANELA,' % (CENA['fadeFromViewport'], CENA['fadeToViewport']))
w('   * convertidos aqui pra coordenada da propria banda (0% = topo da banda).')
w('   * Acima do primeiro stop o alpha e zero, entao o texto da tela cai em canvas')
w('   * chapado e o contraste volta a ser o dos tokens. */')
w('  --solis-cena-mascara: linear-gradient(to bottom, %s);' % MASCARA)
w('  --composer-radius: %s;'    % cp['radius'])
w('  --chip-height: %s;'        % cp['actionChipHeight'])
w('')
w('  /* tipografia — fontFamilyDisplay so na saudacao (contraste intencional) */')
w('  --ease: %s;' % T['motion']['easing'])
w('  --font-body: %s;' % T['typography']['fontFamilyBody'])
w('  --font-display: %s;' % T['typography']['fontFamilyDisplay'])
w('  --font-wordmark: %s;' % T['typography']['fontFamilyWordmark'])
w('  --wordmark-tracking: %s;' % T['typography']['wordmarkTracking'])
for k, v in T['typography']['scale'].items():
    w('  --text-%s: %s;' % (k, v['size']))
    w('  --weight-%s: %s;' % (k, v['weight']))
w('}')
w('')

w('/* Tema padrao na primeira instalacao: %s. O atributo tem que estar no HTML' % PADRAO)
w(' * ANTES do primeiro paint — senao o app pisca num tema e troca pro outro. */')
for nome in TEMAS:
    t = T['themes'][nome]
    w('')
    w('[data-theme="%s"] {' % nome)
    for chave, var in PAPEIS:
        w('  %s: %s;' % (var, t[chave]))
    cena = T['scenes'][t['scene']]
    w('  --solis-horizon-image: url(\'%s\');' % cena['asset'])
    w('}')
w('')
w('/* A cena e uma CAMADA sobre --canvas, nao o fundo em si: com "Exibir imagem')
w(' * de fundo" desligado ela some e sobra a versao solida da paleta do mesmo')
w(' * tema. Nenhuma cor nova precisa existir pra isso. */')
w('[data-scene="off"] { --solis-horizon-image: none; }')
w('')
w('body { background: var(--canvas); color: var(--text-primary); font-family: var(--font-body); }')
w('')
w('@media (prefers-reduced-motion: reduce) {')
w('  /* PERFORMANCE.md: todas as duracoes vao a ~0 */')
w('  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }')
w('}')

open('src/styles/tokens.css', 'w').write('\n'.join(L) + '\n')
print('src/styles/tokens.css — %d temas (%s), padrao %s' % (len(TEMAS), ', '.join(TEMAS), PADRAO))
