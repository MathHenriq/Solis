"""Leitura do Ollama — o que está instalado, o que está carregado.

Só fala HTTP com o servidor do Ollama (padrão 127.0.0.1:11434). Não formata
nada pra tela: devolve bytes e números crus, e quem decide "4,7 GB" ou "128k"
é o front. Assim a mesma rota serve a tela de Modelos e, depois, a escolha de
modelo da Conversa.
"""
import asyncio
import os

import httpx

OLLAMA = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')

# ERROR_STATES.md §2 pede timeout de 8–10s antes de desistir do modelo local.
# A conexão em si falha rápido: se nada escuta na porta, não adianta esperar 8s
# pra dizer que o Ollama está fora do ar.
TIMEOUT = httpx.Timeout(8.0, connect=2.0)


class OllamaIndisponivel(Exception):
    """O Ollama não respondeu — desligado, porta errada ou travado."""


def _contexto(info: dict) -> int | None:
    # A chave é prefixada pela arquitetura ("llama.context_length",
    # "qwen2.context_length", "nomic-bert.context_length"), então procura pelo sufixo.
    for chave, valor in info.items():
        if chave.endswith('.context_length'):
            return int(valor)
    return None


def _embeddings(nome: str, detalhes: dict) -> bool:
    # Ollama recente declara `capabilities`; versões antigas não, e aí o nome é
    # o único sinal que sobra (nomic-embed-text, mxbai-embed-large...).
    capacidades = detalhes.get('capabilities')
    if capacidades is not None:
        return 'embedding' in capacidades
    return 'embed' in nome


async def listar_modelos(transporte: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    async with httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT, transport=transporte) as c:
        try:
            tags, ps = await asyncio.gather(c.get('/api/tags'), c.get('/api/ps'))
            tags.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaIndisponivel() from e

        modelos = tags.json().get('models', [])
        carregados = {m['name'] for m in ps.json().get('models', [])} if ps.is_success else set()

        # /api/show é por modelo; em paralelo, porque com 5 modelos em série a
        # tela esperaria 5 idas e voltas. Se um falhar, o modelo ainda aparece
        # — só sem contexto.
        async def mostrar(nome: str) -> dict:
            try:
                r = await c.post('/api/show', json={'model': nome})
                return r.json() if r.is_success else {}
            except httpx.HTTPError:
                return {}

        detalhes = await asyncio.gather(*(mostrar(m['name']) for m in modelos))

    return [
        {
            'nome': m['name'],
            'bytes': m.get('size', 0),
            'quantizacao': m.get('details', {}).get('quantization_level'),
            'contexto': _contexto(d.get('model_info', {})),
            # "Em uso" = carregado na memória agora (/api/ps). PROVISÓRIO: o
            # Ollama descarrega o modelo depois de ~5 min parado, e a etiqueta
            # some junto. Quando a Conversa escolher um modelo, "em uso" passa
            # a ser essa escolha, não o estado da memória.
            'emUso': m['name'] in carregados,
            'embeddings': _embeddings(m['name'], d),
        }
        for m, d in zip(modelos, detalhes)
    ]
