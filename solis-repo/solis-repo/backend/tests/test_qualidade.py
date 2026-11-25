"""A taxa de acerto por função (IDEIAS.md, princípios 3 e 4): o registro de uso
(rodou ou falhou), o voto do Matheus (acertou ou errou) e os testes com meta."""
import json

from fastapi.testclient import TestClient

from solis import banco, main, qualidade, roteador

from test_cerebros import cerebro_falso, eventos, local_falso


def _por_nome(r):
    return {(f['tipo'], f['nome']): f for f in r.json()['funcoes']}


def test_o_que_as_etapas_dizem_de_cada_funcao():
    usos = banco.usos_de([
        {'etapa': 'cerebro', 'cerebro': 'claude'},
        {'etapa': 'queda', 'cerebro': 'claude', 'motivo': 'limite de 5 horas'},
        # Passar a vez por não ter ferramenta é de propósito: não é falha.
        {'etapa': 'queda', 'cerebro': 'groq', 'motivo': 'precisa de ferramenta'},
        {'etapa': 'ferramenta', 'ferramenta': 'Write', 'ok': True},
        {'etapa': 'ferramenta', 'ferramenta': 'mcp__notion__search', 'ok': False},
        {'etapa': 'fim', 'cerebro': 'codex', 'cortada': True},
    ])
    assert usos == [('cerebro:claude', False, 'limite de 5 horas'), ('ferramenta:Write', True, None),
                    ('ferramenta:mcp__notion__search', False, None), ('cerebro:codex', False, 'cortada no meio')]
    # Recusada no cartão não é falha da ferramenta; aprovada e com erro, é.
    assert banco.usos_de([
        {'etapa': 'aprovacao', 'id': 'a1', 'ferramenta': 'Write'},
        {'etapa': 'aprovacao_resposta', 'id': 'a1', 'aprovado': False},
        {'etapa': 'ferramenta', 'ferramenta': 'Write', 'ok': False},
        {'etapa': 'aprovacao', 'id': 'a2', 'ferramenta': 'Write'},
        {'etapa': 'aprovacao_resposta', 'id': 'a2', 'aprovado': True},
        {'etapa': 'ferramenta', 'ferramenta': 'Write', 'ok': False},
    ]) == [('ferramenta:Write', False, None)]
    # Parado pelo Matheus não conta pra ninguém.
    assert banco.usos_de([{'etapa': 'fim', 'parada': True}, {'etapa': 'fim', 'cerebro': 'claude', 'parada': True}]) == []


def test_queda_e_resposta_contam_e_o_voto_fica(monkeypatch):
    monkeypatch.setattr(roteador, 'ORDEM', ['claude', 'codex', 'local'])
    cerebro_falso(monkeypatch, {'claude': None, 'codex': 'resposta do codex'}, [])
    local_falso(monkeypatch)
    cli = TestClient(main.app)
    cid = cli.post('/conversas').json()['id']
    r = cli.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    fim = next(e for e in eventos(r) if e.get('etapa') == 'fim')
    resposta = banco.mensagens(cid)[-1]
    assert fim['mensagem'] == resposta['id'] and resposta['voto'] is None

    q = _por_nome(cli.get('/qualidade'))
    assert (q[('cerebro', 'claude')]['usos'], q[('cerebro', 'claude')]['certos']) == (1, 0)
    assert q[('cerebro', 'claude')]['falhas'][0]['detalhe'] == 'claude'
    assert (q[('cerebro', 'codex')]['usos'], q[('cerebro', 'codex')]['certos']) == (1, 1)

    assert cli.put(f'/mensagens/{resposta["id"]}/voto', json={'voto': -1}).json() == {'ok': True, 'voto': -1}
    assert banco.mensagens(cid)[-1]['voto'] == -1
    q = _por_nome(cli.get('/qualidade'))
    assert (q[('cerebro', 'codex')]['bons'], q[('cerebro', 'codex')]['ruins']) == (0, 1)
    assert cli.put(f'/mensagens/{resposta["id"]}/voto', json={'voto': None}).json()['voto'] is None
    assert banco.mensagens(cid)[-1]['voto'] is None
    # A fala da pessoa não é resposta: não tem voto. Nem valor fora de 1/-1.
    assert cli.put(f'/mensagens/{resposta["id"] - 1}/voto', json={'voto': 1}).status_code == 404
    assert cli.put(f'/mensagens/{resposta["id"]}/voto', json={'voto': 5}).status_code == 422

    # Apagar a conversa não apaga a história da função.
    cli.delete(f'/conversas/{cid}')
    assert _por_nome(cli.get('/qualidade'))[('cerebro', 'codex')]['usos'] == 1


