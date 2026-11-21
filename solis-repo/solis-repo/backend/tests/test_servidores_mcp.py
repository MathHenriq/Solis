"""Servidores MCP configuráveis (docs/PARIDADE.md): cada um pra Claude, GPT ou
os dois, escritos pelos próprios CLIs; ler é livre, mudar pede (no Claude, o
cartão; no GPT, não roda)."""
import asyncio
import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from solis import agente, banco, cofre, lancar_mcp, main, servidores_mcp


def test_partes_do_comando():
    assert servidores_mcp._partes('npx -y @scope/srv "C:\\Minha Pasta"') == ['npx', '-y', '@scope/srv', 'C:\\Minha Pasta']
    with pytest.raises(servidores_mcp.ServidorInvalido):
        servidores_mcp._partes('npx "aberta')


def test_adicionar_pros_dois_e_ler(mcp_de_mentira):
    s = servidores_mcp.salvar('notion', 'comando', 'npx -y @notion/mcp', '', 'NOTION_TOKEN=abc\n\nOUTRA=1',
                              ['claude', 'codex'])
    assert s['para'] == ['claude', 'codex'] and s['comando'] == 'npx -y @notion/mcp'
    assert s['variaveis'] == ['NOTION_TOKEN', 'OUTRA'] and s['editavel'] and s['origem'] == 'seu'
    assert s['no_cofre']
    # As chaves no cofre; nos CLIs, o lançador do Solis com o comando de verdade.
    config = json.loads((servidores_mcp._casa() / '.claude.json').read_text())['mcpServers']['notion']
    assert config['command'] == servidores_mcp._python()
    assert config['args'] == ['-m', 'solis.lancar_mcp', 'notion', 'npx', '-y', '@notion/mcp']
    assert set(config['env']) == {'PYTHONPATH', 'SOLIS_BANCO'} and config['env']['SOLIS_BANCO'] == str(banco.arquivo())
    add_codex = next(c for c in mcp_de_mentira['chamadas'] if c[:3] == ('codex', 'mcp', 'add'))
    assert add_codex[-6:] == ('-m', 'solis.lancar_mcp', 'notion', 'npx', '-y', '@notion/mcp')
    assert 'abc' not in json.dumps([config, mcp_de_mentira['chamadas']])
    if cofre.DISPONIVEL:
        assert all(cofre.selado(v) for v in banco.ajuste('mcp_variaveis')['notion'].values())
        assert 'abc' not in json.dumps(banco.ajuste('mcp_variaveis'))
    assert servidores_mcp.ler('notion')['variaveis'] == 'NOTION_TOKEN=abc\nOUTRA=1'
    assert servidores_mcp.ler('notion')['comando'] == 'npx -y @notion/mcp'
    # Visto pelo Codex, o mesmo servidor.
    assert servidores_mcp._do_codex()['notion']['env'] == {'NOTION_TOKEN': 'abc', 'OUTRA': '1'}


def test_sem_chave_vai_direto_e_tirar_a_chave_limpa_o_cofre(mcp_de_mentira):
    servidores_mcp.salvar('srv', 'comando', 'npx srv', '', 'TOKEN=1', ['claude'])
    assert 'srv' in banco.ajuste('mcp_variaveis')
    s = servidores_mcp.salvar('srv', 'comando', 'npx srv', '', '', ['claude'], antigo='srv')
    config = json.loads((servidores_mcp._casa() / '.claude.json').read_text())['mcpServers']['srv']
    assert config == {'type': 'stdio', 'command': 'npx', 'args': ['srv'], 'env': {}} and not s['no_cofre']
    assert 'srv' not in banco.ajuste('mcp_variaveis')
    servidores_mcp.salvar('srv', 'comando', 'npx srv', '', 'TOKEN=2', ['claude'], antigo='srv')
    assert servidores_mcp.remover('srv') and 'srv' not in banco.ajuste('mcp_variaveis')


