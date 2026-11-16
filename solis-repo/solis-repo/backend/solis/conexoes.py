"""Conexões que ficam abertas com as APIs do caminho da voz (Groq e Fish).

Cada resposta abria uma conexão nova: DNS, TCP e TLS a cada pergunta. Medido
em 16/11/2026 daqui: a Groq em 0,24–0,46 s com conexão nova contra 0,20 s
reusada; a Fish em 0,29–0,64 s contra 0,17–0,35 s. Um cliente por API, que
guarda as conexões entre uma resposta e outra.

Na voz as perguntas vêm a minutos uma da outra, e o servidor do outro lado
fecha a conexão parada antes disso. Por isso aquecer(): quando a escuta ouve
"Solis", a conexão abre enquanto a pessoa ainda fala o pedido.

O cliente é do laço de eventos em que nasceu (o do servidor). Num laço novo
(os testes, um asyncio.run), nasce outro.
"""
import asyncio
import logging

import httpx

log = logging.getLogger('solis.conexoes')

# Quanto uma conexão parada fica guardada do nosso lado (o servidor pode fechar antes).
PARADA_S = 120.0

# Um pedido barato, sem chave e sem nada do Matheus, só pra abrir a conexão.
AQUECER = {
    'groq': 'https://api.groq.com/openai/v1/models',
    'fish': 'https://api.fish.audio/model?page_size=1',
}

_clientes: dict[str, tuple[asyncio.AbstractEventLoop, httpx.AsyncClient]] = {}
_aquecendo: set[asyncio.Task] = set()


def cliente(nome: str) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    atual = _clientes.get(nome)
    if atual and atual[0] is loop and not atual[1].is_closed:
        return atual[1]
    c = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=PARADA_S))
    _clientes[nome] = (loop, c)
    return c


async def _abrir(nome: str) -> None:
    try:
        await cliente(nome).get(AQUECER[nome], timeout=5.0)
    except httpx.HTTPError as e:
        log.info('a conexão com %s não aqueceu: %s', nome, type(e).__name__)


def aquecer(*nomes: str) -> None:
    """Abre (em segundo plano) a conexão com cada API, pra resposta não pagar o TLS."""
    for nome in nomes:
        if nome not in AQUECER:
            continue
        tarefa = asyncio.get_running_loop().create_task(_abrir(nome))
        _aquecendo.add(tarefa)
        tarefa.add_done_callback(_aquecendo.discard)
