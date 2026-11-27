"""Juntar o PC e o servidor (26/11/2026): o que um Solis sabe, o outro passa a saber.

O cérebro na nuvem começa vazio. Aqui o PC leva pro servidor as conversas, as
mensagens, as memórias, as tarefas e os compromissos — e traz de lá o que foi
dito e aprendido pelo celular. É uma cópia nos dois sentidos, que pode rodar
quantas vezes for: cada linha que viaja ganha uma identidade (uid, a tabela
`juntados`) e ninguém recebe duas vezes a mesma coisa.

O que NÃO viaja, e por quê:
- o privado (mensagem, memória, tarefa, compromisso, título selado): a regra do
  Matheus, "o que é privado não vai pra nuvem" — fica só onde nasceu;
- as finanças e o Conhecimento: decisão dele, ainda em aberto (IDEIAS.md);
- as conversas importadas (ChatGPT): o arquivo inteiro do passado fica no PC; as
  memórias que vieram dele viajam;
- os resumos e as etapas de cada resposta: são refeitos de cada lado.

O que acompanha a cópia:
- memória que substituiu outra leva junto quais ela substituiu: o "trabalha na
  X" velho para de valer do outro lado também;
- tarefa feita de um lado fica feita do outro.

Limites, ditos: apagar não viaja (a identidade fica como lápide: o que foi
apagado aqui não volta de lá, mas também não some de lá); mensagens de uma mesma
conversa escritas ao mesmo tempo nos dois lados ficam na ordem em que chegaram.
"""
import logging
import uuid

from . import banco, cofre

log = logging.getLogger('solis.juntar')

VERSAO = 1


# — As identidades ————————————————————————————————————————————————————————————

def _uid_local(c, tabela: str, local: int, criada: str) -> str:
    """A identidade da linha daqui: a que já tinha, ou uma nova. Se o id foi
    reusado (a linha velha apagada, outra no lugar), a `criada` não bate: nova."""
    l = c.execute('SELECT uid, criada FROM juntados WHERE tabela = ? AND local = ?', (tabela, local)).fetchone()
    if l and l['criada'] == criada:
        return l['uid']
    uid = uuid.uuid4().hex
    c.execute('INSERT OR REPLACE INTO juntados (tabela, local, uid, criada) VALUES (?, ?, ?, ?)',
              (tabela, local, uid, criada))
    return uid


def _local_de(c, tabela: str, uid: str | None) -> int | None:
    if not uid:
        return None
    l = c.execute('SELECT local FROM juntados WHERE tabela = ? AND uid = ?', (tabela, uid)).fetchone()
    return l['local'] if l else None


def _conhecida(c, uid: str) -> bool:
    return c.execute('SELECT 1 FROM juntados WHERE uid = ?', (uid,)).fetchone() is not None


def _marcar(c, tabela: str, local: int, uid: str, criada: str) -> None:
    c.execute('INSERT OR REPLACE INTO juntados (tabela, local, uid, criada) VALUES (?, ?, ?, ?)',
              (tabela, local, uid, criada))


# — Exportar —————————————————————————————————————————————————————————————————

def exportar() -> dict:
    """Tudo o que pode viajar daqui, com as identidades."""
    with banco._con() as c:
        conversas, mensagens = [], []
        for cv in c.execute("SELECT id, criada, titulo, personalidade FROM conversas WHERE origem = 'solis' ORDER BY id").fetchall():
            msgs = c.execute(
                'SELECT id, papel, texto, criada, cerebro, personalidade FROM mensagens '
                'WHERE conversa = ? AND privada = 0 ORDER BY id', (cv['id'],)).fetchall()
            msgs = [m for m in msgs if not cofre.selado(m['texto'])]
            if not msgs:
                continue  # vazia, ou só com o privado
            cuid = _uid_local(c, 'conversas', cv['id'], cv['criada'])
            conversas.append({'uid': cuid, 'criada': cv['criada'], 'personalidade': cv['personalidade'],
                              'titulo': None if cofre.selado(cv['titulo']) else cv['titulo']})
            for m in msgs:
                mensagens.append({'uid': _uid_local(c, 'mensagens', m['id'], m['criada']), 'conversa': cuid,
                                  'papel': m['papel'], 'texto': m['texto'], 'criada': m['criada'],
                                  'cerebro': m['cerebro'], 'personalidade': m['personalidade']})

        memorias = []
        for m in c.execute('SELECT id, texto, tema, pedido, conversa, criada, area FROM memorias '
                           'WHERE privada = 0 AND substituida_por IS NULL ORDER BY id').fetchall():
            if cofre.selado(m['texto']):
                continue
            substituiu = [_uid_local(c, 'memorias', v['id'], v['criada']) for v in c.execute(
                'SELECT id, criada FROM memorias WHERE substituida_por = ?', (m['id'],)).fetchall()]
            cv = c.execute('SELECT criada FROM conversas WHERE id = ?', (m['conversa'],)).fetchone() if m['conversa'] else None
            memorias.append({'uid': _uid_local(c, 'memorias', m['id'], m['criada']), 'texto': m['texto'],
                             'tema': m['tema'], 'pedido': bool(m['pedido']), 'criada': m['criada'], 'area': m['area'],
                             'conversa': _uid_local(c, 'conversas', m['conversa'], cv['criada']) if cv else None,
                             'substituiu': substituiu})

        tarefas = [{'uid': _uid_local(c, 'tarefas', t['id'], t['criada']), 'texto': t['texto'], 'prazo': t['prazo'],
                    'hora': t['hora'], 'criada': t['criada'], 'feita': t['feita']}
                   for t in c.execute('SELECT id, texto, prazo, hora, criada, feita FROM tarefas WHERE privada = 0 ORDER BY id').fetchall()]
        compromissos = [{'uid': _uid_local(c, 'compromissos', a['id'], a['criado']), 'titulo': a['titulo'],
                         'dia': a['dia'], 'hora': a['hora'], 'duracao': a['duracao'], 'onde': a['onde'], 'criado': a['criado']}
                        for a in c.execute('SELECT id, titulo, dia, hora, duracao, onde, criado FROM compromissos '
                                           'WHERE privado = 0 ORDER BY id').fetchall()]
    return {'versao': VERSAO, 'conversas': conversas, 'mensagens': mensagens, 'memorias': memorias,
            'tarefas': tarefas, 'compromissos': compromissos}