def test_os_de_antes_em_texto_aberto_continuam_lidos(mcp_de_mentira):
    (servidores_mcp._casa() / '.claude.json').write_text(json.dumps({'mcpServers': {
        'velho': {'type': 'stdio', 'command': 'npx', 'args': ['srv'], 'env': {'TOKEN': 'x'}}}}))
    s = servidores_mcp.listar()[0]
    assert (s['comando'], s['variaveis'], s['no_cofre']) == ('npx srv', ['TOKEN'], False)
    # Salvo de novo pela tela, a chave sai do arquivo e vai pro cofre.
    servidores_mcp.salvar('velho', 'comando', 'npx srv', '', 'TOKEN=x', ['claude'], antigo='velho')
    assert '"x"' not in (servidores_mcp._casa() / '.claude.json').read_text()


def test_o_lancador_liga_o_servidor_com_as_chaves(mcp_de_mentira):
    servidores_mcp.salvar('eco', 'comando', 'x', '', 'TOKEN=segredo', ['claude'])
    config = json.loads((servidores_mcp._casa() / '.claude.json').read_text())['mcpServers']['eco']
    # O "servidor": lê uma linha da entrada e responde com ela e a chave (a entrada e a saída passam direto).
    filho = ('import os,sys; l=sys.stdin.readline().strip(); '
             'print(l, os.environ["TOKEN"], "SOLIS_BANCO" in os.environ, "PYTHONPATH" in os.environ)')
    args = config['args'][:3] + [sys.executable, '-c', filho]
    r = subprocess.run([config['command'], *args], input='oi\n', capture_output=True, text=True, timeout=30,
                       env={**os.environ, **config['env']})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ['oi', 'segredo', 'False', 'False']
    # Sem as chaves no cofre: não liga, e diz por quê.
    servidores_mcp._guardar_variaveis('eco', {})
    r = subprocess.run([config['command'], *args], input='', capture_output=True, text=True, timeout=30,
                       env={**os.environ, **config['env']})
    assert r.returncode == 1 and 'não tem as variáveis' in r.stderr


def test_chave_que_nao_abre(mcp_de_mentira, monkeypatch):
    servidores_mcp.salvar('srv', 'comando', 'npx srv', '', 'TOKEN=1', ['claude'])
    monkeypatch.setattr(lancar_mcp, 'variaveis', lambda nome: {'TOKEN': cofre.ILEGIVEL})
    assert 'não abrem' in lancar_mcp.ambiente('srv', {})
    monkeypatch.setattr(servidores_mcp, '_do_cofre', lambda nome: {'TOKEN': cofre.ILEGIVEL})
    assert 'não abrem' in asyncio.run(servidores_mcp.conferir('srv'))['erro']


def test_mudar_pra_so_um_e_renomear(mcp_de_mentira):
    servidores_mcp.salvar('docs', 'endereco', '', 'https://exemplo.com/mcp', '', ['claude', 'codex'])
    s = servidores_mcp.salvar('docs2', 'endereco', '', 'https://exemplo.com/mcp', '', ['codex'], antigo='docs')
    assert s['para'] == ['codex'] and s['url'] == 'https://exemplo.com/mcp'
    assert [x['nome'] for x in servidores_mcp.listar()] == ['docs2']
    assert servidores_mcp.remover('docs2') and servidores_mcp.listar() == []
    assert not servidores_mcp.remover('docs2')


def test_os_do_solis_e_os_do_codex_nao_se_mexem(mcp_de_mentira):
    (servidores_mcp._casa() / '.claude.json').write_text(json.dumps({'mcpServers': {
        'solis': {'type': 'stdio', 'command': 'python', 'args': ['-m', 'solis.servidor_mcp'], 'env': {}}}}))
    mcp_de_mentira['codex'].append({'name': 'node_repl', 'enabled': True, 'transport': {
        'type': 'stdio', 'command': 'C:\\Users\\M\\AppData\\Local\\OpenAI\\Codex\\runtimes\\node_repl.exe', 'args': []}})
    origens = {s['nome']: (s['origem'], s['editavel']) for s in servidores_mcp.listar()}
    assert origens == {'solis': ('solis', False), 'node_repl': ('codex', False)}
    assert servidores_mcp.ler('solis') is None and not servidores_mcp.remover('node_repl')
    with pytest.raises(servidores_mcp.ServidorInvalido, match='nome'):
        servidores_mcp.salvar('solis', 'comando', 'x', '', '', ['claude'])


