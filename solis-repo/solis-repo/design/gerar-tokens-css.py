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
w('  --composer-radius: %s;'    % cp['radius'])
w('  --chip-height: %s;'        % cp['actionChipHeight'])
w('')
w('  /* tipografia — fontFamilyDisplay so na saudacao (contraste intencional) */')
w('  --ease: %s;' % T['motion']['easing'])
w('  --font-body: %s;' % T['typography']['fontFamilyBody'])
w('  --font-display: %s;' % T['typography']['fontFamilyDisplay'])
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
    cena = t.get('scene')
    w('  --scene: %s;' % ('none' if cena == 'none' else 'var(--scene-%s)' % cena))
    w('}')
w('')
w('/* A cena e uma CAMADA sobre --canvas, nao o fundo em si: com "Exibir imagem')
w(' * de fundo" desligado ela some e sobra a versao solida da paleta do mesmo')
w(' * tema. Nenhuma cor nova precisa existir pra isso. */')
w('[data-scene="off"] { --scene: none; }')
w('')
w('body { background: var(--canvas); color: var(--text-primary); font-family: var(--font-body); }')
w('')
w('@media (prefers-reduced-motion: reduce) {')
w('  /* PERFORMANCE.md: todas as duracoes vao a ~0 */')
w('  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }')
w('}')

open('src/styles/tokens.css', 'w').write('\n'.join(L) + '\n')
print('src/styles/tokens.css — %d temas (%s), padrao %s' % (len(TEMAS), ', '.join(TEMAS), PADRAO))
