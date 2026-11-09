"""O que o Solis aprende sobre o Matheus, conversa a conversa.

Dois caminhos, e o segundo existe porque o primeiro erra:

1. Automático — depois de cada resposta, uma segunda pergunta ao modelo: "o que
   o Matheus disse aqui que vale guardar?". Roda em segundo plano, depois que a
   resposta já apareceu, então não atrasa a conversa.
2. Pedido — se a mensagem pede pra guardar ("grave", "anote", "lembre que..."),
   algo É guardado, mesmo que o modelo não ache nada ou o Ollama esteja fora.
   Um modelo de 3B decide mal o que é relevante; o que o Matheus pediu não pode
   depender dessa decisão.

A mesma pergunta tira as tarefas ("me lembra de pagar a luz dia 15", "tenho que
entregar o relatório sexta às 14h"), com o prazo já em data: uma chamada só ao
modelo de fundo, e não duas.
"""
import datetime as dt
import logging
import re
import unicodedata

from . import banco, busca, ollama

log = logging.getLogger('solis.memoria')

# Imperativos de guardar. "lembra" e "guarda" ficam de fora de propósito: são
# como se PERGUNTA ("você lembra o que...?", "ele guarda as conversas?").
PEDIDO = re.compile(r'\b(grave|guarde|anote|memorize|lembre(-se)?|registre)\b', re.IGNORECASE)

# Pedido explícito de sigilo. Como o PEDIDO: se a palavra está lá, vale, mesmo
# que o modelo não tenha achado o assunto sensível.
PRIVADO = re.compile(r'\b(privad[oa]s?|confidencia(l|is)|sigilos[oa]s?|segredo)\b', re.IGNORECASE)

# Tarefa de saúde, dinheiro ou documento é privada (a regra do Solis: isso nunca
# sai da máquina). Por palavra, e não pelo modelo: pedido o campo `privada` na
# tarefa, o qwen3:8b acertou 9 e 10 de 11 casos em duas medições (09/11/2026) —
# a fatura do cartão e o psiquiatra saíam pra nuvem — e cada frase a mais na
# instrução fazia ele errar outra coisa (a data de "quinta", "grave" virando
# tarefa). Errar pra mais privada só tira a tarefa do pedido à nuvem.
SENSIVEL = re.compile(
    r'\b(exames?|consultas?|m[eé]dic[oa]s?|dentista|psic[oó]log[oa]|psiquiatra|terapia|rem[eé]dios?|'
    r'hospital|vacinas?|cirurgia|sa[uú]de|fatura|cart[aã]o|boletos?|banco|pix|impostos?|'
    r'empr[eé]stimo|sal[aá]rio|senhas?|cpf|rg|passaporte|cnh)\b',
    re.IGNORECASE,
)

# Quantas memórias existentes o extrator vê, as mais ligadas à mensagem. Mandar
# todas não escala; e ele só precisa das do mesmo assunto pra notar o que mudou.
CANDIDATAS = 15

# Tema de uma memória pedida que não passou pelo modelo.
TEMA_PEDIDO = 'Pedido direto'

INSTRUCAO = (
    'Você extrai memórias sobre o Matheus a partir da última mensagem dele.\n\n'
    'Uma memória é um fato duradouro e útil no futuro: quem ele é, trabalho, '
    'estudos, preferências, rotina, projetos, pessoas próximas, decisões.\n'
    'NÃO é memória: perguntas, cumprimentos, pedidos de tarefa, conhecimento '
    'geral, e qualquer coisa que já esteja nas memórias guardadas.\n'
    'Só vale o que o MATHEUS afirmou. O contexto anterior serve pra entender a '
    'mensagem, não como fonte.\n\n'
    'Cada memória: uma frase curta em terceira pessoa, sem o nome dele '
    '("Trabalha na Syngenta."), e um tema curto que agrupe ("Trabalho", '
    '"Preferências de comunicação", "Projeto Solis").\n'
    'Marque privada = true quando for saúde, senha ou credencial, dinheiro e '
    'finanças, documentos pessoais, ou quando ele disser que é privado. Memória '
    'privada nunca sai do computador dele.\n'    'Se a memória nova CORRIGE ou ATUALIZA uma já guardada (mudou de emprego, '
    'de cidade, de opinião), ponha em substitui o número dela; senão, 0. Só '
    'substitua quando a nova tornar a antiga falsa — fato novo sobre o mesmo '
    'assunto não é substituição.\n'
    'Sem nada novo, devolva a lista vazia.'
)