@pytest.mark.parametrize('args, motivo', [
    (('com espaço', 'comando', 'x', '', '', ['claude']), 'nome'),
    (('a', 'outro', 'x', '', '', ['claude']), 'tipo'),
    (('a', 'comando', '  ', '', '', ['claude']), 'comando'),
    (('a', 'endereco', '', 'ftp://x', '', ['claude']), 'endereço'),
    (('a', 'comando', 'x', '', 'SEM IGUAL', ['claude']), 'variáveis'),
    (('a', 'comando', 'x', '', '', []), 'pra quem'),
])
def test_recusa(args, motivo):
    with pytest.raises(servidores_mcp.ServidorInvalido, match=motivo):
        servidores_mcp.salvar(*args)


def test_nao_duplica(mcp_de_mentira):
    servidores_mcp.salvar('a', 'comando', 'x', '', '', ['claude'])
    with pytest.raises(servidores_mcp.ServidorInvalido, match='já existe'):
        servidores_mcp.salvar('a', 'comando', 'y', '', '', ['codex'])


def test_conferir_e_o_que_o_gpt_pode(mcp_de_mentira, monkeypatch):
    servidores_mcp.salvar('notion', 'comando', 'npx srv', '', '', ['claude', 'codex'])
    servidores_mcp.salvar('so-claude', 'comando', 'npx srv2', '', '', ['claude'])

    async def ferramentas(c):
        return [{'nome': 'search', 'so_le': True}, {'nome': 'create_page', 'so_le': False}]
    monkeypatch.setattr(servidores_mcp, '_listar_ferramentas', ferramentas)
    r = asyncio.run(servidores_mcp.conferir('notion'))
    assert (r['total'], r['so_leem'], r['erro'], r['no_codex']) == (2, 1, None, True)
    asyncio.run(servidores_mcp.conferir('so-claude'))
    # Só o que lê, e só de servidor que está no Codex.
    assert servidores_mcp.liberadas_no_codex() == ['-c', 'mcp_servers.notion.tools.search.approval_mode=approve']
    assert servidores_mcp.listar()[0]['ferramentas']['total'] == 2

    async def caiu(c):
        raise OSError('npx não encontrado')
    monkeypatch.setattr(servidores_mcp, '_listar_ferramentas', caiu)
    assert asyncio.run(servidores_mcp.conferir('notion'))['erro'] == 'npx não encontrado'


def test_no_claude_servidor_seu_conta_como_conector():
    assert agente.conector_de('mcp__notion__search') == ('notion', 'search')
    assert agente.conector_de('mcp__solis__hora') is None and agente.conector_de('mcp__navegador__browser_click') is None
    pytest.importorskip('claude_agent_sdk')
    mandados = []

    def por(tipo, valor=None):
        mandados.append((tipo, valor))
        if tipo == 'etapa' and valor[0] == 'aprovacao':
            asyncio.get_running_loop().call_soon(agente.responder_aprovacao, valor[1]['id'], False)
    # Só lê: livre. Muda: cartão com o que vai ser mandado.
    assert asyncio.run(agente._decidir('mcp__notion__search', {'q': 'x'}, por, so_le=True)).behavior == 'allow'
    asyncio.run(agente._decidir('mcp__notion__create_page', {'titulo': 'Oi'}, por))
    cartao = mandados[0][1][1]
    assert cartao['resumo'] == 'Usar o notion: create_page' and '"titulo": "Oi"' in cartao['entrada']


