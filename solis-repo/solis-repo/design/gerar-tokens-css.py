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

# ---- Camada 3: os 5 estados. So opacity e transform, nunca filter num keyframe.
G, M = T['states']['glow'], T['states']['motion']
def _estados(w):
    w('')
    w('/* Camada 3 — os 5 estados do simbolo. Ver src/components/SolisEstado.tsx.')
    w(' *')
    w(' * O filtro do glow e ESTATICO e mora no SVG; aqui so anda opacity e transform')
    w(' * da camada de brilho. Medido no proprio simbolo, 6s a 60fps: camada parada 1ms')
    w(' * de main thread, animando opacity+transform 3ms, e com `filter` dentro do')
    w(' * keyframe 48ms com um recalculo de estilo por frame. E a regra 1 do')
    w(' * PERFORMANCE.md com numero medido. */')
    w('.solis-estado { position: relative; display: block; }')
    w('.solis-estado > svg { display: block; width: 100%; height: auto; overflow: visible; }')
    w('.solis-brilho { position: absolute; inset: 0; color: %s; will-change: transform, opacity; }' % G['nearColor'])
    w('.solis-arte { position: relative; color: %s; }' % G['artColor'])
    for est in T['states']['order']:
        p = M[est]
        w('')
        w('@keyframes solis-%s {' % est)
        w('  0%%, 100%% { opacity: %s; transform: scale(%s); }' % (p['opacity'][0], p['scale'][0]))
        w('  50%%      { opacity: %s; transform: scale(%s); }' % (p['opacity'][1], p['scale'][1]))
        w('}')
        w('.solis-brilho[data-estado="%s"] { animation: solis-%s %s ease-in-out infinite; }'
          % (est, est, p['duration']))

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
w('  --sidebar-padding-top: %s;' % sb['paddingTop'])
w('  --sidebar-nav-ink: %s;'     % sb['navFirstItemInk'])
pf = sb['profile']
w('  --perfil-altura: %s;'    % pf['blockHeight'])
w('  --perfil-avatar: %s;'    % pf['avatarSize'])
w('  --perfil-avatar-x: %s;'  % pf['avatarInset'])
w('  --perfil-avatar-y: %s;'  % pf['avatarTopInset'])
w('  --perfil-nome: %s;'      % pf['nameSize'])
w('  --perfil-status: %s;'    % pf['statusSize'])
w('  --perfil-ponto: %s;'     % pf['statusDot'])
w('  --composer-height: %s;'    % cp['height'])
w('  --composer-width: %s;'     % cp['width'])
w('')
w('  /* Memoria — medido em 09-memoria.png. Ver layout.memoria no JSON. */')
mem = T['layout']['memoria']
for chave, var in [('padLeft','--mem-pad-l'), ('padRight','--mem-pad-r'),
                   ('titleTop','--mem-titulo-top'), ('titleSize','--mem-titulo'),
                   ('countGap','--mem-contagem-gap'), ('countSize','--mem-contagem'),
                   ('searchGap','--mem-busca-gap'), ('searchHeight','--mem-busca-h'),
                   ('searchRadius','--mem-busca-raio'), ('listGap','--mem-lista-gap'),
                   ('itemPadY','--mem-item-pad-y'), ('itemTextSize','--mem-item-texto'),
                   ('itemLineHeight','--mem-item-lh'), ('originTop','--mem-origem-top'),
                   ('originSize','--mem-origem'), ('dateSize','--mem-data'),
                   ('textMaxWidth','--mem-texto-max')]:
    w('  %s: %s;' % (var, mem[chave]))
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
    # O veu do hover clareia no tema escuro e escurece nos claros — o mesmo hex
    # nao serve aos tres, mas o mesmo COMPONENTE serve, porque le a variavel.
    mem = T['layout']['memoria']
    w('  --mem-hover: %s;' % (mem['hoverTint'] if nome == 'dark' else mem['hoverTintClaro']))
    w('}')
w('')
w('/* A cena e uma CAMADA sobre --canvas, nao o fundo em si: com "Exibir imagem')
w(' * de fundo" desligado ela some e sobra a versao solida da paleta do mesmo')
w(' * tema. Nenhuma cor nova precisa existir pra isso. */')
w('[data-scene="off"] { --solis-horizon-image: none; }')
w('')
w('body { background: var(--canvas); color: var(--text-primary); font-family: var(--font-body); }')
w('')
_estados(w)
w('')
w('@media (prefers-reduced-motion: reduce) {')
w('  /* PERFORMANCE.md: todas as duracoes vao a ~0 */')
w('  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }')
w('}')

open('src/styles/tokens.css', 'w').write('\n'.join(L) + '\n')
print('src/styles/tokens.css — %d temas (%s), padrao %s' % (len(TEMAS), ', '.join(TEMAS), PADRAO))
