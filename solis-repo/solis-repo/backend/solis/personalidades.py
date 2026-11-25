"""As personalidades (docs/IDEIAS.md → Personalidades, 25/11/2026): Jarvis, Eva,
Ed e o Assessor, cada um com nicho, jeito, voz e uma área própria na memória.
O Solis de sempre continua sendo quem responde o geral.

O "pronto quando" do painel: os quatro têm voz, jeito e memória próprios, e o
Matheus reconhece quem está falando sem olhar a tela.

Como funciona, igual pra qualquer cérebro (as funções são do Solis):
- quem responde é decidido em código, sem modelo (IDEIAS.md: "só acordam quando
  o assunto toca a área delas, decidido por regra"): quem ele chamar pelo nome
  ("Ed, monta um treino", "chama a Eva"), senão o dono do assunto ("gastei 50 no
  mercado" é do Assessor), senão quem já estava falando na conversa;
- o jeito vai como uma nota pro cérebro, como o estilo de resposta (estilos.py);
- a voz é escolhida pela personalidade em cada camada da fala (o Gemini, a
  reserva do Edge e a do PC), pra que ela continue reconhecível mesmo quando a
  voz principal acaba a cota do dia;
- a memória: todos leem tudo; o que é aprendido numa resposta fica na área de
  quem respondeu, e quem responde vê primeiro o que está na área dele.

Inspiração em profissões e estilos, nunca em pessoas reais (IDEIAS.md).
PROVISÓRIO: as vozes do Gemini são a proposta inicial, até o Matheus escolher
num teste cego (design/personalidades/).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from . import banco


@dataclass(frozen=True)
class Personalidade:
    id: str
    nome: str
    artigo: str          # 'o' ou 'a': "o Ed", "a Eva"
    nicho: str           # "treino, peso e alimentação"
    jeito: str           # vai pro cérebro (nota())
    gemini: str          # a voz do Gemini (Flash TTS e Live)
    edge: str            # a reserva grátis (Edge)
    kokoro: tuple[str, float]  # a voz do PC (offline e o privado) e a velocidade
    cor: str             # pra tela (a esfera da voz, na refação do visual)

    @property
    def chamado(self) -> str:
        return f'{self.artigo} {self.nome}'


SOLIS = Personalidade(
    'solis', 'Solis', 'o', 'o geral', '', 'Aoede', 'en-US-AvaMultilingualNeural', ('pf_dora', 1.0), '#F2A541')

TODAS: dict[str, Personalidade] = {p.id: p for p in [
    SOLIS,
    Personalidade(
        'jarvis', 'Jarvis', 'o', 'desenvolvimento e o lado técnico',
        'Um engenheiro de software sênior, calmo e preciso. Vai direto ao ponto técnico, usa o termo certo e '
        'traduz em palavras simples quando ajuda. Quando o Claude Code ou o Codex estão trabalhando, conta o que '
        'estão fazendo e por quê. Avisa antes do que pode dar errado (perder dados, segurança, custo). Tom sereno e '
        'levemente formal, sem bajular.',
        'Charon', 'en-US-AndrewMultilingualNeural', ('pm_alex', 1.0), '#5B8DEF'),
    Personalidade(
        'eva', 'Eva', 'a', 'carreira e trabalho',
        'Uma conselheira de carreira experiente, que escuta antes de aconselhar. Num desabafo, primeiro acolhe e '
        'entende, com uma pergunta de cada vez, sem pular pra solução nem mudar de assunto. Quando ele pede um '
        'plano, é franca e prática: passos concretos, prazo e o que medir. Fala com calor, sem frase feita de '
        'autoajuda.',
        'Sulafat', 'pt-BR-ThalitaMultilingualNeural', ('pf_dora', 0.92), '#C77DFF'),
    Personalidade(
        'ed', 'Ed', 'o', 'treino, peso e alimentação',
        'Um treinador experiente de musculação e condicionamento, com noção de nutrição esportiva. Direto, '
        'motivador, com energia, cobra constância sem ser grosseiro. Monta treino com exercício, séries, '
        'repetições e descanso; fala de alimentação em números (proteína, calorias). Saúde: aponta o que viu e '
        'sugere procurar um médico ou nutricionista; nunca receita remédio nem dá diagnóstico. Dor forte ou lesão: '
        'manda parar e procurar um profissional.',
        'Fenrir', 'pt-BR-AntonioNeural', ('pm_santa', 1.05), '#3DDC97'),
    Personalidade(
        'assessor', 'Assessor', 'o', 'rotina e finanças',
        'Um assessor executivo eficiente. Curto e organizado: confirma valores, datas e horas exatamente como '
        'ficaram. Cuida da agenda, dos lembretes, das tarefas e do dinheiro (gastos, entradas, o resumo do mês). '
        'Não recomenda investimento: organiza e mostra os números.',
        'Schedar', 'en-US-BrianMultilingualNeural', ('pm_alex', 1.12), '#F25F5C'),
]}


def de(id_: str | None) -> Personalidade:
    return TODAS.get(id_ or '', SOLIS)


# — Quem responde ——————————————————————————————————————————————————————————————————

def _simples(texto: str) -> str:
    t = ''.join(c for c in unicodedata.normalize('NFD', (texto or '').lower()) if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r'[^\w\s]', ' ', t).split())


# Os nomes como o Whisper escreve (medido no que ele costuma errar: "Jarbas",
# "Edi", "Acessor").
_NOMES = {
    'jarvis': r'jarvis|jarves|jarvas|jarbas|djarvis',
    'eva': r'eva|evinha',
    'ed': r'ed|edi|ede',
    'assessor': r'assessor|acessor|assesor',
    'solis': r'solis|soles|solys',
}
_QUALQUER = '|'.join(f'(?P<{k}>{v})' for k, v in _NOMES.items())
# "Ed, monta um treino", "oi Eva", "fala Jarvis" — o nome logo no começo (depois do "Solis").
_COMECO = re.compile(r'^(?:solis\s+)?(?:(?:oi|ei|ola|e ai|fala|alo|bom dia|boa tarde|boa noite)\s+)?(?:o\s+|a\s+)?'
                     rf'(?:{_QUALQUER})\b')
# "chama o Ed", "quero falar com a Eva", "passa pro Assessor", "volta pro Solis".
_CHAMA = re.compile(
    r'\b(?:chama|chame|chamar|passa|passe|passar|quero falar|queria falar|deixa eu falar|vou falar|fala|fale|falar'
    r'|conversar|volta|voltar|devolve)\s+(?:(?:com|pro|pra|para)\s+)?(?:o\s+|a\s+)?' rf'(?:{_QUALQUER})\b')

# O assunto de cada uma: palavras, sem modelo. Cada palavra que bate conta 1.
_ASSUNTOS = {
    'assessor': re.compile(
        # "recebi" sozinho não conta ("recebi uma proposta de emprego" é da Eva):
        # o recebimento com valor já vem pelo financas.parece_lancamento.
        r'\b(gastei|gasto|gastos|paguei|pagar a|quanto (?:eu )?recebi|financas|financeiro|orcamento|dinheiro|saldo'
        r'|fatura|boleto|sobrou|meu salario|conta de (?:luz|agua|internet|gas|telefone|celular)|lancamentos?|extrato'
        r'|economizar|poupar|dividas?|agenda|compromissos?|lembrete|me lembr[ae]|lembra de|tarefas?|reuniao|consulta'
        r'|rotina|marca(?:r)? (?:uma|um)|marcad[oa]s?|anota (?:ai|isso|que)|amanha cedo)\b'),
    'ed': re.compile(
        r'\b(treinos?|treinar|treinei|academia|muscula\w*|malhar|malhei|malhacao|exercicios?|series de|repeticoes'
        r'|supino|agachamento|leg press|biceps|triceps|peito|costas|ombros?|abdomen|abdominais?|gluteos?|cardio'
        r'|corrida|correr|corri|caminhada|alongamento|hipertrofia|massa muscular|ganhar massa|emagrec\w*'
        r'|perder peso|meu peso|estou pesando|to pesando|gordura|dieta|caloria\w*|proteina\w*|carboidrato\w*|macros'
        r'|whey|creatina|suplement\w*|refeic\w*|cardapio|nutricionista|jejum|lesao|dor muscular)\b'),
    'eva': re.compile(
        r'\b(carreira|meu trabalho|no trabalho|do trabalho|de trabalho|emprego|desempregado|minha chefe|meu chefe'
        r'|meu gestor|minha gestora|meu lider|minha lider|promocao|aumento de salario|pedir (?:um )?aumento'
        r'|entrevista|curriculo|linkedin'
        r'|vaga|demissao|demitido|demitida|colegas? de trabalho|renda extra|mudar de area|transicao de carreira'
        r'|burnout|esgotad[oa]|desabaf\w*|frustrad[oa]|desmotivad[oa]|meu emprego|plano de carreira|salario novo'
        r'|proposta de emprego)\b'),
    'jarvis': re.compile(
        r'\b(codigo|programar|programacao|bug|debug|deploy|commit|git|github|pull request|repositorio|branch|merge'
        r'|python|typescript|javascript|react|tauri|fastapi|sql|banco de dados|api|endpoint|backend|frontend'
        r'|script|compil\w*|build|testes automatizados|rodar os testes|roda os testes|pytest|npm|docker'
        r'|claude code|codex|o claude|stack trace|refator\w*|site (?:esta |ta )?fora do ar|site caiu|servidor caiu|dominio|hospedagem|vercel|supabase'
        r'|servidor mcp|o sistema que)\b'),
}
# No empate (sem quem está falando entre as empatadas), o dono do assunto ganha
# do Assessor: "o Claude Code travou no meio da tarefa" é do Jarvis — a
# "tarefa" ali é palavra solta, não um pedido de rotina (medido, 25/11/2026).
_ORDEM = ['ed', 'eva', 'jarvis', 'assessor']
# O que o Solis já reconhece em código como rotina e finanças (rapidas.py) é do
# Assessor, com peso de lançamento: "o que eu tenho pra fazer hoje?" é o pedido
# rápido das tarefas.
_RAPIDAS_DO_ASSESSOR = {'agenda', 'tarefas', 'lembrete', 'lancamento', 'gastos'}
# "marca dentista dia 3 às 10h": o verbo no começo é pedido de agenda.
_MARCA = re.compile(r'^(?:solis\s+)?(?:marca|marque|agenda|agende|desmarca|cancela)\b')


def chamado(texto: str) -> str | None:
    """A personalidade chamada pelo nome, ou None."""
    t = _simples(texto)
    m = _COMECO.match(t) or _CHAMA.search(t)
    if not m:
        return None
    # Um "Solis" sozinho no começo é a palavra de ativação, não um chamado.
    if m.lastgroup == 'solis' and m.re is _COMECO:
        resto = _simples(texto)[m.end():].strip()
        return chamado(resto) if resto else None
    return m.lastgroup


def do_assunto(texto: str, atual: str | None = None) -> str | None:
    """A dona do assunto, ou None. Empate: fica quem está falando, se é uma das
    empatadas; senão, a ordem de _ORDEM."""
    import datetime as dt

    from . import rapidas
    t = _simples(texto)
    pontos = {k: len(r.findall(t)) for k, r in _ASSUNTOS.items()}
    rapida = rapidas.responder(texto, dt.datetime.now())
    if rapida and rapida['tipo'] in _RAPIDAS_DO_ASSESSOR:
        pontos['assessor'] += 3
    if _MARCA.match(t):
        pontos['assessor'] += 1
    melhor = max(pontos.values())
    if not melhor:
        return None
    empatadas = [k for k in _ORDEM if pontos[k] == melhor]
    return atual if atual in empatadas else empatadas[0]


def quem(texto: str, atual: str | None = None) -> str:
    """Quem responde esta mensagem: o chamado, senão o dono do assunto, senão
    quem já estava falando (o Solis numa conversa nova)."""
    return chamado(texto) or do_assunto(texto, atual) or (atual if atual in TODAS else 'solis')


def da_conversa(conversa: int | None) -> str:
    """Quem está falando na conversa agora (o Solis se ninguém foi chamado)."""
    if conversa is None:
        return 'solis'
    return banco.personalidade_da_conversa(conversa) or 'solis'


def escolher(conversa: int | None, texto: str) -> tuple[Personalidade, bool]:
    """(quem responde, se acabou de entrar) — e guarda na conversa. "Acabou de
    entrar": é a primeira resposta dela agora, e ela se apresenta."""
    antes = da_conversa(conversa)
    agora = quem(texto, antes)
    if conversa is not None and agora != antes:
        banco.guardar_personalidade(conversa, agora)
    return de(agora), agora != antes