def test_rotas(mcp_de_mentira, monkeypatch):
    cli = TestClient(main.app)
    r = cli.post('/mcp', json={'nome': 'notion', 'tipo': 'comando', 'comando': 'npx -y @notion/mcp',
                               'variaveis': 'TOKEN=segredo', 'para': ['claude']})
    assert r.json()['para'] == ['claude']
    assert 'segredo' not in json.dumps(banco.acoes(), ensure_ascii=False) and banco.acoes()
    assert cli.get('/mcp/notion').json()['variaveis'] == 'TOKEN=segredo'
    assert cli.get('/mcp/nada').status_code == 404
    r = cli.post('/mcp', json={'nome': 'x y', 'tipo': 'comando', 'comando': 'a', 'para': ['claude']})
    assert r.status_code == 400 and r.json()['motivo'] == 'nome'
    assert cli.put('/mcp/notion', json={'nome': 'notion', 'tipo': 'endereco', 'url': 'https://n.com/mcp',
                                        'para': ['claude', 'codex']}).json()['para'] == ['claude', 'codex']

    async def ferramentas(c):
        return [{'nome': 'search', 'so_le': True}]
    monkeypatch.setattr(servidores_mcp, '_listar_ferramentas', ferramentas)
    assert cli.post('/mcp/notion/conferir').json()['total'] == 1
    assert cli.post('/mcp/nada/conferir').status_code == 404
    assert [s['nome'] for s in cli.get('/mcp').json()['servidores']] == ['notion']
    assert cli.delete('/mcp/notion').json() == {'ok': True}
    assert cli.delete('/mcp/notion').status_code == 404


# — servidor por endereço com chave (cabeçalhos), 20/11/2026 ——————————————————
def test_cabecalhos_vao_pro_cofre_e_cada_cli_pega_do_seu_jeito(mcp_de_mentira):
    s = servidores_mcp.salvar('gh', 'endereco', '', 'https://api.exemplo.com/mcp', 'Authorization=Bearer abc',
                              ['claude', 'codex'])
    assert s['no_cofre'] and s['para'] == ['claude', 'codex']
    config = json.loads((servidores_mcp._casa() / '.claude.json').read_text())['mcpServers']['gh']
    # No Claude Code: o ajudante que tira a chave do cofre ao conectar.
    assert config['type'] == 'http' and servidores_mcp.CABECALHOS.name in config['headersHelper']
    add = next(c for c in mcp_de_mentira['chamadas'] if c[:3] == ('codex', 'mcp', 'add'))
    assert add[-2:] == ('--bearer-token-env-var', 'SOLIS_MCP_GH_TOKEN')
    assert 'abc' not in json.dumps([config, mcp_de_mentira['chamadas']])
    # O Codex que o Solis liga recebe o token na variável; a tela lê de volta.
    assert servidores_mcp.ambiente_do_codex() == {'SOLIS_MCP_GH_TOKEN': 'abc'}
    assert servidores_mcp.ler('gh')['variaveis'] == 'Authorization=Bearer abc'
    assert servidores_mcp._do_codex()['gh']['env'] == {'Authorization': 'Bearer abc'}
    # Tirar a chave limpa o cofre e volta ao endereço puro.
    servidores_mcp.salvar('gh', 'endereco', '', 'https://api.exemplo.com/mcp', '', ['claude'], antigo='gh')
    config = json.loads((servidores_mcp._casa() / '.claude.json').read_text())['mcpServers']['gh']
    assert 'headersHelper' not in config and 'gh' not in (banco.ajuste('mcp_variaveis') or {})


