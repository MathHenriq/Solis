#!/usr/bin/env python3
"""
Gera src/styles/tokens.css a partir de docs/solis-tokens.json.

Existe pra fazer valer a regra do HANDOFF ("o Tailwind nao deve ter nenhum valor
que nao venha do JSON"). Enquanto o CSS for gerado, nao ha como um hex entrar na
interface sem passar pela fonte de verdade primeiro.

    python3 design/gerar-tokens-css.py        # a partir da raiz do repo
"""
import json

T = json.load(open('docs/solis-tokens.json', encoding='utf-8'))
PAPEIS = [('canvas', '--canvas'), ('divider', '--divider'), ('erro', '--erro'),
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
    w('.solis-brilho > svg { display: block; width: 100%; height: auto; overflow: visible; }')
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
    R = G['reativo']
    w('')
    w('/* Reativo (states.glow.reativo, aprovado em 09/11/2026): opacity e transform vem do nivel do')
    w(' * microfone, escritos por src/nivel.ts; o keyframe sai. Parte do minimo. */')
    w('.solis-brilho[data-reativo] { animation: none; opacity: %s; transition: opacity %sms linear, transform %sms linear; }'
      % (R['opacity'][0], R['passoMs'], R['passoMs']))

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

# --- escala vertical -------------------------------------------------------
# A Fase 2 inteira foi medida numa janela de 1440x930. Um navegador da ~693px de
# altura util, e com o ritmo em px absolutos a pagina passava a rolar e o bloco de
# perfil era espremido. Cada medida vertical vira aqui a PROPORCAO que ela tinha
# em 930, com piso e teto: em 930 o vh bate no teto e a referencia fica intacta,
# px a px; abaixo disso tudo encolhe junto e as relacoes entre os elementos se
# mantem. Ver layout.escalaVertical no JSON.
EV = T['layout']['escalaVertical']
H_REF, PISO = EV['alturaDeReferencia'], EV['piso']

def vy(valor):
    """'69px' -> 'clamp(55px, 7.419vh, 69px)'."""
    px = float(str(valor).replace('px', ''))
    return 'clamp(%gpx, %.3fvh, %gpx)' % (round(px * PISO), px * 100.0 / H_REF, px)

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
w('  --sidebar-logo: %s;'       % vy(sb['logoWidth']))
w('  --sidebar-pitch: %s;'      % vy(sb['itemPitch']))
w('  --sidebar-label: %s;'      % sb['labelSize'])
w('  --sidebar-icon-inset: %s;' % sb['iconInset'])
w('  --sidebar-label-inset: %s;'% sb['labelInset'])
w('  --sidebar-padding-top: %s;' % vy(sb['paddingTop']))
w('  --sidebar-nav-ink: %s;'     % vy(sb['navFirstItemInk']))
pf = sb['profile']
w('  --perfil-altura: %s;'    % vy(pf['blockHeight']))
w('  --perfil-avatar: %s;'    % pf['avatarSize'])
w('  --perfil-avatar-x: %s;'  % pf['avatarInset'])
w('  --perfil-avatar-y: %s;'  % pf['avatarTopInset'])
w('  --perfil-nome: %s;'      % pf['nameSize'])
w('  --perfil-status: %s;'    % pf['statusSize'])
w('  --perfil-ponto: %s;'     % pf['statusDot'])
w('  --composer-height: %s;'    % cp['height'])
w('  --composer-max: %s;'       % cp['maxWidth'])
w('  --composer-width: %s;'     % cp['width'])
w('  --conversa-ancora: %s;'    % cp['anchorLeft'])
cv = T['layout']['conversa']
w('  --conversa-topo: %s;'      % vy(cv['topPadding']))
w('  --conversa-sub: %s;'       % vy(cv['subtitleGap']))
w('  --conversa-campo: %s;'     % vy(cv['composerGap']))
w('  --conversa-chips: %s;'     % vy(cv['chipsGap']))
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
w('  --mem-acao-h: %s;' % mem['actionHeight'])
w('  /* Acoes da Memoria (corrigir, esquecer). Ver layout.memoria.acoes - desenho proprio. */')
ma = T['layout']['memoria']['acoes']
for chave, var in [('iconSize','--mac-icone'), ('iconHit','--mac-alvo'), ('dateGap','--mac-data-gap'),
                   ('editRadius','--mac-campo-raio'), ('editPadX','--mac-campo-px'), ('editPadY','--mac-campo-py'),
                   ('buttonHeight','--mac-botao-h'), ('buttonPadX','--mac-botao-px'), ('buttonRadius','--mac-botao-raio'),
                   ('buttonGap','--mac-botao-gap'), ('buttonTop','--mac-botao-top'), ('buttonTextSize','--mac-botao-texto'),
                   ('lockSize','--mac-cadeado'), ('toastBottom','--mac-aviso-base'), ('toastHeight','--mac-aviso-h'),
                   ('toastPadX','--mac-aviso-px'), ('toastRadius','--mac-aviso-raio')]:
    w('  %s: %s;' % (var, ma[chave]))
w('')
w('  /* Estado vazio/erro — medido em 10-memoria-vazio.png. Ver layout.estadoVazio. */')
ev = T['layout']['estadoVazio']
for chave, var in [('iconSize','--vazio-icone'), ('iconStroke','--vazio-traco'),
                   ('titleSize','--vazio-titulo'), ('bodySize','--vazio-corpo'),
                   ('bodyLineHeight','--vazio-corpo-lh'), ('iconTitleGap','--vazio-icone-gap'),
                   ('titleBodyGap','--vazio-titulo-gap'), ('centerY','--vazio-centro-y')]:
    w('  %s: %s;' % (var, ev[chave]))
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
w('')
w('  /* Configuracoes e barra de icones — ver layout.configuracoes e layout.iconBar. */')
cfg, ib = T['layout']['configuracoes'], T['layout']['iconBar']
for chave, var in [('cardTop','--cfg-card-top'), ('cardPadding','--cfg-card-pad'),
                   ('cardRadius','--cfg-card-raio'), ('cardInsetLeft','--cfg-inset-l'),
                   ('cardInsetRight','--cfg-inset-r'), ('sectionTitleSize','--cfg-secao'),
                   ('rowLabelSize','--cfg-rotulo'), ('rowHintSize','--cfg-dica'),
                   ('rowHintTop','--cfg-dica-top'), ('rowPadY','--cfg-linha-pad'),
                   ('thumbWidth','--cfg-mini-l'), ('thumbGap','--cfg-mini-gap'),
                   ('thumbRadius','--cfg-mini-raio'), ('thumbNameTop','--cfg-mini-nome-top'),
                   ('segmentWidth','--cfg-seg-l'), ('segmentHeight','--cfg-seg-h'),
                   ('segmentRadius','--cfg-seg-raio'), ('switchWidth','--cfg-sw-l'),
                   ('switchHeight','--cfg-sw-h')]:
    w('  %s: %s;' % (var, cfg[chave]))
w('  --cfg-mini-razao: %s;' % cfg['thumbRatio'])
w('  /* Menu do Conhecimento - desenho proprio, aprovado. Ver layout.conhecimento. */')
kn = T['layout']['conhecimento']
for chave, var in [('menuWidth','--kn-menu-l'), ('menuPad','--kn-menu-pad'), ('menuRadius','--kn-menu-raio'),
                   ('menuItemHeight','--kn-menu-item-h'), ('menuItemPadX','--kn-menu-item-px'),
                   ('menuIconGap','--kn-menu-icone-gap'), ('menuTop','--kn-menu-top'),
                   ('addressWidth','--kn-endereco-l')]:
    w('  %s: %s;' % (var, kn[chave]))
w('  /* Tarefas - desenho proprio, PROVISORIO. Ver layout.tarefas. */')
tf = T['layout']['tarefas']
for chave, var in [('dateWidth', '--tf-data-l'), ('timeWidth', '--tf-hora-l')]:
    w('  %s: %s;' % (var, tf[chave]))
w('  /* Chamada: a ilha preta no topo - desenho proprio, PROVISORIO. Ver layout.chamada. */')
ch = T['layout']['chamada']
for chave, var in [('top', '--ch-topo'), ('fill', '--ch-fundo'), ('text', '--ch-texto'), ('textMuted', '--ch-texto-2'),
                   ('radiusTiny', '--ch-raio-min'), ('radiusCompact', '--ch-raio-pilula'), ('radiusOpen', '--ch-raio-aberta'),
                   ('symbolOpen', '--ch-simbolo'), ('symbolSmall', '--ch-simbolo-p'), ('spring', '--ch-mola')]:
    w('  %s: %s;' % (var, ch[chave]))
for chave, pre in [('tiny', '--ch-min'), ('compact', '--ch-pilula'), ('listening', '--ch-ouvindo'), ('answer', '--ch-resposta')]:
    w('  %s-l: %s; %s-a: %s;' % (pre, ch[chave][0], pre, ch[chave][1]))
for chave, var in [('morphMs', '--ch-forma'), ('contentMs', '--ch-conteudo'), ('contentDelayMs', '--ch-conteudo-atraso')]:
    w('  %s: %sms;' % (var, ch[chave]))
w('  /* Agenda - medida na referencia 16; o que e novo, PROVISORIO. Ver layout.agenda. */')
ag = T['layout']['agenda']
for chave, var in [('listIndent', '--ag-recuo'), ('lineX', '--ag-linha-x'), ('titleX', '--ag-titulo-x'),
                   ('rowPadTop', '--ag-pad-cima'), ('rowPadBottom', '--ag-pad-baixo'), ('subGap', '--ag-sub-gap'),
                   ('dot', '--ag-ponto'), ('dotNow', '--ag-ponto-vez'), ('lineWidth', '--ag-linha-l'),
                   ('lineColor', '--ag-linha-cor'), ('dotColor', '--ag-ponto-cor'), ('cardOutLeft', '--ag-cartao-esq'),
                   ('cardOutRight', '--ag-cartao-dir'), ('cardMarginY', '--ag-cartao-my'), ('cardPadY', '--ag-cartao-py'),
                   ('cardRadius', '--ag-cartao-raio'), ('cardBorder', '--ag-cartao-borda'), ('arrowWidth', '--ag-seta-l'),
                   ('todayWidth', '--ag-hoje-l'), ('buttonGap', '--ag-botoes-gap'), ('durationWidth', '--ag-duracao-l'),
                   ('placeWidth', '--ag-onde-l')]:
    w('  %s: %s;' % (var, ag[chave]))
w('  /* Cartao Cerebros - desenho proprio, aprovado. Ver layout.configuracoes.cerebros. */')
for chave, var in [('cardGap','--cer-cartao-gap'), ('orderIcon','--cer-seta'), ('orderHit','--cer-seta-alvo'),
                   ('controlsGap','--cer-controles-gap'), ('positionWidth','--cer-posicao'),
                   ('textMax','--cer-texto-max'), ('rowPadY','--cer-linha-pad')]:
    w('  %s: %s;' % (var, cfg['cerebros'][chave]))
for chave, var in [('width','--barra-l'), ('height','--barra-h'), ('bottom','--barra-base'),
                   ('radius','--barra-raio'), ('iconSize','--barra-icone'),
                   ('activeBoxSize','--barra-ativo'), ('activeBoxRadius','--barra-ativo-raio'),
                   ('topBarHeight','--topo-h'), ('surface','--barra-fundo'),
                   ('shadow','--barra-sombra')]:
    w('  %s: %s;' % (var, ib[chave]))
w('  --chip-texto: %s;' % cp['chipTextSize'])
mo = T['motion']
for chave, var in [('screenIn','--mov-tela'), ('screenShift','--mov-desloc'),
                   ('press','--mov-toque'), ('hover','--mov-hover')]:
    w('  %s: %s;' % (var, mo[chave]))
w('')
th = T['layout']['thread']
for chave, var in [('bubbleMaxWidth','--th-balao-max'), ('bubblePadX','--th-balao-px'),
                   ('bubblePadY','--th-balao-py'), ('bubbleRadius','--th-balao-raio'),
                   ('avatarSize','--th-avatar'), ('avatarGap','--th-avatar-gap'),
                   ('turnGap','--th-turno-gap'), ('paragraphGap','--th-par-gap'),
                   ('composerHeight','--th-composer-h'), ('composerBottom','--th-composer-base'),
                   ('timeSize','--th-hora'), ('textMaxWidth','--th-texto-max'),
                   ('columnMax','--th-coluna')]:
    w('  %s: %s;' % (var, th[chave]))
w('  /* Etapas da resposta. Ver layout.thread.etapas no JSON. */')
et = th['etapas']
for chave, var in [('textSize','--et-texto'), ('rowPitch','--et-passo'), ('textIndent','--et-recuo'),
                   ('iconSize','--et-icone'), ('dotSize','--et-ponto'), ('ringSize','--et-anel'),
                   ('futureOpacity','--et-futura'), ('foldTextSize','--et-dobra-texto'),
                   ('foldIndent','--et-dobra-recuo'), ('foldGap','--et-dobra-gap'), ('afterHeader','--et-cabecalho'),
                   ('chipHeight','--et-chip-h'), ('chipTextSize','--et-chip-texto'),
                   ('chipPadX','--et-chip-px'), ('chipIconGap','--et-chip-icone-gap'),
                   ('chipRadius','--et-chip-raio'), ('chipTop','--et-chip-top'),
                   ('chipBorderMix','--et-chip-borda'), ('chipFillMix','--et-chip-fundo'),
                   # PROVISÓRIO: o cartão de aprovação do agente (desenho próprio).
                   ('approvalPadY','--et-apr-py'), ('approvalPadX','--et-apr-px'),
                   ('approvalRadius','--et-apr-raio'), ('approvalGap','--et-apr-gap')]:
    w('  %s: %s;' % (var, et[chave]))
w('  /* Lista de conversas na sidebar. Ver layout.recentes no JSON (PROVISORIO). */')
rc = T['layout']['recentes']
for chave, var in [('sectionTop','--rc-topo'), ('rowInset','--rc-recuo'), ('rowPadX','--rc-px'),
                   ('rowHeight','--rc-linha-h'), ('rowRadius','--rc-raio'), ('textSize','--rc-texto'),
                   ('labelSize','--rc-rotulo'), ('labelTop','--rc-rotulo-top'), ('labelHeight','--rc-rotulo-h'),
                   ('plusSize','--rc-mais'), ('iconSize','--rc-icone'), ('iconGap','--rc-icone-gap'),
                   ('drawerWidth','--rc-gaveta')]:
    w('  %s: %s;' % (var, rc[chave]))
w('  --composer-radius: %s;'    % cp['radius'])
w('')
w('  /* Barra de rolagem. Ver appearance.scrollbar no JSON. */')
sc = T['appearance']['scrollbar']
w('  --scroll-larg: %s;'        % sc['width'])
w('  --scroll-recuo: %s;'       % sc['inset'])
w('  --scroll-polegar: %s;'     % sc['thumb'])
w('  --scroll-polegar-hover: %s;' % sc['thumbHover'])
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
    w('  --mem-hover-forte: %s;' % (mem['hoverTintStrong'] if nome == 'dark' else mem['hoverTintClaroStrong']))
    rc = T['layout']['recentes']
    w('  --rc-ativo: %s;' % (rc['activeTint'] if nome == 'dark' else rc['activeTintClaro']))
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

# utf-8 e quebra de linha LF explícitos: no Windows o padrão é cp1252 com CRLF,
# e o arquivo deixaria de bater com o commitado (o checar-regras lê em utf-8).
open('src/styles/tokens.css', 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
print('src/styles/tokens.css — %d temas (%s), padrao %s' % (len(TEMAS), ', '.join(TEMAS), PADRAO))
