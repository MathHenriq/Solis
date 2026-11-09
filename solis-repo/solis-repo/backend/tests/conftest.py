import pytest

from solis import banco, cerebros, ocr, ollama


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
    for nome in ('embeddings', 'responder_json', 'responder_texto', 'instalados', 'ler_imagem'):
        monkeypatch.setattr(ollama, nome, indisponivel)


@pytest.fixture(autouse=True)
def sem_aviso_de_verdade(monkeypatch):
    """Nenhum teste põe notificação na tela do Matheus: o aviso "sai" numa lista."""
    from solis import avisos
    mostrados = []

    async def falso(titulo, texto, tag):
        mostrados.append({'titulo': titulo, 'texto': texto, 'tag': tag})
        return True
    monkeypatch.setattr(avisos, 'mostrar', falso)
    return mostrados


@pytest.fixture(autouse=True)
def sem_ocr_de_verdade(monkeypatch):
    """O OCR do Windows sobe um PowerShell: só o teste dele, marcado, o chama."""
    async def sem(png):
        raise ocr.SemLeitor('teste')
    monkeypatch.setattr(ocr, 'windows', sem)
    monkeypatch.setattr(ocr, 'parado', None)


@pytest.fixture(autouse=True)
def sem_cli_de_verdade(monkeypatch):
    """Nenhum teste chama o Claude Code ou o Codex de verdade — gastaria a cota
    do Matheus e dependeria de login. Por padrão nenhum CLI está "instalado";
    os testes do roteador trocam os executores por falsos."""
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: False)
    monkeypatch.setattr(cerebros, '_fora_ate', {})
    monkeypatch.setattr(cerebros, '_motivo_pausa', {})