# — Importar —————————————————————————————————————————————————————————————————

class PacoteInvalido(ValueError):
    pass


def importar(pacote: dict) -> dict:
    """Guarda o que ainda não existe aqui; devolve quantos de cada entraram (e
    quantas tarefas foram marcadas feitas). Rodar de novo não muda nada."""
    if not isinstance(pacote, dict) or pacote.get('versao') != VERSAO:
        raise PacoteInvalido(f'pacote de outra versão ({pacote.get("versao") if isinstance(pacote, dict) else "?"}); atualize os dois lados')
    novos = {'conversas': 0, 'mensagens': 0, 'memorias': 0, 'tarefas': 0, 'compromissos': 0, 'feitas': 0}
    with banco._con() as c:
        for cv in pacote.get('conversas', []):
            local = _local_de(c, 'conversas', cv['uid'])
            if local is None and not _conhecida(c, cv['uid']):
                local = c.execute('INSERT INTO conversas (criada, origem, titulo, personalidade) VALUES (?, ?, ?, ?)',
                                  (cv['criada'], 'solis', cv.get('titulo'), cv.get('personalidade'))).lastrowid
                _marcar(c, 'conversas', local, cv['uid'], cv['criada'])
                novos['conversas'] += 1
            elif local is not None and cv.get('titulo'):
                # O título que o outro lado deu (e este ainda não tinha).
                c.execute('UPDATE conversas SET titulo = ? WHERE id = ? AND titulo IS NULL', (cv['titulo'], local))

        for m in pacote.get('mensagens', []):
            if _conhecida(c, m['uid']):
                continue
            conversa = _local_de(c, 'conversas', m['conversa'])
            if conversa is None or not banco_existe(c, conversa):
                continue  # a conversa daqui foi apagada: a mensagem não volta sozinha
            if m['papel'] not in ('pessoa', 'solis'):
                continue
            local = c.execute('INSERT INTO mensagens (conversa, papel, texto, criada, cerebro, personalidade) '
                              'VALUES (?, ?, ?, ?, ?, ?)',
                              (conversa, m['papel'], m['texto'], m['criada'], m.get('cerebro'), m.get('personalidade'))).lastrowid
            _marcar(c, 'mensagens', local, m['uid'], m['criada'])
            novos['mensagens'] += 1

        for m in pacote.get('memorias', []):
            if _conhecida(c, m['uid']):
                continue
            conversa = _local_de(c, 'conversas', m.get('conversa'))
            local = c.execute('INSERT INTO memorias (texto, tema, pedido, privada, conversa, criada, area) '
                              'VALUES (?, ?, ?, 0, ?, ?, ?)',
                              (m['texto'], m['tema'], int(bool(m.get('pedido'))),
                               conversa if conversa and banco_existe(c, conversa) else None,
                               m['criada'], m.get('area'))).lastrowid
            _marcar(c, 'memorias', local, m['uid'], m['criada'])
            novos['memorias'] += 1
            # A que ela substituiu do outro lado, se está aqui, para de valer aqui também.
            for velha in m.get('substituiu', []):
                v = _local_de(c, 'memorias', velha)
                if v is not None:
                    c.execute('UPDATE memorias SET substituida_por = ? WHERE id = ? AND substituida_por IS NULL', (local, v))

        for t in pacote.get('tarefas', []):
            local = _local_de(c, 'tarefas', t['uid'])
            if local is None and not _conhecida(c, t['uid']):
                local = c.execute('INSERT INTO tarefas (texto, prazo, hora, privada, criada, feita) VALUES (?, ?, ?, 0, ?, ?)',
                                  (t['texto'], t.get('prazo'), t.get('hora'), t['criada'], t.get('feita'))).lastrowid
                _marcar(c, 'tarefas', local, t['uid'], t['criada'])
                novos['tarefas'] += 1
            elif local is not None and t.get('feita'):
                # Feita lá, feita aqui (o contrário não: desfazer não viaja).
                novos['feitas'] += c.execute('UPDATE tarefas SET feita = ? WHERE id = ? AND feita IS NULL',
                                             (t['feita'], local)).rowcount

        for a in pacote.get('compromissos', []):
            if _conhecida(c, a['uid']):
                continue
            local = c.execute('INSERT INTO compromissos (titulo, dia, hora, duracao, onde, privado, criado) '
                              'VALUES (?, ?, ?, ?, ?, 0, ?)',
                              (a['titulo'], a['dia'], a.get('hora'), a.get('duracao'), a.get('onde'), a['criado'])).lastrowid
            _marcar(c, 'compromissos', local, a['uid'], a['criado'])
            novos['compromissos'] += 1
    if any(novos.values()):
        log.info('juntar: entraram %s', novos)
    return novos


