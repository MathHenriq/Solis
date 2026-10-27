import pytest

from solis import banco, ollama


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path):
    """Cada teste num SQLite próprio — nunca no banco de verdade do usuário."""
    banco.usar(tmp_path / 'solis.db')


@pytest.fixture(autouse=True)
def sem_embeddings_de_verdade(monkeypatch):
    """Nenhum teste sai pra rede atrás de embeddings. Por padrão eles estão
    "indisponíveis" — que é também o caminho de queda que precisa funcionar.
    Os testes de busca trocam isto por vetores falsos."""
    async def indisponivel(*_, **__):
        raise ollama.OllamaIndisponivel()
    monkeypatch.setattr(ollama, 'embeddings', indisponivel)
