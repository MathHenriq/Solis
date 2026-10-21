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

from . import banco, ollama

log = logging.getLogger('solis.memoria')

# Imperativos de guardar. "lembra" e "guarda" ficam de fora de propósito: são
# como se PERGUNTA ("você lembra o que...?", "ele guarda as conversas?").
PEDIDO = re.compile(r'\b(grave|guarde|anote|memorize|lembre(-se)?|registre)\b', re.IGNORECASE)

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
    'Sem nada novo, devolva a lista vazia.'
)

ESQUEMA = {
    'type': 'object',
    'properties': {
        'memorias': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'texto': {'type': 'string'}, 'tema': {'type': 'string'}},
                'required': ['texto', 'tema'],
            },
        }
    },
    'required': ['memorias'],
}


def eh_pedido(texto: str) -> bool:
    # Pergunta não é pedido, mesmo com o verbo: "você grava as conversas?".
    return bool(PEDIDO.search(texto)) and not texto.rstrip().endswith('?')


def _normal(texto: str) -> str:
    return re.sub(r'\W+', ' ', texto).strip().lower()


def guardar_pedido_cru(texto: str, conversa: int | None) -> None:
    """O pedido sem modelo nenhum: guarda a própria mensagem. Feio, mas fica."""
    banco.adicionar_memoria(texto.strip(), TEMA_PEDIDO, True, conversa)


async def aprender(modelo: str, conversa: int, mensagem: str, contexto: list[dict]) -> None:
    """Extrai e guarda o que houver de novo na `mensagem`. Nunca levanta: roda
    depois da resposta, e não há mais ninguém pra receber um erro."""
    pedido = eh_pedido(mensagem)
    guardadas = banco.memorias()

    anteriores = '\n'.join(f'{"Matheus" if m["papel"] == "pessoa" else "Solis"}: {m["texto"]}' for m in contexto)
    texto = (
        'Memórias já guardadas:\n'
        + ('\n'.join(f'- {m["texto"]}' for m in guardadas) or '(nenhuma)')
        + f'\n\nContexto anterior:\n{anteriores or "(nenhum)"}'
        + f'\n\nÚltima mensagem do Matheus:\n{mensagem}'
    )
    if pedido:
        texto += '\n\nO Matheus PEDIU pra guardar algo nesta mensagem: extraia o que ele pediu.'

    try:
        resposta = await ollama.responder_json(modelo, INSTRUCAO, texto, ESQUEMA)
        novas = resposta.get('memorias', [])
    except Exception:
        log.exception('extração de memória falhou')
        novas = []

    vistas = {_normal(m['texto']) for m in guardadas}
    guardou = False
    for m in novas:
        conteudo, tema = m.get('texto', '').strip(), m.get('tema', '').strip()
        if not conteudo:
            continue
        if _normal(conteudo) in vistas:
            # Já sabia. Se foi um pedido, está atendido do mesmo jeito.
            guardou = guardou or pedido
            continue
        banco.adicionar_memoria(conteudo, tema or 'Geral', pedido, conversa)
        vistas.add(_normal(conteudo))
        guardou = True

    if pedido and not guardou:
        guardar_pedido_cru(mensagem, conversa)
