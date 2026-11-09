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
import asyncio
import logging
import os

import numpy as np

from . import banco, ollama

log = logging.getLogger('solis.busca')

# O modelo de embeddings, escolhido medindo (09/11/2026, ver docs/ESCOPO.md →
# Conhecimento): 10 perguntas em português contra páginas reais em inglês e
# textos em português, mais 5 sem relação nenhuma.
#
#   modelo                 fonte certa  menor certo  maior ruído  folga
#   nomic-embed-text       7/10         0,54         0,65         −0,10
#   qwen3-embedding:0.6b   10/10        0,38         0,42         −0,03  (11× mais lento)
#   bge-m3                 9/10         0,48         0,56         −0,09
#   embeddinggemma         10/10        0,45         0,29         +0,16
#
# O nomic quase não liga português com inglês: "como rodo uma tarefa depois de
# devolver a resposta no FastAPI?" dava 0,57 na página certa, nota de ruído. O
# embeddinggemma (621 MB, roda na CPU) é o único em que um piso separa o que
# importa do que não importa. Cada modelo tem os prefixos com que foi treinado
# — sem eles a busca piora — e o seu piso, que é medido, não adivinhado.
MODELOS = {
    'embeddinggemma': {
        'pergunta': 'task: search result | query: ',
        'documento': 'title: none | text: ',
        # No meio da folga medida (0,29 a 0,45). PROVISÓRIO: calibrar com os
        # arquivos e as conversas de verdade.
        'piso': 0.37,
    },
    'nomic-embed-text': {
        'pergunta': 'search_query: ',
        'documento': 'search_document: ',
        'piso_trecho': 0.55,
        'piso': 0.65,  # medido em 08/11 (0,56–0,60 ruído, 0,68–0,82 certo)
    },
}
MODELO = os.environ.get('SOLIS_EMBEDDING', 'embeddinggemma')
_CONF = MODELOS.get(MODELO.split(':')[0], {})
DOCUMENTO = _CONF.get('documento', '')
PERGUNTA = _CONF.get('pergunta', '')

# Até aqui, todas as memórias vão — caber é barato e não perde nada.
TODAS_ATE = 30
# Acima disso: as mais parecidas com a mensagem, mais as mais recentes (o que
# acabou de ser dito costuma importar mesmo sem parecer com a pergunta).
MEMORIAS_PARECIDAS = 12
MEMORIAS_RECENTES = 5
# Trechos de conversas antigas, e só os que passam do piso de similaridade.
# Alto demais e nada antigo aparece; baixo demais e entra ruído.
TRECHOS = 5
PISO_TRECHO = _CONF.get('piso_trecho', _CONF.get('piso', 0.5))
TRECHO_MAX = 400
# Trechos dos arquivos do Conhecimento. Um trecho de arquivo tem ~200 palavras
# (conhecimento.PALAVRAS), então vai inteiro.
ARQUIVOS = 4
PISO_ARQUIVO = _CONF.get('piso', 0.5)

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


def conferir_modelo() -> None:
    """Vetores de modelos diferentes não se comparam (nem o tamanho bate: 768
    no gemma, 1024 em outros). Se os guardados não são do MODELO de agora, saem
    todos e são refeitos pelo indexar_pendentes — o texto fica, só o vetor é
    refeito. Banco de antes desta marca: os vetores eram do nomic."""
    if banco.ajuste('modelo_vetores') == MODELO:
        return
    if banco.tem_vetores():
        log.warning('vetores feitos por outro modelo; refazendo todos com %s', MODELO)
        banco.apagar_vetores()
    banco.guardar_ajuste('modelo_vetores', MODELO)


async def indexar_pendentes() -> int:
    """Vetoriza o que ainda não tem vetor. Roda depois de cada resposta; o que
    falhar fica pendente e entra na próxima. Devolve quantos indexou."""
    conferir_modelo()
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
    # Os trechos dos arquivos por último: um PDF grande são centenas, e a
    # memória do que acabou de ser dito não pode esperar por eles.
    while pendentes := banco.trechos_sem_vetor(LOTE):
        try:
            vetores = await ollama.embeddings(MODELO, [DOCUMENTO + p['texto'] for p in pendentes])
        except (ollama.OllamaIndisponivel, ollama.ModeloInexistente):
            log.info('embeddings indisponíveis; trechos de arquivo ficam pra depois')
            return total
        if len(vetores) != len(pendentes):
            log.warning('embeddings: %d trechos, %d vetores', len(pendentes), len(vetores))
            return total
        banco.guardar_vetores_trechos([(p['id'], _bytes(v)) for p, v in zip(pendentes, vetores)])
        total += len(pendentes)
    return total