def banco_existe(c, conversa: int) -> bool:
    return c.execute('SELECT 1 FROM conversas WHERE id = ?', (conversa,)).fetchone() is not None


# — O PC e o servidor ——————————————————————————————————————————————————————————
# O PC guarda o endereço e a senha do servidor (a senha selada no cofre) e faz a
# viagem: traz de lá e leva daqui. O servidor só responde GET/POST /juntar, com a
# senha (nuvem.Porteiro).

import datetime as _dt  # noqa: E402

import httpx  # noqa: E402

PRAZO = httpx.Timeout(60.0, connect=10.0)
_transporte: httpx.AsyncBaseTransport | None = None  # os testes trocam


class NaoJuntou(Exception):
    """Em palavras, pra tela: o servidor não respondeu, a senha não é essa..."""


def servidor() -> dict:
    """O que a tela pode ver: o endereço, se há senha, e a última viagem."""
    s = banco.ajuste('servidor') or {}
    return {'endereco': s.get('endereco') or '', 'tem_senha': bool(s.get('token')),
            'ultima': banco.ajuste('servidor_ultima')}


def guardar_servidor(endereco: str, token: str | None) -> dict:
    endereco = endereco.strip().rstrip('/')
    if endereco and not endereco.startswith(('https://', 'http://')):
        endereco = 'https://' + endereco
    atual = banco.ajuste('servidor') or {}
    banco.guardar_ajuste('servidor', {
        'endereco': endereco,
        # Senha vazia mantém a que estava (a tela nunca recebe a senha de volta).
        'token': cofre.selar(token.strip()) if token and token.strip() else atual.get('token'),
    })
    return servidor()


async def juntar_com_servidor() -> dict:
    """Traz do servidor e leva pra ele. {trazidos, levados, quando}."""
    s = banco.ajuste('servidor') or {}
    endereco, token = s.get('endereco'), cofre.abrir(s.get('token'))
    if not endereco or not token or token == cofre.ILEGIVEL:
        raise NaoJuntou('Falta o endereço ou a senha do servidor.')
    cabecalho = {'Authorization': f'Bearer {token}'}
    try:
        async with httpx.AsyncClient(timeout=PRAZO, transport=_transporte, follow_redirects=False) as cliente:
            r = await cliente.get(f'{endereco}/juntar', headers=cabecalho)
            if r.status_code == 401:
                raise NaoJuntou('O servidor não aceitou a senha.')
            if r.status_code != 200:
                raise NaoJuntou(f'O servidor respondeu {r.status_code} (ele está atualizado?).')
            trazidos = importar(r.json())
            r = await cliente.post(f'{endereco}/juntar', headers=cabecalho, json=exportar())
            if r.status_code != 200:
                raise NaoJuntou(f'O servidor não guardou ({r.status_code}): {r.text[:200]}')
            levados = r.json()
    except httpx.HTTPError as e:
        raise NaoJuntou(f'Não consegui falar com o servidor ({type(e).__name__}).') from e
    except PacoteInvalido as e:
        raise NaoJuntou(str(e)) from e
    ultima = {'quando': _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds'),
              'trazidos': trazidos, 'levados': levados}
    banco.guardar_ajuste('servidor_ultima', ultima)
    return ultima