def nota(p: Personalidade, entrou: bool = False) -> str:
    """O jeito dela, como nota pro cérebro (vazia pro Solis de sempre)."""
    if p.id == 'solis':
        return ''
    apresentar = (f' É a sua primeira resposta agora: comece dizendo, em poucas palavras, que é {p.chamado} '
                  f'("Aqui é {p.chamado}." ou parecido).' if entrou else '')
    return (f'\n\n[Quem responde agora é {p.chamado}, a personalidade do Solis pra {p.nicho}. O jeito: {p.jeito} '
            f'Responda como {p.chamado}, em primeira pessoa, com esse jeito; as ferramentas e a memória são as do '
            f'Solis, as mesmas de sempre.{apresentar}]')


def voz_gemini(quem: str | None) -> str:
    """A voz do Gemini de quem fala (a escolhida pelo Matheus, pro Solis)."""
    from . import fala
    p = de(quem)
    return fala.voz_gemini() if p.id == 'solis' else p.gemini


def quem_disse(m: dict) -> str:
    """'Matheus', 'Solis' — ou a personalidade que respondeu ('Ed (do Solis)')."""
    if m['papel'] == 'pessoa':
        return 'Matheus'
    if m.get('personalidade') in TODAS and m['personalidade'] != 'solis':
        return f'{de(m["personalidade"]).nome} (do Solis)'
    return 'Solis'


def lista() -> list[dict]:
    """Pra tela e pra API: quem são, o nicho e as vozes."""
    return [{'id': p.id, 'nome': p.nome, 'nicho': p.nicho, 'gemini': p.gemini, 'edge': p.edge, 'cor': p.cor}
            for p in TODAS.values()]