_indexando = asyncio.Lock()


async def indexar_se_livre() -> int:
    """indexar_pendentes, a menos que uma já esteja rodando — essa pega o que
    falta, porque volta a perguntar o banco a cada lote. É o que as tarefas de
    fundo chamam: a tela do Conhecimento pede a cada 1,5 s enquanto falta
    trecho, e sem a trava cada pedido abriria mais uma indexação."""
    if _indexando.locked():
        return 0
    async with _indexando:
        return await indexar_pendentes()


async def _consulta(texto: str) -> np.ndarray | None:
    # Toda busca passa aqui: nunca comparar a pergunta com vetores de outro modelo.
    conferir_modelo()
    try:
        [v] = await ollama.embeddings(MODELO, [PERGUNTA + texto])
    except (ollama.OllamaIndisponivel, ollama.ModeloInexistente):
        return None
    return np.frombuffer(_bytes(v), dtype=np.float32)


def _ordenar(q: np.ndarray, ativas: list[dict]) -> list[dict]:
    """As memórias que valem, da mais parecida com `q` pra menos. As
    substituídas ainda têm vetor no banco, mas não entram."""
    por_id = {m['id']: m for m in ativas}
    ids, m = _matriz([(r, b) for r, b in banco.vetores('memoria') if r in por_id])
    if not ids:
        return []
    return [por_id[ids[i]] for i in np.argsort(m @ q)[::-1]]


async def memorias_parecidas(texto: str, quantas: int) -> list[dict]:
    """As `quantas` memórias mais ligadas a `texto` — pra o extrator saber o que
    já existe sobre o assunto e poder dizer o que mudou. Sem embeddings, as
    mais recentes."""
    ativas = banco.memorias()
    q = await _consulta(texto)
    if q is None:
        return ativas[:quantas]
    ordenadas = _ordenar(q, ativas)
    # Memória que ainda não foi vetorizada (acabou de nascer) entra pela data.
    vistas = {m['id'] for m in ordenadas}
    return (ordenadas + [m for m in ativas if m['id'] not in vistas])[:quantas]


async def contexto(mensagem: str, conversa: int, desde: int = 0) -> tuple[list[dict], list[dict]]:
    """(memórias, trechos) que vão no pedido desta mensagem. Os trechos são de
    conversas antigas e, marcados com `arquivo`, dos arquivos do Conhecimento —
    numa lista só porque o caminho deles é o mesmo, inclusive o filtro do que é
    privado antes da nuvem (`privada`).

    Da conversa aberta, só ficam de fora as mensagens depois de `desde` — essas
    já vão inteiras no histórico. As de antes viraram resumo, e um trecho exato
    delas ainda pode ser o que a pergunta precisa."""
    todas = banco.memorias()
    q = await _consulta(mensagem)
    if q is None:
        return todas[: TODAS_ATE + MEMORIAS_RECENTES], []

    if len(todas) <= TODAS_ATE:
        memorias = todas
    else:
        escolhidas = {x['id'] for x in _ordenar(q, todas)[:MEMORIAS_PARECIDAS]}
        escolhidas |= {x['id'] for x in todas[:MEMORIAS_RECENTES]}
        memorias = [x for x in todas if x['id'] in escolhidas]

    ids, m = _matriz(banco.vetores('mensagem'))
    trechos = []
    if ids:
        sims = m @ q
        candidatos = [(ids[i], float(sims[i])) for i in np.argsort(sims)[::-1] if sims[i] >= PISO_TRECHO]
        por_id = {x['id']: x for x in banco.mensagens_por_id([i for i, _ in candidatos[: TRECHOS * 4]])}
        for ref, _ in candidatos:
            msg = por_id.get(ref)
            if msg and not (msg['conversa'] == conversa and msg['id'] > desde):
                trechos.append({**msg, 'texto': msg['texto'][:TRECHO_MAX]})
            if len(trechos) == TRECHOS:
                break
    return memorias, trechos + _arquivos(q)


def _arquivos(q: np.ndarray) -> list[dict]:
    ids, m = _matriz(banco.vetores_trechos())
    if not ids:
        return []
    sims = m @ q
    melhores = [ids[i] for i in np.argsort(sims)[::-1][:ARQUIVOS] if sims[i] >= PISO_ARQUIVO]
    por_id = {t['id']: t for t in banco.trechos_por_id(melhores)}
    return [
        {
            'arquivo': True,
            'id': t['id'],
            'documento': t['documento'],
            'nome': t['nome'],
            'pagina': t['pagina'],
            'url': t['url'],
            'texto': t['texto'],
            'privada': t['privado'],
        }
        for t in (por_id[i] for i in melhores if i in por_id)
    ]
