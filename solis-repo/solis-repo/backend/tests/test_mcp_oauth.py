"""O login (OAuth) nos servidores MCP por endereço (solis/mcp_oauth.py): o
Solis entra uma vez, com o Matheus, guarda o token no cofre e renova sozinho;
o Claude Code (headersHelper), o Codex (a variável) e os cérebros por API usam
o mesmo login. Um servidor com login de verdade roda na máquina
(oauth_de_teste.py); o "navegador" segue o redirecionamento da página de
login, que aprova sozinha. Os CLIs são os falsos do conftest."""
import asyncio
import io
import json
import time
from contextlib import redirect_stdout
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from oauth_de_teste import ServidorComLogin
from solis import lancar_mcp, main, mcp_oauth, servidores_mcp


def _entrar(cli, monkeypatch, nome):
    """O caminho da tela: Entrar → o Solis abre a página → o Matheus entra →
    o serviço volta pro Solis. Devolve a situação do login no fim."""
    abertas = []
    monkeypatch.setattr(main, '_abrir_no_navegador', abertas.append)
    r = cli.post(f'/mcp/{nome}/entrar')
    assert r.status_code == 200, r.text
    assert abertas == [r.json()['url']]
    assert cli.get(f'/mcp/{nome}/entrar').json()['estado'] == 'esperando'
    # O navegador: a página de login aprova e manda de volta pro Solis.
    volta = httpx.get(abertas[0], follow_redirects=False).headers['location']
    partes = urlsplit(volta)
    assert partes.path == mcp_oauth.VOLTA
    pagina = cli.get(f'{partes.path}?{partes.query}')
    assert 'Pronto: o Solis entrou' in pagina.text
    for _ in range(100):
        s = cli.get(f'/mcp/{nome}/entrar').json()
        if s['estado'] != 'esperando':
            return s
        time.sleep(0.05)
    return s


def test_entrar_guarda_no_cofre_e_todos_usam_o_mesmo_login(mcp_de_mentira, monkeypatch):
    with ServidorComLogin() as srv, TestClient(main.app) as cli:
        servidores_mcp.salvar('docs', 'endereco', '', srv.url, '', ['claude', 'codex'])
        # Sem login: o servidor recusa, e a tela sabe que é caso de "Entrar".
        r = cli.post('/mcp/docs/conferir').json()
        assert r['erro'] == 'o servidor pede login ou chave (401): use "Entrar", ou ponha a chave nos cabeçalhos'
        assert _entrar(cli, monkeypatch, 'docs') == {'estado': 'pronto', 'erro': None}
        # O token no cofre, nunca nos arquivos dos CLIs.
        token = mcp_oauth._ler('docs')['tokens']['access_token']
        config = json.loads((servidores_mcp._casa() / '.claude.json').read_text())['mcpServers']['docs']
        assert servidores_mcp.CABECALHOS.name in config['headersHelper']
        add = [c for c in mcp_de_mentira['chamadas'] if c[:3] == ('codex', 'mcp', 'add')][-1]
        assert add[-2:] == ('--bearer-token-env-var', 'SOLIS_MCP_DOCS_TOKEN')
        assert token not in json.dumps([config, mcp_de_mentira['chamadas']])
        assert next(s for s in servidores_mcp.listar() if s['nome'] == 'docs')['login'] is True
        # O Solis (o "Conferir" e os cérebros por API) conecta com o login.
        assert cli.post('/mcp/docs/conferir').json()['total'] == 1
        assert asyncio.run(servidores_mcp.chamar(servidores_mcp._do_claude()['docs'], 'eco', {'texto': 'oi'})) == (
            'oi', True)
        # O Claude Code (o headersHelper) e o Codex (a variável) recebem o mesmo token.
        saida = io.StringIO()
        with redirect_stdout(saida):
            assert lancar_mcp.cabecalhos('docs') == 0
        assert json.loads(saida.getvalue()) == {'Authorization': f'Bearer {token}'}
        assert servidores_mcp.ambiente_do_codex()['SOLIS_MCP_DOCS_TOKEN'] == token


def test_o_token_vencido_e_renovado_sozinho(mcp_de_mentira, monkeypatch):
    with ServidorComLogin(dura=2) as srv, TestClient(main.app) as cli:
        servidores_mcp.salvar('docs', 'endereco', '', srv.url, '', ['claude'])
        assert _entrar(cli, monkeypatch, 'docs')['estado'] == 'pronto'
        antes = mcp_oauth._ler('docs')['tokens']['access_token']
        renovados = srv.provedor.renovados
        time.sleep(2.2)  # venceu de verdade: o servidor recusaria o de antes
        assert cli.post('/mcp/docs/conferir').json()['total'] == 1
        assert srv.provedor.renovados > renovados
        assert mcp_oauth._ler('docs')['tokens']['access_token'] != antes


def test_login_vencido_sem_renovacao_pede_entrar_de_novo(mcp_de_mentira, monkeypatch):
    with ServidorComLogin() as srv, TestClient(main.app) as cli:
        servidores_mcp.salvar('docs', 'endereco', '', srv.url, '', ['claude'])
        assert _entrar(cli, monkeypatch, 'docs')['estado'] == 'pronto'
        dados = mcp_oauth._ler('docs')
        dados['vence'] = time.time() - 10
        dados['tokens'].pop('refresh_token')
        mcp_oauth._guardar('docs', dados)
        erro = cli.post('/mcp/docs/conferir').json()['erro']
        assert erro == 'o login do servidor "docs" venceu: entre de novo'
        with pytest.raises(mcp_oauth.PrecisaEntrar):
            mcp_oauth.token('docs')
        assert lancar_mcp.cabecalhos('docs') == 1


def test_salvar_de_novo_mantem_o_login_e_mudar_o_endereco_ou_remover_tira(mcp_de_mentira, monkeypatch):
    with ServidorComLogin() as srv, TestClient(main.app) as cli:
        servidores_mcp.salvar('docs', 'endereco', '', srv.url, '', ['claude'])
        assert _entrar(cli, monkeypatch, 'docs')['estado'] == 'pronto'
        servidores_mcp.salvar('docs2', 'endereco', '', srv.url, '', ['claude'], antigo='docs')
        assert mcp_oauth.tem('docs2') and not mcp_oauth.tem('docs')
        servidores_mcp.salvar('docs2', 'endereco', '', srv.url + '/outro', '', ['claude'], antigo='docs2')
        assert not mcp_oauth.tem('docs2')
        # Nesse endereço não há servidor: o Entrar diz por quê.
        monkeypatch.setattr(main, '_abrir_no_navegador', lambda url: None)
        r = cli.post('/mcp/docs2/entrar')
        assert r.status_code == 400 and r.json()['motivo'] == 'o servidor não deixou entrar (Not Found)'
        servidores_mcp.salvar('docs2', 'endereco', '', srv.url, '', ['claude'], antigo='docs2')
        assert _entrar(cli, monkeypatch, 'docs2')['estado'] == 'pronto'
        servidores_mcp.remover('docs2')
        assert not mcp_oauth.tem('docs2')


def test_volta_sem_login_esperando_e_servidor_sem_oauth(mcp_de_mentira, monkeypatch):
    with TestClient(main.app) as cli:
        assert 'não estava sendo esperado' in cli.get(f'{mcp_oauth.VOLTA}?code=x&state=y').text
        assert cli.post('/mcp/nao-existe/entrar').status_code == 404
