"""O PC como corpo do servidor, com dois Solis de verdade (26/11/2026): o "PC" de
teste (8767) libera uma pasta, liga a chave "Deixar o servidor usar este PC" e
liga sozinho no servidor de teste (8766, SOLIS_SERVIDOR=1); pelo servidor, ler a
pasta e um arquivo do PC; o registro de ações do PC anota; tirar a chave derruba
a ligação.

Rodar da raiz do app, com os dois no ar:
    $env:SOLIS_TOKEN_TESTE = '...'; backend/.venv/Scripts/python design/nuvem/testar_corpo_remoto.py
"""
import os
import tempfile
import time
from pathlib import Path

import httpx

PC = 'http://127.0.0.1:8767'
SERVIDOR = 'http://127.0.0.1:8766'
TOKEN = os.environ['SOLIS_TOKEN_TESTE']
NO_SERVIDOR = {'Authorization': f'Bearer {TOKEN}'}


def esperar(condicao, prazo: float) -> float | None:
    t = time.perf_counter()
    while time.perf_counter() - t < prazo:
        if condicao():
            return time.perf_counter() - t
        time.sleep(0.5)
    return None


pasta = Path(tempfile.mkdtemp(prefix='solis-pc-'))
(pasta / 'notas-do-pc.txt').write_text('A reunião com a Ana é sexta às 15h.', encoding='utf-8')
httpx.put(f'{PC}/pc/pastas', json={'pastas': [str(pasta)]}).raise_for_status()

ligado = lambda: httpx.get(f'{SERVIDOR}/corpo/pc', headers=NO_SERVIDOR).json()  # noqa: E731
# Começa sem a chave (de uma rodada anterior, ela pode estar ligada).
httpx.put(f'{PC}/servidor', json={'endereco': SERVIDOR, 'usa_pc': False}).raise_for_status()
assert esperar(lambda: not ligado()['ligado'], 40) is not None, 'o PC continua ligado sem a chave'
httpx.put(f'{PC}/servidor', json={'endereco': SERVIDOR, 'token': TOKEN, 'usa_pc': True}).raise_for_status()
levou = esperar(lambda: ligado()['ligado'], 30)
assert levou is not None, 'o PC não ligou no servidor em 30 s'
print(f'o PC ligou no servidor em {levou:.1f} s depois da chave: {ligado()}')
print('o PC diz:', {k: v for k, v in httpx.get(f'{PC}/servidor').json().items() if k.startswith('pc_') or k == 'usa_pc'})

# Pelo servidor (o celular), ler do PC.
t = time.perf_counter()
r = httpx.post(f'{SERVIDOR}/corpo/ler', headers=NO_SERVIDOR, timeout=30,
               json={'ferramenta': 'mcp__solis__listar_pasta', 'entrada': {'caminho': ''}}).json()
print(f'listar a pasta do PC ({(time.perf_counter() - t) * 1000:.0f} ms):', r)
assert r['ok'] and 'notas-do-pc.txt' in r['saida'] or pasta.name in r['saida']
t = time.perf_counter()
r = httpx.post(f'{SERVIDOR}/corpo/ler', headers=NO_SERVIDOR, timeout=30,
               json={'ferramenta': 'mcp__solis__ler_arquivo', 'entrada': {'caminho': str(pasta / 'notas-do-pc.txt')}}).json()
print(f'ler o arquivo do PC ({(time.perf_counter() - t) * 1000:.0f} ms):', r)
assert r['ok'] and 'sexta às 15h' in r['saida']
fora = httpx.post(f'{SERVIDOR}/corpo/ler', headers=NO_SERVIDOR, timeout=30,
                  json={'ferramenta': 'mcp__solis__ler_arquivo', 'entrada': {'caminho': 'C:/Windows/win.ini'}}).json()
print('fora das pastas liberadas:', fora)
assert not fora['ok']

registro = httpx.get(f'{PC}/pc/registro').json()
acoes = registro if isinstance(registro, list) else registro.get('acoes', [])
print('o registro do PC anotou:', [(a.get('ferramenta'), a.get('ok')) for a in acoes[:3]])

# Tirar a chave: a ligação cai (o PC confere a cada pulso, 25 s).
httpx.put(f'{PC}/servidor', json={'endereco': SERVIDOR, 'usa_pc': False}).raise_for_status()
levou = esperar(lambda: not ligado()['ligado'], 40)
assert levou is not None, 'a ligação não caiu sem a chave'
print(f'sem a chave, a ligação caiu em {levou:.1f} s')
print('ok: o PC é o corpo do servidor, só com a chave, e só o que ele libera')
