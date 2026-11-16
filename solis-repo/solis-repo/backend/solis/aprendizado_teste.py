"""O teste do aprendizado: casos fixos, inventados (nada do Matheus), passados
pela extração (memoria.extrair) SEM guardar nada, cada um com o que devia sair.
Serve pra escolher medindo quem aprende (o modelo local, a Groq) e com qual
modelo — o princípio 4 do IDEIAS.md: função com taxa de acerto, medida.

Um caso passa quando sai o que devia (memória, tarefa ou compromisso com as
palavras esperadas, a substituição certa) e nada do que não devia."""
import asyncio
import datetime as dt
import time
import unicodedata

from . import memoria

# Uma segunda-feira, às 10h: as datas dos casos saem daqui.
AGORA = dt.datetime(2026, 11, 16, 10, 0)

# (mensagem, memórias já guardadas, o que espera)
# espera: 'memoria' (palavras que a memória nova tem), 'substitui' (o id),
# 'tarefa' (palavras), 'compromisso' (palavras, dia, hora), 'nada' (nada sai),
# 'privada' (a memória sai marcada privada).
CASOS = [
    ('Eu trabalho como engenheiro numa empresa de energia.', [], {'memoria': ['engenheir']}),
    ('Que horas são?', [], {'nada': True}),
    ('Grava aí: minha cor preferida é verde.', [], {'memoria': ['verde']}),
    ('Me mudei pra Curitiba semana passada.', [{'id': 7, 'texto': 'Mora em Campinas.', 'privada': False}],
     {'memoria': ['curitiba'], 'substitui': 7}),
    ('Prefiro café sem açúcar.', [], {'memoria': ['cafe']}),
    ('Amanhã às 15h tenho dentista.', [], {'compromisso': (['dentista'], '2026-11-17', '15:00')}),
    ('Preciso comprar pão.', [], {'tarefa': ['pao']}),
    ('Qual a capital da França?', [], {'nada': True}),
    ('Meu filho se chama Pedro e tem seis anos.', [], {'memoria': ['pedro']}),
    ('Não gosto de reunião de manhã cedo.', [], {'memoria': ['reuni']}),
    ('Obrigado, era isso.', [], {'nada': True}),
    ('Tenho diabetes tipo 2, descobri mês passado.', [], {'memoria': ['diabetes'], 'privada': True}),
    ('Mudei de emprego, agora trabalho numa startup de logística.',
     [{'id': 3, 'texto': 'Trabalha como analista num banco.', 'privada': False}],
     {'memoria': ['logistica'], 'substitui': 3}),
    ('Sexta às 9h tenho reunião com o cliente pelo Teams.', [],
     {'compromisso': (['reuni', 'cliente'], '2026-11-20', '09:00')}),
]


def _sem_acento(t: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', t.lower()) if unicodedata.category(c) != 'Mn')


def _tem(texto: str, palavras: list[str]) -> bool:
    t = _sem_acento(texto)
    return all(_sem_acento(p) in t for p in palavras)


def pontuar(espera: dict, resposta: dict) -> tuple[bool, str]:
    """(passou, por quê)."""
    memorias = [m for m in resposta.get('memorias', []) if (m.get('texto') or '').strip()]
    tarefas = [t for t in resposta.get('tarefas', []) if (t.get('texto') or '').strip()]
    compromissos = [c for c in resposta.get('compromissos', []) if (c.get('titulo') or '').strip()]
    if espera.get('nada'):
        if memorias or tarefas or compromissos:
            return False, 'devia sair nada'
        return True, ''
    if 'memoria' in espera:
        achada = next((m for m in memorias if _tem(m['texto'], espera['memoria'])), None)
        if not achada:
            return False, f'sem a memória {espera["memoria"]}'
        if 'substitui' in espera and achada.get('substitui') != espera['substitui']:
            return False, f'não substituiu a {espera["substitui"]} (veio {achada.get("substitui")})'
        if espera.get('privada') and not achada.get('privada'):
            return False, 'devia ser privada'
    if 'tarefa' in espera and not any(_tem(t['texto'], espera['tarefa']) for t in tarefas):
        return False, f'sem a tarefa {espera["tarefa"]}'
    if 'compromisso' in espera:
        palavras, dia, hora = espera['compromisso']
        c = next((c for c in compromissos if _tem(c['titulo'], palavras)), None)
        if not c:
            return False, f'sem o compromisso {palavras}'
        if c.get('dia') != dia or (c.get('hora') or '')[:5] != hora:
            return False, f'compromisso em {c.get("dia")} {c.get("hora")}, devia {dia} {hora}'
        if any(_tem(t['texto'], palavras) for t in tarefas):
            return False, 'o compromisso saiu também como tarefa'
    return True, ''


async def medir(onde: str, modelo: str, pausa: float = 0.0) -> dict:
    """Todos os casos, um de cada vez. Nada é guardado."""
    resultado = []
    t0 = time.perf_counter()
    for mensagem, candidatas, espera in CASOS:
        t = time.perf_counter()
        try:
            resposta = await memoria.extrair(onde, modelo, mensagem, candidatas, [], AGORA,
                                             pedido=memoria.eh_pedido(mensagem))
            ok, motivo = pontuar(espera, resposta)
        except Exception as e:  # noqa: BLE001 — o caso falha, o teste segue
            resposta, ok, motivo = {}, False, f'{type(e).__name__}: {e}'[:200]
        resultado.append({'mensagem': mensagem, 'passou': ok, 'motivo': motivo,
                          'segundos': round(time.perf_counter() - t, 2), 'resposta': resposta})
        await asyncio.sleep(pausa)
    certos = sum(r['passou'] for r in resultado)
    tempos = sorted(r['segundos'] for r in resultado)
    return {
        'resumo': {'onde': onde, 'modelo': modelo, 'casos': len(CASOS), 'certos': certos,
                   'mediana_s': tempos[len(tempos) // 2], 'total_s': round(time.perf_counter() - t0, 1)},
        'casos': resultado,
    }
