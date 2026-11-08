"""O que o Solis aprende sobre o Matheus, conversa a conversa.

Dois caminhos, e o segundo existe porque o primeiro erra:

1. Automático — depois de cada resposta, uma segunda pergunta ao modelo: "o que
   o Matheus disse aqui que vale guardar?". Roda em segundo plano, depois que a
   resposta já apareceu, então não atrasa a conversa.
2. Pedido — se a mensagem pede pra guardar ("grave", "anote", "lembre que..."),
   algo É guardado, mesmo que o modelo não ache nada ou o Ollama esteja fora.
   Um modelo de 3B decide mal o que é relevante; o que o Matheus pediu não pode
   depender dessa decisão.
"""
import logging
import re

from . import banco, busca, ollama

log = logging.getLogger('solis.memoria')

# Imperativos de guardar. "lembra" e "guarda" ficam de fora de propósito: são
# como se PERGUNTA ("você lembra o que...?", "ele guarda as conversas?").
PEDIDO = re.compile(r'\b(grave|guarde|anote|memorize|lembre(-se)?|registre)\b', re.IGNORECASE)

# Pedido explícito de sigilo. Como o PEDIDO: se a palavra está lá, vale, mesmo
# que o modelo não tenha achado o assunto sensível.
PRIVADO = re.compile(r'\b(privad[oa]s?|confidencia(l|is)|sigilos[oa]s?|segredo)\b', re.IGNORECASE)

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
) -> list[str]:
    """Extrai e guarda o que houver de novo na `mensagem`; devolve o texto das
    memórias que guardou (a tela mostra cada uma). Nunca levanta: roda depois
    da resposta, e não há mais ninguém pra receber um erro.

    `antiga` ("ChatGPT, 14/03/2023"): a mensagem são as falas do Matheus numa
    conversa importada. Aí não há pedido (um "grave isso" dito ao ChatGPT anos
    atrás não é pedido ao Solis) e não há substituição — o passado não pode
    apagar o presente: "trabalho na X" de 2023 não derruba "Trabalha na
    Syngenta" de hoje. O fato vem com a data."""
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
        resposta = await ollama.responder_json(modelo, INSTRUCAO, texto, ESQUEMA)
        novas = resposta.get('memorias', [])
    except Exception:
        log.exception('extração de memória falhou')
        novas = []

    # Só substitui o que o modelo viu: um número inventado, ou de uma memória que
    # não estava na lista, não pode apagar nada da tela.
    substituiveis = {} if antiga else {m['id']: m for m in candidatas}
    vistas = {_normal(m['texto']) for m in guardadas}
    guardou = saiu_privada = False
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

    # Se saiu algo privado desta mensagem, ela (e a resposta) não vai mais pra
    # nuvem — nem no histórico, nem como trecho antigo.
    if mensagem_id is not None and (privado or saiu_privada):
        banco.marcar_privada(mensagem_id)
    return guardadas_agora