# Medido em 09/11/2026 no qwen3:8b, 20 mensagens (tarefas com e sem prazo, "dia
# 15", "sexta às 14h", "fim do mês", "daqui a duas semanas", duas tarefas numa
# mensagem, saúde e dinheiro; e o que não é tarefa: pergunta, pedido pro Solis
# fazer agora, o que já foi feito, fatos): 20 de 20 tarefas com o prazo certo,
# 11 de 11 com a privacidade certa e 20 de 20 com as memórias certas, em ~10 s
# — o mesmo tempo da extração só de memórias. O que levou lá: o calendário dos
# próximos dias no pedido (o modelo copia a data em vez de fazer conta); "pedido
# pro Solis fazer agora não é tarefa" ("me ajuda a escrever um email" virava
# tarefa); e o que o código faz depois — _prazo, _eh_a_tarefa, corrigir_data e
# SENSIVEL. O modelo é determinístico pra um mesmo pedido, mas cada frase mudada
# na instrução troca qual caso ele erra: tirar a hora de "Agora", pôr "daqui a N
# dias" no calendário ou pedir `privada` na tarefa, todos pioraram. Por isso a
# instrução ficou como está, e as contas foram pro código.
INSTRUCAO_TAREFAS = (
    '\n\nTarefas: além das memórias, extraia as tarefas que o MATHEUS disse que ELE precisa '
    'fazer depois, ou pediu pra lembrar ("me lembra de...", "tenho que...", "preciso... até sexta"). '
    'Cada tarefa: a ação, curta, no infinitivo e começando com maiúscula ("Pagar a conta de luz", '
    '"Reunião com o orientador" — nunca "Lembrar de..."); o prazo como AAAA-MM-DD, tirado do '
    'calendário da mensagem, ou "" se ele não disse quando (nunca a data de agora por padrão); a '
    'hora como HH:MM se ele disse uma hora ou um período ("à noite" = 20:00, "de manhã" = 09:00), ou "".\n'
    'NÃO é tarefa: pedido pro Solis fazer algo agora, nesta conversa ("me ajuda a escrever um email", '
    '"pode resumir isso?") — quem faz é o Solis, não o Matheus; o que já foi feito; pergunta.\n'
    'Uma tarefa NUNCA vai também em memórias: compromisso e coisa a fazer são só tarefa.'
)
# Compromisso: o que tem dia marcado em que ele vai ESTAR em algum lugar. Medido
# em 09/11/2026 no qwen3:8b, 22 mensagens (consulta, reunião com duração e meio,
# "das 11h30 às 13h", viagem sem hora, e as tarefas e não-tarefas das medições
# anteriores): 18 de 18 compromissos e 18 de 18 tarefas certos, 22 de 22 nas
# memórias, em ~13 s. Os dois cortes no código: compromisso numa mensagem que
# fala em cancelar, desmarcar ou adiar não é criado ("a reunião de amanhã foi
# cancelada" virava compromisso), e a tarefa que repete um compromisso sai
# ("reunião com o orientador" saía nos dois). Repetição ("toda terça") ainda não
# existe: vira só a próxima.
INSTRUCAO_COMPROMISSOS = (
    '\n\nCompromissos: o que tem dia (e quase sempre hora) marcado em que o MATHEUS vai ESTAR '
    'em algum lugar ou com alguém — reunião, consulta, aula, treino, viagem, evento. Vai em '
    'compromissos, NUNCA em tarefas. Tarefa é algo que ele precisa FAZER até um prazo ("pagar", '
    '"entregar", "comprar", "marcar a consulta"). Cada compromisso: o título curto ("Consulta com o '
    'dentista"); o dia como AAAA-MM-DD, do calendário; a hora de início HH:MM ou ""; a duração em '
    'minutos se ele disse (ou o fim), senão 0; o lugar ou meio ("Google Meet", "academia") ou "". '
    'O que já aconteceu ou foi cancelado não é compromisso.'
)
CANCELADO = re.compile(r'\b(cancelad[oa]s?|cancelou|desmarcad[oa]s?|desmarquei|adiad[oa]s?|adiou)\b', re.IGNORECASE)

