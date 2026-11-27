"""Juntar o PC e o servidor com dois Solis de verdade (26/11/2026): o "PC" de teste
(porta 8767, modo normal) e o servidor de teste (8766, SOLIS_SERVIDOR=1), cada
um com o seu banco. Pelo que a tela faz: conversas no PC (uma com um pedaço
privado), Juntar, conferir no servidor; uma mensagem "pelo celular" no
servidor, Juntar de novo, conferir no PC; e Juntar uma terceira vez (nada novo).

Rodar da raiz do app, com os dois no ar:
    $env:SOLIS_TOKEN_TESTE = '...'; backend/.venv/Scripts/python design/nuvem/testar_juntar.py
"""
import json
import os
import time

import httpx

PC = 'http://127.0.0.1:8767'
SERVIDOR = 'http://127.0.0.1:8766'
TOKEN = os.environ['SOLIS_TOKEN_TESTE']
NO_SERVIDOR = {'Authorization': f'Bearer {TOKEN}'}


def mandar(base, texto, cabecalhos=None, **extra):
    c = httpx.Client(timeout=60, headers=cabecalhos or {})
    conversa = extra.pop('conversa', None) or c.post(f'{base}/conversas').json()['id']
    r = c.post(f'{base}/conversas/{conversa}/mensagens', json={'texto': texto, **extra})
    eventos = [json.loads(l) for l in r.text.splitlines() if l]
    return conversa, ''.join(e.get('texto', '') for e in eventos)


def textos(base, conversa, cabecalhos=None):
    return [m['texto'] for m in httpx.get(f'{base}/conversas/{conversa}', headers=cabecalhos or {}).json()['mensagens']]


# 1. No PC: duas conversas, uma com um pedaço privado (o cadeado).
cv1, r1 = mandar(PC, 'Que horas são?')
cv2, r2 = mandar(PC, 'Me lembra de comprar pão amanhã às 9h')
mandar(PC, 'Que dia é hoje?', privada=True, conversa=cv2)
print('PC:', textos(PC, cv1), '|', textos(PC, cv2))

# 2. O PC guarda o servidor e junta.
httpx.put(f'{PC}/servidor', json={'endereco': SERVIDOR, 'token': TOKEN})
t = time.perf_counter()
feito = httpx.post(f'{PC}/servidor/juntar', timeout=60).json()
print(f'juntar 1 ({time.perf_counter() - t:.2f} s): trazido {feito["trazidos"]} · levado {feito["levados"]}')

# 3. No servidor: as conversas chegaram, sem o privado; a tarefa também.
lista = httpx.get(f'{SERVIDOR}/conversas', headers=NO_SERVIDOR).json()['conversas']
no_servidor = {c['id']: textos(SERVIDOR, c['id'], NO_SERVIDOR) for c in lista}
print('servidor:', no_servidor)
tudo = json.dumps(no_servidor, ensure_ascii=False)
assert 'Que horas são?' in tudo and 'Me lembra de comprar pão' in tudo
assert 'Que dia é hoje?' not in tudo, 'o privado viajou!'
tarefas = [t['texto'] for t in httpx.get(f'{SERVIDOR}/tarefas', headers=NO_SERVIDOR).json()['tarefas']]
print('tarefas no servidor:', tarefas)

# 4. "Pelo celular": uma mensagem nova no servidor, numa das conversas que vieram.
cv_srv = next(i for i, ms in no_servidor.items() if 'Que horas são?' in ms)
mandar(SERVIDOR, 'Quanto é 7 vezes 8?', NO_SERVIDOR, conversa=cv_srv)
feito = httpx.post(f'{PC}/servidor/juntar', timeout=60).json()
print(f'juntar 2: trazido {feito["trazidos"]} · levado {feito["levados"]}')
print('PC depois:', textos(PC, cv1))
assert 'Quanto é 7 vezes 8?' in textos(PC, cv1), 'o que foi dito no celular não chegou no PC'

# 5. De novo: nada novo, nos dois sentidos.
feito = httpx.post(f'{PC}/servidor/juntar', timeout=60).json()
print(f'juntar 3: trazido {feito["trazidos"]} · levado {feito["levados"]}')
assert not any(feito['trazidos'].values()) and not any(feito['levados'].values())
print('ok: juntou nos dois sentidos, sem o privado e sem duplicar')
