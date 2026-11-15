"""Servidores MCP configuráveis (docs/PARIDADE.md): cada um pra Claude, GPT ou
os dois, escritos pelos próprios CLIs; ler é livre, mudar pede (no Claude, o
cartão; no GPT, não roda)."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from solis import agente, banco, main, servidores_mcp


def test_partes_do_comando():
    assert servidores_mcp._partes('npx -y @scope/srv "C:\\Minha Pasta"') == ['npx', '-y', '@scope/srv', 'C:\\Minha Pasta']
    with pytest.raises(servidores_mcp.ServidorInvalido):
        servidores_mcp._partes('npx "aberta')


def test_adicionar_pros_dois_e_ler(mcp_de_mentira):
    s = servidores_mcp.salvar('notion', 'comando', 'npx -y @notion/mcp', '', 'NOTION_TOKEN=abc\n\nOUTRA=1',
                              ['claude', 'codex'])
    assert s['para'] == ['claude', 'codex'] and s['comando'] == 'npx -y @notion/mcp'
    assert s['variaveis'] == ['NOTION_TOKEN', 'OUTRA'] and s['editavel'] and s['origem'] == 'seu'
    config = json.loads((servidores_mcp._casa() / '.claude.json').read_text())['mcpServers']['notion']
    assert config == {'type': 'stdio', 'command': 'npx', 'args': ['-y', '@notion/mcp'],
                      'env': {'NOTION_TOKEN': 'abc', 'OUTRA': '1'}}
    assert ('codex', 'mcp', 'add', 'notion', '--env', 'NOTION_TOKEN=abc', '--env', 'OUTRA=1', '--', 'npx', '-y',
            '@notion/mcp') in mcp_de_mentira['chamadas']
    assert servidores_mcp.ler('notion')['variaveis'] == 'NOTION_TOKEN=abc\nOUTRA=1'


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
