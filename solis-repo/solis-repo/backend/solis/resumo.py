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


async def resumir(modelo: str, conversa: int) -> None:
    """Junta ao resumo as mensagens que saíram da janela, se já forem um lote.
    Nunca levanta: roda depois da resposta, sem ninguém pra receber o erro."""
    texto, ate = banco.resumo(conversa)
    depois = banco.mensagens(conversa, depois_de=ate)
    if len(depois) <= JANELA + LOTE:
        return
    velhas = depois[:-JANELA]
    linhas = '\n'.join(f'{"Matheus" if m["papel"] == "pessoa" else "Solis"}: {m["texto"]}' for m in velhas)
    pedido = f'Resumo anterior:\n{texto or "(nenhum)"}\n\nMensagens a incluir:\n{linhas}'
    try:
        novo = (await ollama.responder_texto(modelo, INSTRUCAO, pedido)).strip()
    except Exception:
        log.exception('resumo da conversa %s falhou', conversa)
        return
    if novo:
        banco.guardar_resumo(conversa, novo, velhas[-1]['id'])