DIAS = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
CALENDARIO_DIAS = 35

ESQUEMA = {
    'type': 'object',
    'properties': {
        'memorias': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'texto': {'type': 'string'},
                    'tema': {'type': 'string'},
                    'privada': {'type': 'boolean'},
                    # 0 em vez de null: união de tipos é onde a gramática de
                    # formato de modelo pequeno mais tropeça.
                    'substitui': {'type': 'integer'},
                },
                'required': ['texto', 'tema', 'privada', 'substitui'],
            },
        }
    },
    'required': ['memorias'],
}


# Com tarefas: o mesmo esquema e mais a lista delas. A conversa importada não
# usa este — tarefa de anos atrás não é tarefa de hoje.
ESQUEMA_COM_TAREFAS = {
    **ESQUEMA,
    'properties': {
        **ESQUEMA['properties'],
        'tarefas': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'texto': {'type': 'string'}, 'prazo': {'type': 'string'}, 'hora': {'type': 'string'}},
                'required': ['texto', 'prazo', 'hora'],
            },
        },
    },
    'required': ['memorias', 'tarefas'],
}
# E com compromissos: é este que vai pro modelo nas conversas de agora.
ESQUEMA_COMPLETO = {
    **ESQUEMA_COM_TAREFAS,
    'properties': {
        **ESQUEMA_COM_TAREFAS['properties'],
        'compromissos': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'titulo': {'type': 'string'}, 'dia': {'type': 'string'}, 'hora': {'type': 'string'},
                    'duracao': {'type': 'integer'}, 'onde': {'type': 'string'},
                },
                'required': ['titulo', 'dia', 'hora', 'duracao', 'onde'],
            },
        },
    },
    'required': ['memorias', 'tarefas', 'compromissos'],
}


def calendario(agora: dt.datetime) -> str:
    """O dia de hoje e os próximos, cada um com a data."""
    linhas = [f'Agora: {DIAS[agora.weekday()]}, {agora:%d/%m/%Y}, {agora:%H:%M}.', 'Calendário dos próximos dias:']
    for i in range(CALENDARIO_DIAS):
        d = agora.date() + dt.timedelta(days=i)
        extra = ' (hoje)' if i == 0 else ' (amanhã)' if i == 1 else ''
        linhas.append(f'{DIAS[d.weekday()]} {d:%d/%m} = {d:%Y-%m-%d}{extra}')
    return '\n'.join(linhas)


def _prazo(tarefa: dict, agora: dt.datetime) -> tuple[str | None, str | None]:
    """(prazo, hora) validados. Sem prazo dito, o modelo às vezes devolve o
    "Agora" do pedido — "anota aí: comprar ração" saía pra hoje, na hora exata
    do pedido (medido). Prazo de hoje na hora de agora é essa cópia: sem prazo."""
    prazo, hora = (tarefa.get('prazo') or '').strip(), (tarefa.get('hora') or '').strip()
    try:
        dt.date.fromisoformat(prazo)
    except ValueError:
        return None, None
    if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', hora):
        hora = ''
    if (prazo, hora) == (f'{agora:%Y-%m-%d}', f'{agora:%H:%M}'):
        return None, None
    return prazo, hora or None


