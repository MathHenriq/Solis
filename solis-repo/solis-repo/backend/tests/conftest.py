import pytest

from solis import banco, ollama


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path):
    """Cada teste num SQLite próprio — nunca no banco de verdade do usuário."""
    banco.usar(tmp_path / 'solis.db')


@pytest.fixture(autouse=True)
def sem_ollama_de_verdade(monkeypatch):
    """Nenhum teste sai pra rede atrás do Ollama. Por padrão as chamadas de fundo
    (embeddings, extração, resumo) dão "indisponível" — que é também o caminho de
    queda que precisa funcionar. Cada teste troca a que precisar por uma falsa."""
    async def indisponivel(*_, **__):
        raise ollama.OllamaIndisponivel()
    for nome in ('embeddings', 'responder_json', 'responder_texto'):
        monkeypatch.setattr(ollama, nome, indisponivel)
