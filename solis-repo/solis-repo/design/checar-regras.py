#!/usr/bin/env python3
"""
Trava as regras do projeto que ja foram quebradas alguma vez.

    python3 design/checar-regras.py        # a partir da raiz do repo
    npm run checar

Sai com codigo 1 se alguma quebrar. Cada checagem existe por causa de um erro
que aconteceu de verdade, nao por hipotese:

1. filter/box-shadow animado em loop — o PERFORMANCE.md proibe, o prototipo
   fazia, foi corrigido na Fase 0 e VOLTOU na Fase 2 via tailwind.config.js.
   Duas vezes e padrao, nao acidente.
2. lista de navegacao duplicada — a regra 4 do CLAUDE.md existe porque telas
   geradas sairam com um item a mais/a menos entre si.
3. constantes de tema duplicadas no bootstrap inline do index.html, que nao
   pode importar do TypeScript.
4. tokens.css fora de sincronia com solis-tokens.json.
"""
import json, re, subprocess, sys, tempfile, os

erros = []
def falha(regra, detalhe):
    erros.append('%s\n    %s' % (regra, detalhe))

def ler(p):
    try: return open(p, encoding='utf-8').read()
    except FileNotFoundError: return None

# 1 — animacao proibida --------------------------------------------------------
PROIBIDO = re.compile(r'\b(filter|box-shadow|backdrop-filter|boxShadow|backdropFilter)\b')

def sem_comentarios(s):
    """Comentario que MENCIONA a regra nao pode disparar a regra — o comentario
    que explica a correcao vive exatamente dentro do bloco checado."""
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    return re.sub(r'//[^\n]*', '', s)
tw = ler('tailwind.config.js')
if tw:
    bloco = re.search(r'keyframes:\s*\{(.*?)\n      \},', tw, re.S)
    if bloco and PROIBIDO.search(sem_comentarios(bloco.group(1))):
        falha('PERFORMANCE.md: propriedade nao-compositora animada em loop',
              'tailwind.config.js -> keyframes usa filter/box-shadow. So transform e opacity.')
for css in ('src/styles/index.css', 'src/styles/tokens.css'):
    s = ler(css)
    if s:
        for m in re.finditer(r'@keyframes[^{]*\{.*?\n\}', s, re.S):
            if PROIBIDO.search(sem_comentarios(m.group(0))):
                falha('PERFORMANCE.md: propriedade nao-compositora animada em loop',
                      '%s -> @keyframes usa filter/box-shadow.' % css)

# 2 — navegacao com fonte unica ------------------------------------------------
tokens = json.load(open('docs/solis-tokens.json', encoding='utf-8'))
oficial = tokens['navigation']['items']
nav = ler('src/nav-items.ts')
if nav:
    no_codigo = re.findall(r"rotulo:\s*'([^']+)'", nav)
    if no_codigo != oficial:
        falha('CLAUDE.md regra 4: lista de navegacao divergente',
              'src/nav-items.ts %s != solis-tokens.json %s' % (no_codigo, oficial))

# 3 — bootstrap de tema em sincronia com o TypeScript --------------------------
ts, html = ler('src/theme/theme.ts'), ler('index.html')
if ts and html:
    def const_ts(nome):
        m = re.search(r"%s\s*(?::\s*\w+\s*)?=\s*'([^']+)'" % nome, ts); return m.group(1) if m else None
    def const_html(nome):
        m = re.search(r"var %s = '([^']+)'" % nome, html); return m.group(1) if m else None
    for nome in ('CHAVE_TEMA', 'CHAVE_CENA', 'TEMA_PADRAO'):
        a, b = const_ts(nome), const_html(nome)
        if a is None or b is None or a != b:
            falha('bootstrap de tema fora de sincronia',
                  '%s: theme.ts=%r index.html=%r' % (nome, a, b))
    temas_ts = re.findall(r"'(\w+)'", re.search(r'TEMAS = \[(.*?)\]', ts, re.S).group(1))
    temas_html = re.findall(r"'(\w+)'", re.search(r"var TEMAS = \[(.*?)\]", html, re.S).group(1))
    if temas_ts != temas_html:
        falha('bootstrap de tema fora de sincronia',
              'TEMAS: theme.ts=%s index.html=%s' % (temas_ts, temas_html))
    oficiais = [t for t in tokens['themes'] if not t.startswith('_')]
    if temas_ts != oficiais:
        falha('temas divergem da fonte de verdade',
              'theme.ts=%s solis-tokens.json=%s' % (temas_ts, oficiais))
    padrao = tokens['appearance']['theme']['defaultOnFirstInstall']
    if const_ts('TEMA_PADRAO') != padrao:
        falha('tema padrao divergente',
              'theme.ts=%r solis-tokens.json=%r' % (const_ts('TEMA_PADRAO'), padrao))

# 4 — tokens.css regenerado bate com o commitado -------------------------------
atual = ler('src/styles/tokens.css')
if atual:
    subprocess.run([sys.executable, 'design/gerar-tokens-css.py'],
                   check=True, capture_output=True)
    if ler('src/styles/tokens.css') != atual:
        falha('src/styles/tokens.css fora de sincronia com solis-tokens.json',
              'rode: npm run tokens')

if erros:
    print('FALHOU:\n\n' + '\n\n'.join('  - ' + e for e in erros))
    sys.exit(1)
print('ok — 4 checagens passaram')