# As duas contas em que o modelo erra, medidas (09/11/2026): o dia da semana
# ("quinta às 15h" saía na quarta, 11/11, em 2 de 4 versões da instrução) e o
# "daqui a N semanas" (duas semanas saía 01/12 e 02/12 em vez de 23/11). As duas
# são conta, e conta o código faz certo. Só quando a mensagem tem UMA tarefa e
# UMA expressão dessas: com duas, não dá pra saber qual data é de qual.
SEMANA = {
    'segunda': 0, 'terça': 1, 'terca': 1, 'quarta': 2, 'quinta': 3, 'sexta': 4, 'sábado': 5, 'sabado': 5,
    'domingo': 6,
}
NUMEROS = {'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'três': 3, 'tres': 3, 'quatro': 4, 'cinco': 5, 'seis': 6,
           'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10, 'quinze': 15}
DIA_DA_SEMANA = re.compile(r'\b(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)(-feira)?\b', re.I)
DAQUI_A = re.compile(r'\b(?:daqui a|em|dentro de)\s+(\d+|' + '|'.join(NUMEROS) + r')\s+(dias?|semanas?)\b', re.I)


def corrigir_data(mensagem: str, prazo: str | None, agora: dt.datetime) -> str | None:
    """O prazo do modelo, corrigido pela conta quando a mensagem diz o dia da
    semana ou "daqui a N dias/semanas" e o modelo errou a conta."""
    hoje = agora.date()
    daqui = DAQUI_A.findall(mensagem)
    if len(daqui) == 1:
        [(n, unidade)] = daqui
        dias = (int(n) if n.isdigit() else NUMEROS[n.lower()]) * (7 if unidade.lower().startswith('semana') else 1)
        return (hoje + dt.timedelta(days=dias)).isoformat()
    semana = {SEMANA[d.lower()] for d, _ in DIA_DA_SEMANA.findall(mensagem)}
    if prazo and len(semana) == 1:
        [alvo] = semana
        data = dt.date.fromisoformat(prazo)
        if data.weekday() != alvo:
            # O dia com esse nome mais perto do que o modelo deu ("quinta" com
            # prazo na quarta vira a quinta seguinte), nunca antes de hoje.
            frente = data + dt.timedelta(days=(alvo - data.weekday()) % 7)
            tras = frente - dt.timedelta(days=7)
            data = tras if tras >= hoje and (data - tras) < (frente - data) else frente
            return data.isoformat()
    return prazo


def _tokens(texto: str) -> set[str]:
    sem_acento = unicodedata.normalize('NFKD', texto.lower()).encode('ascii', 'ignore').decode()
    return {p for p in re.findall(r'\w+', sem_acento) if len(p) >= 3} - {'para', 'pra', 'com', 'que', 'dos', 'das', 'uma', 'por'}


def _eh_a_tarefa(memoria: str, tarefas: list[str]) -> bool:
    """A memória repete uma tarefa ("Renovar CNH no fim do mês" com a tarefa
    "Renovar a CNH"): 60% ou mais das palavras da tarefa estão nela. O modelo
    fazia isso em 4 de 17 casos mesmo instruído a não fazer (medido)."""
    m = _tokens(memoria)
    return any((t := _tokens(tarefa)) and len(t & m) / len(t) >= 0.6 for tarefa in tarefas)


def eh_pedido(texto: str) -> bool:
    # Pergunta não é pedido, mesmo com o verbo: "você grava as conversas?".
    return bool(PEDIDO.search(texto)) and not texto.rstrip().endswith('?')


def eh_privado(texto: str) -> bool:
    return bool(PRIVADO.search(texto))


def _normal(texto: str) -> str:
    return re.sub(r'\W+', ' ', texto).strip().lower()


# O que não diz de que assunto é: os verbos de pedido e as palavras vazias.
VAZIAS = {
    'grave', 'guarde', 'anote', 'memorize', 'lembre', 'registre', 'isso', 'isto', 'essa', 'esse',
    'minha', 'minhas', 'meus', 'para', 'sobre', 'tenho', 'estou', 'está', 'agora', 'ainda', 'também',
    'quero', 'favor', 'pode', 'aqui', 'então', 'como', 'mais', 'muito', 'sempre', 'nunca', 'quando',
}


def _palavras(texto: str) -> set[str]:
    return {p for p in _normal(texto).split() if len(p) >= 4 and p not in VAZIAS}


def _fala_de(memoria: str, mensagem: str) -> bool:
    """A memória e a mensagem têm alguma palavra de conteúdo em comum.
    Estrito de propósito: errar pra "não fala" guarda o pedido cru (uma
    memória a mais); errar pra "fala" perde o que foi pedido."""
    return bool(_palavras(memoria) & _palavras(mensagem))


def guardar_pedido_cru(texto: str, conversa: int | None) -> None:
    """O pedido sem modelo nenhum: guarda a própria mensagem. Feio, mas fica."""
    banco.adicionar_memoria(texto.strip(), TEMA_PEDIDO, True, conversa, privada=eh_privado(texto))


async def aprender(
    modelo: str,
    conversa: int,
    mensagem: str,
    contexto: list[dict],
    mensagem_id: int | None = None,
    antiga: str | None = None,
    tarefas: list[dict] | None = None,
    agora: dt.datetime | None = None,
    compromissos: list[dict] | None = None,
) -> list[str]:
    """Extrai e guarda o que houver de novo na `mensagem`; devolve o texto das
    memórias que guardou (a tela mostra cada uma). Nunca levanta: roda depois
    da resposta, e não há mais ninguém pra receber um erro.

    `antiga` ("ChatGPT, 14/03/2023"): a mensagem são as falas do Matheus numa
    conversa importada. Aí não há pedido (um "grave isso" dito ao ChatGPT anos
    atrás não é pedido ao Solis) e não há substituição — o passado não pode
    apagar o presente: "trabalho na X" de 2023 não derruba "Trabalha na
    Syngenta" de hoje. O fato vem com a data.

    As tarefas tiradas da mensagem são guardadas também, e cada uma entra em
    `tarefas` (texto, prazo, hora), pra a tela mostrar. Na importada, não.
    `agora`: a hora local (fixa nos testes)."""
    agora = agora or dt.datetime.now()
    pedido = eh_pedido(mensagem) and antiga is None
    privado = eh_privado(mensagem) and antiga is None
    guardadas = banco.memorias()
    candidatas = await busca.memorias_parecidas(mensagem, CANDIDATAS)

    anteriores = '\n'.join(f'{"Matheus" if m["papel"] == "pessoa" else "Solis"}: {m["texto"]}' for m in contexto)
    if antiga:
        fala = (
            f'\n\nFalas do Matheus numa conversa antiga ({antiga}). Fato que pode ter mudado '
            'desde então vai com a data ("Em 2023, trabalhava na X."), e nunca substitui '
            f'uma memória guardada (substitui = 0):\n{mensagem}'
        )
    else:
        fala = f'\n\nÚltima mensagem do Matheus:\n{mensagem}'
    texto = (
        'Memórias já guardadas sobre assuntos parecidos (número: texto):\n'
        + ('\n'.join(f'{m["id"]}: {m["texto"]}' for m in candidatas) or '(nenhuma)')
        + f'\n\nContexto anterior:\n{anteriores or "(nenhum)"}'
        + ('' if antiga else '\n\n' + calendario(agora))
        + fala
    )
    if pedido:
        texto += '\n\nO Matheus PEDIU pra guardar algo nesta mensagem: extraia o que ele pediu.'

    try:
        # COM raciocínio, de propósito — o contrário do título e do resumo.
        # Medido no qwen3:8b em 12 casos (fatos, perguntas, pedidos, sigilo,
        # mudança de emprego e de cidade): pensando acertou 12, em ~11 s; sem
        # pensar acertou 10, em ~1 s, e deixou de guardar uma preferência dita
        # com todas as letras e a senha do wifi. Guardar é a razão de o Solis
        # existir, e isto roda depois da resposta, sem prender a conversa.
        if antiga:
            resposta = await ollama.responder_json(modelo, INSTRUCAO, texto, ESQUEMA)
        else:
            resposta = await ollama.responder_json(
                modelo, INSTRUCAO + INSTRUCAO_TAREFAS + INSTRUCAO_COMPROMISSOS, texto, ESQUEMA_COMPLETO
            )
        novas = resposta.get('memorias', [])
        achadas = [] if antiga else [t for t in resposta.get('tarefas', []) if (t.get('texto') or '').strip()]
        marcados = [] if antiga else [c for c in resposta.get('compromissos', []) if (c.get('titulo') or '').strip()]
    except Exception:
        log.exception('extração de memória falhou')
        novas, achadas, marcados = [], [], []

    if CANCELADO.search(mensagem):
        marcados = []
    titulos = [c['titulo'].strip() for c in marcados]
    # A tarefa que repete um compromisso sai: ele é o compromisso.
    achadas = [t for t in achadas if not _eh_a_tarefa(t['texto'], titulos)]
    # A memória que só repete uma tarefa ou um compromisso sai (o sigilo dela fica).
    textos_tarefas = [t['texto'].strip() for t in achadas] + titulos
    repetidas = [m for m in novas if _eh_a_tarefa(m.get('texto', ''), textos_tarefas)]
    novas = [m for m in novas if m not in repetidas]

    # Só substitui o que o modelo viu: um número inventado, ou de uma memória que
    # não estava na lista, não pode apagar nada da tela.
    substituiveis = {} if antiga else {m['id']: m for m in candidatas}
    vistas = {_normal(m['texto']) for m in guardadas}
    guardou = False
    saiu_privada = any(m.get('privada') for m in repetidas)
    guardadas_agora: list[str] = []
    for m in novas:
        conteudo, tema = m.get('texto', '').strip(), m.get('tema', '').strip()
        if not conteudo:
            continue
        if _normal(conteudo) in vistas:
            # Já sabia. Se foi um pedido, está atendido do mesmo jeito — mas só
            # se a repetida fala do que foi pedido. Modelo pequeno devolve uma
            # memória guardada qualquer: "grave: minha cor preferida é verde"
            # voltava como "Tem uma loja e quer emitir NF-e.", e o pedido se
            # perdia (visto com o llama3.2:3b, 08/11/2026).
            guardou = guardou or (pedido and _fala_de(conteudo, mensagem))
            continue
        antiga = substituiveis.pop(m.get('substitui') or 0, None)
        banco.adicionar_memoria(
            conteudo,
            tema or 'Geral',
            pedido,
            conversa,
            # Sigilo não se perde numa atualização: o que era privado continua.
            privada=privado or bool(m.get('privada')) or bool(antiga and antiga['privada']),
            substitui=antiga['id'] if antiga else None,
        )
        vistas.add(_normal(conteudo))
        guardou = True
        guardadas_agora.append(conteudo)
        saiu_privada = saiu_privada or bool(m.get('privada'))

    if pedido and not guardou:
        guardar_pedido_cru(mensagem, conversa)
        guardadas_agora.append(mensagem.strip())

    # O sigilo das memórias desta mensagem vale pras tarefas dela; o de uma
    # tarefa sensível vale só pra ela (e tira a mensagem da nuvem).
    memoria_privada = saiu_privada
    for t in achadas:
        prazo, hora = _prazo(t, agora)
        if len(achadas) == 1:
            prazo = corrigir_data(mensagem, prazo, agora)
        texto_tarefa = t['texto'].strip().rstrip('.')
        sensivel = bool(SENSIVEL.search(texto_tarefa))
        banco.adicionar_tarefa(texto_tarefa, prazo, hora, conversa, privada=privado or memoria_privada or sensivel)
        saiu_privada = saiu_privada or sensivel
        if tarefas is not None:
            tarefas.append({'texto': texto_tarefa, 'prazo': prazo, 'hora': hora})

    for c in marcados:
        dia, hora = _prazo({'prazo': c.get('dia'), 'hora': c.get('hora')}, agora)
        if len(marcados) == 1:
            dia = corrigir_data(mensagem, dia, agora)
        if not dia:
            continue  # compromisso sem dia não cabe na Agenda
        titulo = c['titulo'].strip().rstrip('.')
        duracao = c.get('duracao') if isinstance(c.get('duracao'), int) and 0 < c['duracao'] <= 24 * 60 else None
        onde = (c.get('onde') or '').strip() or None
        sensivel = bool(SENSIVEL.search(titulo))
        banco.adicionar_compromisso(
            titulo, dia, hora, duracao, onde, conversa, privado=privado or memoria_privada or sensivel
        )
        saiu_privada = saiu_privada or sensivel
        if compromissos is not None:
            compromissos.append({'titulo': titulo, 'dia': dia, 'hora': hora, 'duracao': duracao, 'onde': onde})

    # Se saiu algo privado desta mensagem, ela (e a resposta) não vai mais pra
    # nuvem — nem no histórico, nem como trecho antigo.
    if mensagem_id is not None and (privado or saiu_privada):
        banco.marcar_privada(mensagem_id)
    return guardadas_agora