def test_cabecalhos_lidos_e_recusados():
    assert servidores_mcp._cabecalhos('X-API-Key: k1\n\nAuthorization=Bearer a=b') == {
        'X-API-Key': 'k1', 'Authorization': 'Bearer a=b'}
    for ruim in ('sem separador', 'Nome com espaço=1', 'Vazio='):
        with pytest.raises(servidores_mcp.ServidorInvalido, match='cabeçalhos'):
            servidores_mcp._cabecalhos(ruim)
    # O Codex só sabe a chave como Bearer: outro cabeçalho, só pro Claude.
    with pytest.raises(servidores_mcp.ServidorInvalido, match='no Codex'):
        servidores_mcp.salvar('k', 'endereco', '', 'https://x.com/mcp', 'X-API-Key=1', ['codex'])
    assert servidores_mcp.variavel_do_codex('meu-servidor.2') == 'SOLIS_MCP_MEU_SERVIDOR_2_TOKEN'


def test_o_ajudante_do_claude_code_imprime_os_cabecalhos(mcp_de_mentira):
    servidores_mcp.salvar('gh', 'endereco', '', 'https://x.com/mcp', 'X-API-Key=k1', ['claude'])
    config = json.loads((servidores_mcp._casa() / '.claude.json').read_text())['mcpServers']['gh']
    # Roda a linha num shell, como o Claude Code, com o banco dos testes.
    r = subprocess.run(config['headersHelper'], shell=True, capture_output=True, text=True, timeout=30,
                       env={**os.environ, 'SOLIS_BANCO': str(banco.arquivo())})
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {'X-API-Key': 'k1'}
    servidores_mcp._guardar_variaveis('gh', {})
    r = subprocess.run(config['headersHelper'], shell=True, capture_output=True, text=True, timeout=30,
                       env={**os.environ, 'SOLIS_BANCO': str(banco.arquivo())})
    assert r.returncode == 1 and 'não tem a chave nem o login' in r.stderr


def test_o_solis_conecta_com_a_chave_num_servidor_de_verdade(mcp_de_mentira):
    import socket
    import threading
    import time as _time

    import uvicorn
    from mcp.server.mcpserver import MCPServer
    from starlette.responses import PlainTextResponse

    srv = MCPServer('com-chave')

    @srv.tool()
    def eco(texto: str) -> str:
        return texto

    app = srv.streamable_http_app()

    async def porteiro(scope, receive, send):
        chave = dict(scope['headers']).get(b'authorization', b'') if scope['type'] == 'http' else b'Bearer certa'
        if chave.startswith(b'Basic'):
            # Como o GitHub com a chave errada: 400 e o motivo em texto.
            await PlainTextResponse('bad request: Authorization header is badly formatted',
                                    status_code=400)(scope, receive, send)
            return
        if chave != b'Bearer certa':
            await PlainTextResponse('sem chave', status_code=401)(scope, receive, send)
            return
        await app(scope, receive, send)

    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        porta = s.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(porteiro, host='127.0.0.1', port=porta, log_level='error',
                                             lifespan='on'))
    fio = threading.Thread(target=servidor.run, daemon=True)
    fio.start()
    try:
        while not servidor.started:
            _time.sleep(0.05)
        url = f'http://127.0.0.1:{porta}/mcp'
        servidores_mcp.salvar('certo', 'endereco', '', url, 'Authorization=Bearer certa', ['claude'])
        servidores_mcp.salvar('errado', 'endereco', '', url, 'Authorization=Bearer outra', ['claude'])
        servidores_mcp.salvar('sem', 'endereco', '', url, '', ['claude'])
        servidores_mcp.salvar('mal', 'endereco', '', url, 'Authorization=Basic x', ['claude'])
        assert asyncio.run(servidores_mcp.conferir('mal'))['erro'] == (
            'o servidor respondeu 400: bad request: Authorization header is badly formatted')
        assert asyncio.run(servidores_mcp.conferir('certo'))['total'] == 1
        assert asyncio.run(servidores_mcp.conferir('errado'))['erro'] == (
            'o servidor recusou a chave (401): confira os cabeçalhos')
        assert asyncio.run(servidores_mcp.conferir('sem'))['erro'] == (
            'o servidor pede login ou chave (401): use "Entrar", ou ponha a chave nos cabeçalhos')

    finally:
        servidor.should_exit = True
        fio.join(10)
