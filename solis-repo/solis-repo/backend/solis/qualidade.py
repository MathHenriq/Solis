"""A taxa de acerto por função (IDEIAS.md, princípios 3 e 4; decisões do
Matheus, 17/11/2026).

Duas medidas, porque são duas perguntas:
- **rodou** — o que o Solis sabe sozinho, do registro de uso (banco.usos): o
  cérebro respondeu ou falhou (caiu pro próximo, cortou no meio), a
  ferramenta deu certo ou erro. Diz se a peça funcionou, não se acertou.
- **acertou** — o voto do Matheus (👍/👎) embaixo da resposta. Só quem pediu
  sabe se o horário da reunião estava certo. Resposta sem voto não conta.

E os testes de qualidade com meta (9 em 10): a escuta (voz_teste.py) e o
aprendizado (aprendizado_teste.py). "Só existe o que funciona" mostra, não
desliga: cada função aparece como passou, não passou ou sem teste.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import banco

META = 0.9
FALHAS_MOSTRADAS = 3


def _grupo(funcao: str) -> tuple[str, str]:
    """(tipo, nome): 'cerebro:claude' → ('cerebro', 'claude'); as ferramentas de
    um servidor MCP (mcp__notion__search) contam juntas, pelo servidor."""
    tipo, _, nome = funcao.partition(':')
    if tipo == 'ferramenta' and nome.startswith('mcp__'):
        return 'mcp', nome.split('__')[1] or nome
    return tipo, nome


def _funcoes(usos: list[dict]) -> list[dict]:
    grupos: dict[tuple[str, str], dict] = {}
    for u in usos:
        tipo, nome = _grupo(u['funcao'])
        g = grupos.setdefault((tipo, nome), {'tipo': tipo, 'nome': nome, 'usos': 0, 'certos': 0,
                                              'bons': 0, 'ruins': 0, 'falhas': [], 'ultimo': None})
        g['usos'] += 1
        g['certos'] += u['ok']
        g['bons'] += u['voto'] == 1
        g['ruins'] += u['voto'] == -1
        g['ultimo'] = u['quando']
        if not u['ok']:
            g['falhas'].append({'quando': u['quando'], 'detalhe': u['detalhe']})
    saida = []
    for g in grupos.values():
        g['falhas'] = g['falhas'][-FALHAS_MOSTRADAS:][::-1]  # as mais novas primeiro
        saida.append(g)
    ordem = {'cerebro': 0, 'ferramenta': 1, 'mcp': 2}
    return sorted(saida, key=lambda g: (ordem.get(g['tipo'], 3), -g['usos'], g['nome'].lower()))


def _teste_escuta() -> dict | None:
    """A medida mais nova da escuta de hoje ('atual') numa gravação do Matheus."""
    from . import voz_teste
    for t in voz_teste.listar():  # do mais novo pro mais antigo
        m = t['medidas'].get('atual')
        if m and m.get('chamadas'):
            return {'id': 'escuta', 'certos': m['entendeu'], 'total': m['chamadas'], 'falsos': m['falsos'],
                    'passou': bool(m['passou']), 'quando': t['id']}
    return None


def guardar_teste_aprendizado(resumo: dict) -> None:
    """O teste do aprendizado não guardava nada: o último fica pra tela."""
    banco.guardar_ajuste('teste_aprendizado', {
        'certos': resumo['certos'], 'total': resumo['casos'], 'onde': resumo['onde'], 'modelo': resumo['modelo'],
        'passou': resumo['casos'] > 0 and resumo['certos'] / resumo['casos'] >= META,
        'quando': datetime.now(timezone.utc).isoformat(timespec='seconds')})


def _teste_aprendizado() -> dict | None:
    t = banco.ajuste('teste_aprendizado')
    return {'id': 'aprendizado', 'falsos': None, **t} if t else None


def relatorio(dias: int = 30) -> dict:
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec='seconds')
    return {
        'dias': dias,
        'meta': META,
        'funcoes': _funcoes(banco.usos(desde)),
        'testes': [t for t in (_teste_escuta(), _teste_aprendizado()) if t],
    }
