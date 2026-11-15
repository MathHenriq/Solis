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
def skills_numa_casa_de_mentira(monkeypatch, tmp_path):
    """Nenhum teste escreve nas skills do Matheus (~/.claude e ~/.codex)."""
    from solis import skills
    casa = tmp_path / 'casa'
    monkeypatch.setattr(skills, '_casa', lambda: casa)
    return casa


@pytest.fixture(autouse=True)
def mcp_de_mentira(monkeypatch, tmp_path):
    """Nenhum teste mexe nos servidores MCP do Matheus: os CLIs (claude mcp,
    codex mcp) viram falsos que escrevem num ~/.claude.json temporário e numa
    lista do Codex em memória. Devolve as chamadas e a lista do Codex."""
    import json as _json
    from solis import servidores_mcp
    casa = tmp_path / 'casa-mcp'
    casa.mkdir()
    monkeypatch.setattr(servidores_mcp, '_casa', lambda: casa)
    estado = {'chamadas': [], 'codex': []}

    def rodar(cli, *args, timeout=60):
        estado['chamadas'].append((cli, *args))
        arquivo = casa / '.claude.json'
        if cli == 'claude':
            dados = _json.loads(arquivo.read_text()) if arquivo.exists() else {}
            servidores = dados.setdefault('mcpServers', {})
            if args[:2] == ('mcp', 'add-json'):
                servidores[args[4]] = _json.loads(args[5])
            elif args[:2] == ('mcp', 'remove'):
                servidores.pop(args[4])
            arquivo.write_text(_json.dumps(dados))
            return ''
        if args[:2] == ('mcp', 'list'):
            return _json.dumps(estado['codex'])
        if args[:2] == ('mcp', 'add'):
            nome, resto = args[2], list(args[3:])
            if resto[0] == '--url':
                t = {'type': 'streamable_http', 'url': resto[1]}
            else:
                env = {}
                while resto[0] == '--env':
                    k, _, v = resto[1].partition('=')
                    env[k] = v
                    resto = resto[2:]
                t = {'type': 'stdio', 'command': resto[1], 'args': resto[2:], 'env': env}
            estado['codex'].append({'name': nome, 'enabled': True, 'transport': t})
            return ''
        if args[:2] == ('mcp', 'remove'):
            estado['codex'] = [x for x in estado['codex'] if x['name'] != args[2]]
            return ''
        raise AssertionError(args)
    monkeypatch.setattr(servidores_mcp, '_rodar', rodar)
    return estado


@pytest.fixture(autouse=True)
def sem_navegador_de_verdade(monkeypatch):
    """Nenhum teste abre o Chrome do Matheus: o servidor do navegador "não sobe"."""
    from solis import navegador
    monkeypatch.setattr(navegador, 'servidor', lambda: None)
    monkeypatch.setattr(navegador, 'segurar', lambda: None)


@pytest.fixture(autouse=True)
def sem_cli_de_verdade(monkeypatch):
    """Nenhum teste chama o Claude Code ou o Codex de verdade — gastaria a cota
    do Matheus e dependeria de login. Por padrão nenhum CLI está "instalado";
    os testes do roteador trocam os executores por falsos."""
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: False)
    monkeypatch.setattr(cerebros, '_fora_ate', {})
    monkeypatch.setattr(cerebros, '_motivo_pausa', {})
