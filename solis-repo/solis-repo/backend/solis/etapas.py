"""O que o Solis está fazendo, etapa por etapa, com o tempo de cada uma.

Uma resposta passa por várias etapas que a tela não via: a busca na memória, a
escolha do cérebro, o CLI subindo, a primeira palavra, a queda pro próximo
cérebro quando um falha, e depois da resposta o aprendizado e o resumo. Cada
etapa vira um evento com o tempo desde o começo do pedido (`t`, em segundos),
que vai pra tela pelo stream da resposta e pro log do servidor — é o log que
flagra a próxima demora.

O stream é NDJSON, um objeto por linha:

    {"etapa": "memoria", "t": 0.12, "memorias": 8, "trechos": 2}
    {"etapa": "cerebro", "t": 0.12, "cerebro": "claude"}
    {"texto": "Olá"}
    {"etapa": "fim", "t": 3.4, "cerebro": "claude"}
    {"erro": "ollama_indisponivel", "t": 0.3}
"""
import asyncio
import logging
import time

log = logging.getLogger('solis.etapas')


class Etapas:
    def __init__(self, conversa: int):
        self.conversa = conversa
        self.inicio = time.perf_counter()
        self.fila: asyncio.Queue[dict | None] = asyncio.Queue()
        # As etapas e o erro, sem o texto: é o que vai pro banco com a resposta.
        self.lista: list[dict] = []

    def _t(self) -> float:
        return round(time.perf_counter() - self.inicio, 2)

    def marcar(self, etapa: str, **dados) -> None:
        evento = {'etapa': etapa, 't': self._t(), **dados}
        detalhes = ' '.join(f'{k}={v}' for k, v in dados.items())
        log.info('conversa %s  %6.2fs  %s %s', self.conversa, evento['t'], etapa, detalhes)
        self.lista.append(evento)
        self.fila.put_nowait(evento)

    def texto(self, pedaco: str) -> None:
        self.fila.put_nowait({'texto': pedaco})

    def erro(self, erro: str, **dados) -> None:
        evento = {'erro': erro, 't': self._t(), **dados}
        log.warning('conversa %s  %6.2fs  erro %s %s', self.conversa, evento['t'], erro, dados)
        self.lista.append(evento)
        self.fila.put_nowait(evento)

    def encerrar(self) -> None:
        # Uma linha só com a resposta inteira: é a que se lê pra achar a demora.
        vistas = (f'{e.get("etapa") or "erro"} {e["t"]:.2f}s' for e in self.lista)
        log.info('conversa %s  resumo: %s', self.conversa, ' · '.join(vistas))
        self.fila.put_nowait(None)

    async def eventos(self):
        while (evento := await self.fila.get()) is not None:
            yield evento


class _Muda:
    """Pra quem chama um cérebro fora de uma conversa (testes, importação)."""

    def marcar(self, etapa: str, **dados) -> None:
        pass


MUDA = _Muda()
