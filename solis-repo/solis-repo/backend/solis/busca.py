"""Busca por significado: o que, de tudo que está guardado, importa pra ESTA mensagem.

Sem isto, toda memória ia em todo pedido, e nenhuma conversa antiga ia. Com
centenas de memórias o pedido passa da janela de contexto, o Ollama corta o
começo sem avisar e o Solis "esquece" justamente o que tinha.

Como funciona: cada memória e cada mensagem vira um vetor (embedding) — uma
lista de números em que textos de sentido parecido ficam perto. A mensagem nova
também vira vetor, e entram no pedido os guardados mais próximos dela, medidos
por similaridade de cosseno.

Tudo aqui falha pra trás: sem o modelo de embeddings, o Solis volta a mandar as
memórias mais recentes, como antes. Lembrar menos é melhor que não responder.
"""
import logging
import os

import numpy as np

from . import banco, ollama

log = logging.getLogger('solis.busca')

# nomic-embed-text: pequeno (274 MB), roda até na CPU, e já está instalado.
MODELO = os.environ.get('SOLIS_EMBEDDING', 'nomic-embed-text')

# O nomic foi treinado com esses prefixos; sem eles a busca piora.
DOCUMENTO = 'search_document: '
PERGUNTA = 'search_query: '

# Até aqui, todas as memórias vão — caber é barato e não perde nada.
TODAS_ATE = 30
# Acima disso: as mais parecidas com a mensagem, mais as mais recentes (o que
# acabou de ser dito costuma importar mesmo sem parecer com a pergunta).
MEMORIAS_PARECIDAS = 12
MEMORIAS_RECENTES = 5
# Trechos de conversas antigas, e só os que passam do piso de similaridade.
TRECHOS = 5
# PROVISÓRIO: piso escolhido no escuro. Precisa ser calibrado com dados reais
# no notebook — alto demais e nada antigo aparece; baixo demais e entra ruído.
PISO_TRECHO = 0.55
TRECHO_MAX = 400

LOTE = 64


def _bytes(vetor: list[float]) -> bytes:
    v = np.asarray(vetor, dtype=np.float32)
    # Normalizado na entrada: aí a similaridade de cosseno vira um produto
    # escalar só, e a busca é uma multiplicação de matriz.
    return (v / (np.linalg.norm(v) or 1.0)).tobytes()


def _matriz(pares: list[tuple[int, bytes]]) -> tuple[list[int], np.ndarray]:
    if not pares:
        return [], np.empty((0, 0), dtype=np.float32)
    return [r for r, _ in pares], np.stack([np.frombuffer(b, dtype=np.float32) for _, b in pares])


async def indexar_pendentes() -> int:
    """Vetoriza o que ainda não tem vetor. Roda depois de cada resposta; o que
    falhar fica pendente e entra na próxima. Devolve quantos indexou."""
    total = 0
    for tipo in ('memoria', 'mensagem'):
        while pendentes := banco.sem_vetor(tipo, LOTE):
            try:
                vetores = await ollama.embeddings(MODELO, [DOCUMENTO + p['texto'] for p in pendentes])
            except (ollama.OllamaIndisponivel, ollama.ModeloInexistente):
                log.info('embeddings indisponíveis; %s pendentes ficam pra depois', tipo)
                return total
            if len(vetores) != len(pendentes):
                # Resposta fora do combinado: sem isto o mesmo lote voltaria
                # pendente pra sempre.
                log.warning('embeddings: %d textos, %d vetores', len(pendentes), len(vetores))
                return total
            banco.guardar_vetores(tipo, [(p['id'], _bytes(v)) for p, v in zip(pendentes, vetores)])
            total += len(pendentes)
    return total


async def contexto(mensagem: str, conversa: int) -> tuple[list[dict], list[dict]]:
    """(memórias, trechos de conversas antigas) que vão no pedido desta mensagem."""
    todas = banco.memorias()
    try:
        [consulta] = await ollama.embeddings(MODELO, [PERGUNTA + mensagem])
    except (ollama.OllamaIndisponivel, ollama.ModeloInexistente):
        return todas[: TODAS_ATE + MEMORIAS_RECENTES], []
    q = np.frombuffer(_bytes(consulta), dtype=np.float32)

    if len(todas) <= TODAS_ATE:
        memorias = todas
    else:
        ids, m = _matriz(banco.vetores('memoria'))
        parecidas = [ids[i] for i in np.argsort(m @ q)[::-1][:MEMORIAS_PARECIDAS]] if ids else []
        escolhidas = set(parecidas) | {x['id'] for x in todas[:MEMORIAS_RECENTES]}
        memorias = [x for x in todas if x['id'] in escolhidas]

    ids, m = _matriz(banco.vetores('mensagem'))
    trechos = []
    if ids:
        sims = m @ q
        candidatos = [(ids[i], float(sims[i])) for i in np.argsort(sims)[::-1] if sims[i] >= PISO_TRECHO]
        por_id = {x['id']: x for x in banco.mensagens_por_id([i for i, _ in candidatos[: TRECHOS * 4]])}
        for ref, _ in candidatos:
            # A conversa aberta já vai inteira no histórico; repetir é desperdício.
            msg = por_id.get(ref)
            if msg and msg['conversa'] != conversa:
                trechos.append({**msg, 'texto': msg['texto'][:TRECHO_MAX]})
            if len(trechos) == TRECHOS:
                break
    return memorias, trechos
