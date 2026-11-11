"""O básico, respondido em código: hora, data, lembrete, agenda e tarefas.

Pedido do Matheus depois do terceiro teste com a voz (11/11/2026): "colocar uma
coisa na agenda tem que ser extremamente rápido", e "que horas são" não pode
errar. O modelo errava o básico — copiava uma resposta antiga ("não vejo o
horário"), inventava a hora (10:48 com o relógio em 10:38) — e esperava a busca
na memória (1,7 a 4,7 s) que a pergunta nem precisa. Aqui não há modelo nem
busca: a resposta sai em milissegundos, do relógio e do banco, e não erra.

Só pedidos curtos e reconhecidos inteiros: "que horas são?" sim; "que horas são
boas pra marcar com a Paula?" não — essa é do modelo. O que não casa aqui segue
o caminho de sempre.
"""
import datetime as dt
import re
import unicodedata

from . import banco, memoria

DIAS = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro',
         'outubro', 'novembro', 'dezembro']

_DIA = r'(?:\s+(?:pra|para))?(?:\s+(hoje|amanha))?'
# "e horas sao": o Whisper às vezes come o "qu" do começo (medido, voz baixa).
HORA = re.compile(r'^(?:(?:que |e |q )?horas? (?:sao|e)(?: agora)?|me (?:diz|diga|fala|fale) (?:que horas sao|as horas|a hora)|horas)$')
DATA = re.compile(
    r'^(?:que dia (?:e|vai ser) (hoje|amanha)|(hoje|amanha) e que dia|qual (?:e )?(?:a )?data(?: de (hoje|amanha))?'
    r'|que dia da semana (?:e )?(hoje|amanha)|em que dia (?:estamos|a gente esta))$'
)
AGENDA = re.compile(
    r'^(?:o que (?:eu )?tenho(?: marcado| na (?:minha )?agenda)?|o que tem na (?:minha )?agenda|qual (?:e )?(?:a )?minha agenda'
    r'|tenho (?:algum )?(?:compromisso|coisa marcada|algo marcado))' + _DIA + r'$'
)
TAREFAS = re.compile(
    r'^(?:quais (?:sao )?(?:as )?minhas tarefas|o que (?:eu )?tenho (?:que|pra|para) fazer|minhas tarefas)' + _DIA + r'$'
)


def _limpo(texto: str) -> str:
    t = ''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if unicodedata.category(c) != 'Mn')
    t = re.sub(r'[^\w\s]', ' ', t)
    # Erros de ouvido do Whisper que não mudam o pedido (medidos em voz baixa):
    # "a manhã" no lugar de "amanhã", "ok" no lugar de "o que".
    t = re.sub(r'\ba manha\b', 'amanha', t)
    t = re.sub(r'^ok eu tenho\b', 'o que eu tenho', re.sub(r'\s+', ' ', t).strip())
    t = re.sub(r'\b(solis|por favor|ei|oi|ok)\b', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def _hora(h: str) -> str:
    """'10:38' → '10h38'; '15:00' → '15h' — como se fala."""
    hh, mm = h.split(':')
    return f'{int(hh)}h' + ('' if mm == '00' else mm)


def _quando(dia: str, hora: str | None, agora: dt.datetime) -> str:
    d = dt.date.fromisoformat(dia)
    hoje = agora.date()
    dias = (d - hoje).days
    curto = DIAS[d.weekday()].split('-')[0]
    nome = 'hoje' if dias == 0 else 'amanhã' if dias == 1 else curto if 1 < dias < 7 else f'dia {d.day}'
    return f'{nome} às {_hora(hora)}' if hora else nome


def _lista(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ', '.join(itens[:-1]) + ' e ' + itens[-1]


def responder(texto: str, agora: dt.datetime) -> dict | None:
    """{'tipo', 'texto', 'tarefa' (pra anotar, ou None), 'privada'} — ou None,
    e aí o pedido vai pro modelo."""
    limpo = _limpo(texto)
    if not limpo or len(limpo.split()) > 20:
        return None

    if HORA.match(limpo):
        return {'tipo': 'hora', 'texto': f'São {_hora(f"{agora:%H:%M}")}.', 'tarefa': None, 'privada': False}

    if m := DATA.match(limpo):
        amanha = 'amanha' in [g for g in m.groups() if g]
        d = agora.date() + dt.timedelta(days=1 if amanha else 0)
        quem = 'Amanhã' if amanha else 'Hoje'
        return {'tipo': 'data', 'texto': f'{quem} é {DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]}.',
                'tarefa': None, 'privada': False}

    if m := AGENDA.match(limpo):
        amanha = m.group(1) == 'amanha'
        d = (agora.date() + dt.timedelta(days=1 if amanha else 0)).isoformat()
        quem = 'amanhã' if amanha else 'hoje'
        itens = banco.compromissos(d, d, 20)
        if not itens:
            return {'tipo': 'agenda', 'texto': f'Nada na agenda {quem}.', 'tarefa': None, 'privada': False}
        partes = [f'{c["titulo"].lower() if c["titulo"][:1].isupper() and not c["titulo"][1:2].isupper() else c["titulo"]}'
                  + (f' às {_hora(c["hora"])}' if c.get('hora') else '')
                  + (f', na {c["onde"]}' if c.get('onde') else '') for c in itens]
        return {'tipo': 'agenda', 'texto': f'{quem.capitalize()} você tem {_lista(partes)}.', 'tarefa': None,
                'privada': any(c.get('privado') for c in itens)}

    if m := TAREFAS.match(limpo):
        dia = m.group(1)
        abertas = banco.tarefas_abertas(50)
        if dia:
            d = (agora.date() + dt.timedelta(days=1 if dia == 'amanha' else 0)).isoformat()
            # "pra hoje" inclui as atrasadas: são de hoje também.
            abertas = [t for t in abertas if t.get('prazo') and (t['prazo'] == d or (dia == 'hoje' and t['prazo'] < d))]
        quem = {'hoje': 'pra hoje', 'amanha': 'pra amanhã', None: ''}[dia]
        if not abertas:
            return {'tipo': 'tarefas', 'texto': f'Nenhuma tarefa {quem}.'.replace('  ', ' ').replace(' .', '.'),
                    'tarefa': None, 'privada': False}
        nomes = [t['texto'][0].lower() + t['texto'][1:] + (f' às {_hora(t["hora"])}' if t.get('hora') else '')
                 for t in abertas[:5]]
        mais = f' e mais {len(abertas) - 5}' if len(abertas) > 5 else ''
        cabeca = f'{len(abertas)} {"tarefa" if len(abertas) == 1 else "tarefas"} {quem}'.strip()
        return {'tipo': 'tarefas', 'texto': f'{cabeca.capitalize()}: {_lista(nomes)}{mais}.', 'tarefa': None,
                'privada': any(t.get('privada') for t in abertas[:5])}

    # Lembrete com hora: anotado aqui, antes de qualquer resposta.
    if not texto.rstrip().endswith('?') and (t := memoria.lembrete_rapido(texto, agora)):
        privada = memoria.eh_privado(texto) or bool(memoria.SENSIVEL.search(t['texto']))
        return {'tipo': 'lembrete', 'texto': f'Anotado: {t["texto"][0].lower() + t["texto"][1:]}. '
                f'Te aviso {_quando(t["prazo"], t["hora"], agora)}.', 'tarefa': t, 'privada': privada}
    return None
