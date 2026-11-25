"""As finanças do Assessor (22/11/2026): "gastei 50 no mercado" vira um lançamento.

A frente da ordem (docs/progresso.html): "gastei 50 no mercado", por voz ou
WhatsApp, vira o lançamento certo 19 de 20 vezes, e o resumo do mês bate com a
conta. O problema é real (o Meu Assessor, pelo WhatsApp, tem 300 mil usuários —
IDEIAS.md) e o Claude Code não faz.

- Os valores falados viram centavos (`valor_de`): "50", "12,90", "R$ 1.234,56",
  "2 mil", "cento e vinte", "mil e duzentos", "50 conto".
- As categorias são fixas (`categoria_de`): o resumo do mês agrupa igual, não
  importa qual cérebro anotou nem como ele chamou a categoria.
- `interpretar` lê a frase sem IA nenhuma (no PC, na hora): o caminho que
  não manda o dinheiro dele pra nuvem, se ele quiser assim.
- As ferramentas do Solis (corpo.py: lancar, gastos, apagar_lancamento) valem
  pra todos os cérebros. O banco guarda a descrição selada (banco.lancamentos).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from . import banco

# — os valores ————————————————————————————————————————————————————————————————

_UNIDADES = {'zero': 0, 'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'tres': 3, 'quatro': 4, 'cinco': 5, 'seis': 6,
             'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10, 'onze': 11, 'doze': 12, 'treze': 13, 'catorze': 14,
             'quatorze': 14, 'quinze': 15, 'dezesseis': 16, 'dezessete': 17, 'dezoito': 18, 'dezenove': 19,
             'vinte': 20, 'trinta': 30, 'quarenta': 40, 'cinquenta': 50, 'sessenta': 60, 'setenta': 70,
             'oitenta': 80, 'noventa': 90, 'cem': 100, 'cento': 100, 'duzentos': 200, 'duzentas': 200,
             'trezentos': 300, 'trezentas': 300, 'quatrocentos': 400, 'quinhentos': 500, 'seiscentos': 600,
             'setecentos': 700, 'oitocentos': 800, 'novecentos': 900}
_NUMERO_FALADO = r'(?:' + '|'.join(sorted(_UNIDADES, key=len, reverse=True)) + r'|mil|e)'


def _simples(t: str) -> str:
    return unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode().lower()


def _palavras_em_numero(palavras: list[str]) -> int | None:
    total, atual, achou = 0, 0, False
    for p in palavras:
        if p == 'e':
            continue
        if p == 'mil':
            total += (atual or 1) * 1000
            atual, achou = 0, True
        elif p in _UNIDADES:
            atual += _UNIDADES[p]
            achou = True
        else:
            return None
    return total + atual if achou else None


# "R$ 1.234,56", "1234,5", "12.90" (ponto com 2 casas é decimal), "2 mil", "2,5 mil", "50 conto".
_DIGITOS = re.compile(r'(?:r\$\s*)?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(mil\b)?(?:\s*e\s*(\d+))?')


def valor_de(texto: str) -> int | None:
    """Os centavos do primeiro valor no texto, ou None."""
    t = _simples(str(texto or '')).strip()
    m = _DIGITOS.search(t)
    if m:
        bruto, mil, resto = m.group(1), m.group(2), m.group(3)
        if re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?', bruto):
            bruto = bruto.replace('.', '')
        bruto = bruto.replace(',', '.')
        reais = float(bruto) * (1000 if mil else 1) + (int(resto) if (mil and resto) else 0)
        centavos = round(reais * 100)
        # "18 e 50" falado é R$ 18,50 (os centavos depois do "e"); "2 mil e 500" é 2.500.
        if resto and not mil and len(resto) <= 2 and '.' not in bruto:
            centavos += int(resto.ljust(2, '0')) if len(resto) == 1 else int(resto)
        cents = re.search(r'(\d{1,2})\s*centavos', t[m.end():])
        if cents and not mil:
            centavos += int(cents.group(1))
        return centavos if centavos > 0 else None
    # Por extenso: "cento e vinte", "mil e duzentos", "vinte e cinco reais e cinquenta centavos".
    falado = re.findall(rf'\b{_NUMERO_FALADO}\b', t)
    if not falado:
        return None
    partes = re.split(r'\breais?\b', t, maxsplit=1)
    reais = _palavras_em_numero(re.findall(rf'\b{_NUMERO_FALADO}\b', partes[0]))
    if reais is None:
        return None
    centavos = reais * 100
    if len(partes) > 1 and 'centavo' in partes[1]:
        c = _palavras_em_numero(re.findall(rf'\b{_NUMERO_FALADO}\b', partes[1].split('centavo')[0]))
        centavos += c or 0
    return centavos if centavos > 0 else None


def reais(centavos: int) -> str:
    return 'R$ ' + f'{centavos / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


# — as categorias ———————————————————————————————————————————————————————————————

GASTOS = {
    'mercado': r'mercado|supermercado|feira|sacolao|hortifruti|acougue|atacad|compras do mes',
    'alimentação': r'almoc|almoco|jant|lanche|restaurante|ifood|pizza|hamburguer|cafe|padaria|marmita|sorvete|'
                   r'\bbar\b|cerveja|delivery|comida|acai|pastel|salgado',
    'transporte': r'\buber\b|\b99\b|taxi|gasolina|combustivel|abasteci|onibus|metro|passagem|estacionamento|pedagio|'
                  r'oficina|mecanico|carro|moto',
    'contas da casa': r'\bluz\b|energia|\bagua\b|internet|aluguel|condominio|\bgas\b|telefone|conta de|iptu|'
                      r'plano do celular|net\b',
    'saúde': r'farmacia|remedio|medic|consulta|exame|dentista|hospital|psicolog|terapia|plano de saude',
    'lazer': r'cinema|show|jogo|steam|netflix|spotify|assinatura|viagem|passeio|ingresso|festa|balada|playstation',
    'compras': r'roupa|tenis|sapato|loja|presente|eletronic|shopping|camisa|calca|mercado livre|amazon|shopee',
    'educação': r'curso|livro|faculdade|escola|mensalidade|material escolar|udemy',
    'academia': r'academia|personal|suplement|whey',
}
ENTRADAS = {
    'salário': r'salario|pagamento do trabalho|holerite',
    'freela': r'freela|servico|cliente|projeto|trabalho extra|job',
    'venda': r'vend',
    'reembolso': r'reembols|devolu|estorno',
}
CATEGORIAS = list(GASTOS) + ['outros']
CATEGORIAS_ENTRADA = list(ENTRADAS) + ['outras entradas']


def categoria_de(descricao: str, tipo: str = 'gasto', sugerida: str = '') -> str:
    """A categoria fixa: pelas palavras da descrição primeiro (a mesma, não importa
    o cérebro: medido em 22/11/2026, a Groq e o Gemini puseram o livro em
    "compras"); senão a sugerida, se é uma das fixas; senão pelas palavras dela."""
    fixas = CATEGORIAS_ENTRADA if tipo == 'entrada' else CATEGORIAS
    regras = (ENTRADAS if tipo == 'entrada' else GASTOS).items()
    for c, padrao in regras:
        if re.search(padrao, _simples(descricao or '')):
            return c
    s = _simples(sugerida or '').strip()
    for c in fixas:
        if s and s == _simples(c):
            return c
    for c, padrao in regras:
        if re.search(padrao, s):
            return c
    return fixas[-1]


# — a frase, sem IA ———————————————————————————————————————————————————————————————

_ENTRADA = re.compile(r'\b(recebi|ganhei|entrou|entraram|caiu|cairam|me pagaram|vendi|faturei)\b')
# Sem "foi", "saiu": "o jogo foi 2 a 1", "o resultado saiu 3 a 0" não são gasto.
_GASTO = re.compile(r'\b(gastei|paguei|comprei|torrei|deixei|custou|almocei|jantei|abasteci|lanchei|dei)\b')
_PERGUNTA = re.compile(r'^(quanto|qual|quais|como|quando|onde|por ?que|quem|o que|sera|sabe|me (diz|fala))\b')
_FORMA = re.compile(r'\b(no |pelo |via |com )?(pix|cartao de credito|cartao de debito|cartao|credito|debito|dinheiro|'
                    r'boleto)\b')
_VERBO_VIRA = {'almocei': 'almoço', 'jantei': 'jantar', 'abasteci': 'combustível', 'lanchei': 'lanche'}
_VAZIAS = {'eu', 'que', 'no', 'na', 'nos', 'nas', 'de', 'do', 'da', 'dos', 'das', 'em', 'com', 'pro', 'pra', 'para',
           'o', 'a', 'os', 'as', 'um', 'uma', 'por', 'reais', 'real', 'conto', 'contos', 'pila', 'hoje', 'ontem',
           'anteontem', 'solis', 'anota', 'anotar', 'lanca', 'lancar', 'registra', 'ai', 'agora', 'mais', 'centavos',
           'r$', 'e', 'foi', 'foram', 'me', 'meu', 'minha'}


def _dia_de(t: str, hoje: date) -> date:
    if 'anteontem' in t:
        return hoje - timedelta(days=2)
    if 'ontem' in t:
        return hoje - timedelta(days=1)
    m = re.search(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b', t)
    if m:
        ano = int(m.group(3)) + (2000 if m.group(3) and len(m.group(3)) == 2 else 0) if m.group(3) else hoje.year
        try:
            d = date(ano, int(m.group(2)), int(m.group(1)))
            return d if m.group(3) or d <= hoje else d.replace(year=hoje.year - 1)
        except ValueError:
            pass
    return hoje


def dia_de(texto: str, hoje: date | None = None) -> date:
    """O dia do lançamento: hoje, ontem, anteontem, 15/11, 2026-11-15."""
    hoje = hoje or date.today()
    t = _simples(texto or '')
    m = re.fullmatch(r'\s*(\d{4})-(\d{2})-(\d{2})\s*', t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return _dia_de(t, hoje)


def parece_lancamento(frase: str) -> bool:
    """É um lançamento pra anotar na hora (o pedido rápido), e não uma pergunta,
    um lembrete ("me lembra de pagar a luz") ou um plano ("vou pagar")?"""
    t = _simples(frase or '').strip().rstrip('.!')
    t = re.sub(r'^(solis|e?i solis|ei|oi)[,!.\s]+', '', t)
    t = re.sub(r'^(anota|anote|lanca|lance|registra|registre)( ai)?( que)?\s+', '', t)
    if not t or '?' in t or _PERGUNTA.match(t) or re.search(r'\blembr|\bvou\b|\bvamos\b|\bpreciso\b|\btenho que\b', t):
        return False
    # O ano não é valor ("em 2025 eu gastei muito").
    if valor_de(re.sub(r'\b(em|de|no ano de|desde)\s+(19|20)\d\d\b', ' ', t)) is None:
        return False
    if _GASTO.search(t) or _ENTRADA.search(t):
        return True
    # Sem o verbo, só bem curto, com o valor no fim e começando por um gasto
    # conhecido ("uber 18,50", "netflix 55,90"): "minha senha é 1234" não é.
    return (len(t.split()) <= 5 and bool(re.search(r'\d([.,]\d{1,2})?\s*(reais|conto)?$', t))
            and categoria_de(t.split()[0]) != 'outros')


def confirmacao(lancamento: dict, id_: int, hoje: date | None = None) -> str:
    """O que o Solis diz depois de anotar: o lançamento e como ficou o mês."""
    hoje = hoje or date.today()
    dia = date.fromisoformat(lancamento['dia'])
    mes = resumo(dia.replace(day=1), max(dia, hoje))
    tipo, categoria, descricao = lancamento['tipo'], lancamento['categoria'], lancamento['descricao']
    forma = lancamento.get('forma')
    quando = 'hoje' if dia == hoje else 'ontem' if dia == hoje - timedelta(days=1) else f'em {dia:%d/%m}'
    detalhe = f' ({descricao})' if _simples(descricao) not in _simples(categoria) else ''
    base = (f'Anotado: {"entrada" if tipo == "entrada" else "gasto"} de {reais(lancamento["centavos"])} em '
            f'{categoria}{detalhe}, {quando}{", no " + forma if forma else ""}. ')
    if tipo == 'gasto':
        base += f'No mês, {categoria} soma {reais(mes["por_categoria"].get(categoria, 0))} e os gastos, {reais(mes["gastos"])}.'
    else:
        base += f'No mês, as entradas somam {reais(mes["entradas"])} e os gastos, {reais(mes["gastos"])}.'
    return base + f' (lançamento nº {id_})'


def interpretar(frase: str, hoje: date | None = None) -> dict | None:
    """O lançamento de uma frase ("gastei 50 no mercado"), sem IA; None se não é um."""
    t = _simples(frase).strip().rstrip('.!?')
    centavos = valor_de(t)
    if centavos is None:
        return None
    entrada = bool(_ENTRADA.search(t))
    if not entrada and not _GASTO.search(t) and not re.search(r'\d|reais|conto', t):
        return None
    tipo = 'entrada' if entrada else 'gasto'
    forma = _FORMA.search(t)
    forma_txt = None
    if forma:
        f = forma.group(2)
        forma_txt = 'pix' if f == 'pix' else 'cartão de crédito' if 'credito' in f else \
            'cartão de débito' if 'debito' in f else 'cartão' if f == 'cartao' else f
    # A descrição: as palavras da frase (com os acentos dela) sem o verbo, o valor,
    # a forma, o dia e as vazias.
    verbo = (_ENTRADA.search(t) or _GASTO.search(t))
    fora = set(_VAZIAS) | set(_UNIDADES) | {'mil', 'dia', 'pix', 'cartao', 'credito', 'debito', 'dinheiro', 'boleto',
                                             'via', 'pelo'}
    if verbo:
        fora |= set(verbo.group(1).split())
    palavras = [p for p in re.findall(r'[^\W\d_]+', frase.lower()) if _simples(p) not in fora]
    descricao = ' '.join(palavras).strip()
    if not descricao and verbo and verbo.group(1) in _VERBO_VIRA:
        descricao = _VERBO_VIRA[verbo.group(1)]
    if not descricao:
        descricao = 'sem descrição'
    categoria = categoria_de(descricao, tipo)
    if categoria in ('outros', 'outras entradas'):
        categoria = categoria_de(t, tipo)  # "vendi meu monitor": o verbo diz a categoria
    return {'tipo': tipo, 'centavos': centavos, 'descricao': descricao, 'categoria': categoria,
            'forma': forma_txt, 'dia': dia_de(t, hoje).isoformat()}


# — o resumo ———————————————————————————————————————————————————————————————————

_MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro',
          'novembro', 'dezembro']


def periodo_de(texto: str, hoje: date | None = None) -> tuple[date, date, str]:
    """(de, até, nome) de "este mês", "mês passado", "hoje", "ontem", "semana", "novembro"."""
    hoje = hoje or date.today()
    t = _simples(texto or '')
    inicio_mes = hoje.replace(day=1)
    if 'passad' in t and 'mes' in t:
        fim = inicio_mes - timedelta(days=1)
        return fim.replace(day=1), fim, f'{_MESES[fim.month - 1]} de {fim.year}'
    if 'ontem' in t:
        d = hoje - timedelta(days=1)
        return d, d, 'ontem'
    if 'hoje' in t:
        return hoje, hoje, 'hoje'
    if 'semana' in t:
        return hoje - timedelta(days=hoje.weekday()), hoje, 'esta semana'
    for i, nome in enumerate(_MESES, 1):
        if _simples(nome) in t:
            ano = hoje.year if i <= hoje.month else hoje.year - 1
            fim = (date(ano + (i == 12), (i % 12) + 1, 1) - timedelta(days=1))
            return date(ano, i, 1), fim, f'{nome} de {ano}'
    return inicio_mes, hoje, f'{_MESES[hoje.month - 1]} até hoje'


def resumo(de: date, ate: date) -> dict:
    itens = banco.lancamentos(de.isoformat(), ate.isoformat())
    gastos = [i for i in itens if i['tipo'] == 'gasto']
    entradas = [i for i in itens if i['tipo'] == 'entrada']
    por_categoria: dict[str, int] = {}
    for g in gastos:
        por_categoria[g['categoria']] = por_categoria.get(g['categoria'], 0) + g['centavos']
    total_gastos = sum(g['centavos'] for g in gastos)
    total_entradas = sum(e['centavos'] for e in entradas)
    return {'de': de.isoformat(), 'ate': ate.isoformat(), 'lancamentos': len(itens),
            'gastos': total_gastos, 'entradas': total_entradas, 'saldo': total_entradas - total_gastos,
            'por_categoria': dict(sorted(por_categoria.items(), key=lambda kv: -kv[1])), 'itens': itens}


def resumo_em_texto(r: dict, nome: str) -> str:
    if not r['lancamentos']:
        return f'Nenhum lançamento em {nome}.'
    partes = [f'{nome}: gastos de {reais(r["gastos"])}' + (f', entradas de {reais(r["entradas"])}, saldo de '
                                                           f'{reais(r["saldo"])}' if r['entradas'] else '') + '.']
    if r['por_categoria']:
        partes.append('Por categoria: ' + '; '.join(f'{c} {reais(v)}' for c, v in r['por_categoria'].items()) + '.')
    ultimos = r['itens'][-5:]
    partes.append('Últimos: ' + '; '.join(
        f'#{i["id"]} {i["dia"][8:10]}/{i["dia"][5:7]} {"+" if i["tipo"] == "entrada" else "-"}{reais(i["centavos"])} '
        f'{i["descricao"]}' for i in ultimos) + '.')
    return ' '.join(partes)
