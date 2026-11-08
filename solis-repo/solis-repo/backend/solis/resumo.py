"""Conversa longa: o começo vira resumo, o fim vai inteiro.

Mandar a conversa toda não escala — passa da janela de contexto, e o Ollama
corta o começo sem avisar. Cortar sem resumir também perde: a decisão tomada na
mensagem 5 some na mensagem 50.

O modelo sempre recebe o resumo (que cobre até a mensagem `resumo_ate`) mais
TODAS as mensagens depois dele, sem buraco entre os dois. Quando as mensagens
depois do resumo passam de JANELA + LOTE, as mais velhas entram no resumo e
ficam as JANELA últimas. Resumir em lote, e não a cada mensagem, é o que impede
uma terceira chamada ao modelo em toda resposta.
"""
import logging

from . import banco, ollama

log = logging.getLogger('solis.resumo')

# Mensagens que vão sempre inteiras.
JANELA = 20
# Quantas se deixa acumular além da janela antes de resumir de novo.
LOTE = 10

INSTRUCAO = (
    'Você resume o começo de uma conversa entre o Matheus e o Solis, o '
    'assistente dele, pra servir de memória do que já foi dito.\n'
    'Mantenha o que importa pra continuar a conversa: decisões, fatos, números, '
    'nomes, o que ficou combinado e o que ficou em aberto. Corte cumprimentos e '
    'repetição.\n'
    'Se houver um resumo anterior, junte o que é novo a ele — o resultado '
    'substitui o anterior. Em português do Brasil, em tópicos curtos, com no '
    'máximo 250 palavras.'
)


def para_o_modelo(conversa: int) -> tuple[str | None, list[dict], int]:
    """(resumo, mensagens que vão inteiras, id até onde o resumo cobre)."""
    texto, ate = banco.resumo(conversa)
    depois = banco.mensagens(conversa, depois_de=ate)
    # Teto: se o resumo falhar várias vezes seguidas (Ollama fora), o que vai
    # inteiro não cresce sem limite. O que ficar de fora não se perde — entra no
    # resumo assim que ele voltar a funcionar.
    return texto, depois[-(JANELA + LOTE):], ate


INSTRUCAO_TITULO = (
    'Você dá título a uma conversa entre o Matheus e o Solis, o assistente dele, '
    'pra ela aparecer numa lista de conversas.\n'
    'Responda só o título: de 2 a 6 palavras, em português do Brasil, dizendo o '
    'assunto ("Sistema de NF-e da loja", "Estudos de pandas e SQL"). Sem aspas, '
    'sem ponto final, sem "Título:".'
)

# Teto do título, e quanto da conversa o modelo lê pra dar o título.
TITULO_MAX = 60
TITULO_LE = 1500


def _limpar_titulo(bruto: str) -> str:
    """O modelo pequeno às vezes enfeita: aspas, "Título:", ponto final, uma
    explicação na linha de baixo. Fica a primeira linha, limpa."""
    linha = next((l for l in bruto.strip().splitlines() if l.strip()), '')
    linha = linha.strip().strip('*#').strip()
    if linha.lower().startswith('título:'):
        linha = linha[len('título:'):]
    linha = linha.strip().strip('"\'“”‘’').strip().rstrip('.').strip()
    return linha[:TITULO_MAX].rsplit(' ', 1)[0] if len(linha) > TITULO_MAX else linha


async def titular(modelo: str, conversa: int) -> str | None:
    """Dá um título curto à conversa que ainda não tem, lendo o começo dela.
    Devolve o título novo, ou None quando já havia um ou o modelo não respondeu
    — aí a lista mostra a primeira fala, e a próxima mensagem tenta de novo.
    Nunca levanta: roda depois da resposta."""
    if banco.titulo(conversa):
        return None
    falas = banco.mensagens(conversa)[:4]
    if not any(m['papel'] == 'solis' for m in falas):
        return None
    linhas = '\n'.join(f'{"Matheus" if m["papel"] == "pessoa" else "Solis"}: {m["texto"]}' for m in falas)
    try:
        bruto = await ollama.responder_texto(modelo, INSTRUCAO_TITULO, linhas[:TITULO_LE])
    except Exception:
        log.info('título da conversa %s ficou pra próxima', conversa)
        return None
    titulo = _limpar_titulo(bruto)
    if not titulo:
        return None
    banco.guardar_titulo(conversa, titulo)
    return titulo


async def resumir(modelo: str, conversa: int) -> bool:
    """Junta ao resumo as mensagens que saíram da janela, se já forem um lote;
    devolve se resumiu. Nunca levanta: roda depois da resposta, sem ninguém pra
    receber o erro."""
    texto, ate = banco.resumo(conversa)
    depois = banco.mensagens(conversa, depois_de=ate)
    if len(depois) <= JANELA + LOTE:
        return False
    velhas = depois[:-JANELA]
    linhas = '\n'.join(f'{"Matheus" if m["papel"] == "pessoa" else "Solis"}: {m["texto"]}' for m in velhas)
    pedido = f'Resumo anterior:\n{texto or "(nenhum)"}\n\nMensagens a incluir:\n{linhas}'
    try:
        novo = (await ollama.responder_texto(modelo, INSTRUCAO, pedido)).strip()
    except Exception:
        log.exception('resumo da conversa %s falhou', conversa)
        return False
    if novo:
        banco.guardar_resumo(conversa, novo, velhas[-1]['id'])
    return bool(novo)