def test_ninguem_respondeu_tambem_conta(monkeypatch):
    cerebro_falso(monkeypatch, {'claude': None}, [])
    local_falso(monkeypatch)
    cli = TestClient(main.app)
    cid = cli.post('/conversas').json()['id']
    r = cli.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': '/claude oi'})
    assert eventos(r)[-1]['erro'] == 'cerebro_indisponivel'
    q = _por_nome(cli.get('/qualidade'))
    assert (q[('cerebro', 'claude')]['usos'], q[('cerebro', 'claude')]['certos']) == (1, 0)


def test_o_historico_entra_uma_vez_quando_o_registro_nasce(tmp_path):
    """Um banco de antes do registro (versão 20): as respostas guardadas viram usos."""
    caminho = tmp_path / 'antigo.db'
    banco.usar(caminho)
    banco.usar(caminho)  # abrir de novo não importa duas vezes
    con = banco._con()
    con.execute('DELETE FROM usos')
    con.execute('PRAGMA user_version = 20')
    con.execute('DROP TABLE usos')
    con.execute('DROP TABLE copias_volta')
    con.execute('DROP TABLE lancamentos')
    cid = banco.nova_conversa()
    mid = banco.adicionar(cid, 'solis', 'oi', cerebro='claude')
    banco.guardar_etapas(mid, [{'etapa': 'ferramenta', 'ferramenta': 'Bash', 'ok': False},
                               {'etapa': 'fim', 'cerebro': 'claude'}])
    con.commit()
    banco.usar(caminho)
    banco.usar(caminho)
    assert [(u['funcao'], u['ok']) for u in banco.usos('')] == [('ferramenta:Bash', 0), ('cerebro:claude', 1)]


def test_grupos_e_testes(monkeypatch):
    banco.registrar_usos(None, [{'etapa': 'ferramenta', 'ferramenta': 'mcp__notion__search', 'ok': True},
                                {'etapa': 'ferramenta', 'ferramenta': 'mcp__notion__create', 'ok': False}])
    qualidade.guardar_teste_aprendizado({'certos': 14, 'casos': 14, 'onde': 'groq', 'modelo': 'openai/gpt-oss-20b'})
    from solis import voz_teste
    monkeypatch.setattr(voz_teste, 'listar', lambda: [
        {'id': '20261117-090000', 'medidas': {'silero': {'chamadas': 12, 'entendeu': 12, 'falsos': 0, 'passou': True}}},
        {'id': '20261116-143000', 'medidas': {'atual': {'chamadas': 12, 'entendeu': 11, 'falsos': 0, 'passou': True}}},
    ])
    r = qualidade.relatorio()
    notion = next(f for f in r['funcoes'] if f['tipo'] == 'mcp')
    assert (notion['nome'], notion['usos'], notion['certos']) == ('notion', 2, 1)
    testes = {t['id']: t for t in r['testes']}
    assert (testes['escuta']['certos'], testes['escuta']['total'], testes['escuta']['quando']) == (11, 12, '2026-11-16T14:30:00')
    assert testes['aprendizado']['passou'] and r['meta'] == 0.9
    assert json.dumps(r)  # vai pra tela como está
