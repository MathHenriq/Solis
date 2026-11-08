"""A ordem dos cérebros escolhida pela tela (Configurações → Cérebros)."""
import time

from fastapi.testclient import TestClient

from solis import banco, cerebros, main, roteador


APIS = [('groq', False), ('gemini', False), ('mistral', False), ('openrouter', False)]


def nomes(r):
    return [(c['nome'], c['ligado']) for c in r.json()['cerebros']]


def test_sem_escolha_vale_o_padrao(monkeypatch):
    monkeypatch.setattr(roteador, 'ORDEM', ['claude', 'codex', 'local'])
    r = TestClient(main.app).get('/cerebros')
    assert nomes(r) == [('claude', True), ('codex', True), ('local', True)] + APIS
    assert [c['rotulo'] for c in r.json()['cerebros']][:3] == ['Claude', 'Codex', 'Modelo local']


def test_fora_do_padrao_entra_desligado(monkeypatch):
    monkeypatch.setattr(roteador, 'ORDEM', ['claude', 'local'])
    assert nomes(TestClient(main.app).get('/cerebros')) == [('claude', True), ('local', True), ('codex', False)] + APIS


def test_escolha_guardada_vence_o_padrao_e_muda_o_roteador(monkeypatch):
    monkeypatch.setattr(roteador, 'ORDEM', ['claude', 'codex', 'local'])
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: True)
    ordem = [{'nome': 'local', 'ligado': True}, {'nome': 'codex', 'ligado': True}, {'nome': 'claude', 'ligado': False}]
    r = TestClient(main.app).put('/cerebros', json={'ordem': ordem})
    assert nomes(r) == [('local', True), ('codex', True), ('claude', False)] + APIS
    assert banco.ajuste('cerebros') == ordem
    # Desligado não é tentado; a ordem é a da tela.
    assert roteador.escolher('oi') == ('oi', ['local', 'codex'], False)
    # O comando continua mandando, mesmo pra um desligado.
    assert roteador.escolher('/claude oi') == ('oi', ['claude'], True)


def test_local_nunca_desliga():
    ordem = [{'nome': 'claude', 'ligado': True}, {'nome': 'codex', 'ligado': True}, {'nome': 'local', 'ligado': False}]
    r = TestClient(main.app).put('/cerebros', json={'ordem': ordem})
    assert ('local', True) in nomes(r)


def test_ordem_repetida_ou_desconhecida_e_recusada():
    cliente = TestClient(main.app)
    for ordem in (
        [{'nome': 'claude', 'ligado': True}, {'nome': 'claude', 'ligado': True}, {'nome': 'local', 'ligado': True}],
        [{'nome': 'claude', 'ligado': True}, {'nome': 'codex', 'ligado': True}, {'nome': 'gpt', 'ligado': True}],
    ):
        assert cliente.put('/cerebros', json={'ordem': ordem}).status_code == 400
    assert banco.ajuste('cerebros') is None


def test_ordem_incompleta_completa_pelo_fim():
    """Uma tela mais velha que um cérebro novo manda só os que conhece."""
    r = TestClient(main.app).put('/cerebros', json={'ordem': [{'nome': 'codex', 'ligado': True}]})
    assert r.status_code == 200
    assert nomes(r)[:2] == [('codex', True), ('local', True)]
    assert ('claude', False) in nomes(r)


def test_cerebro_novo_depois_da_escolha_vai_pro_fim_desligado(monkeypatch):
    banco.guardar_ajuste('cerebros', [{'nome': 'local', 'ligado': True}, {'nome': 'claude', 'ligado': True}])
    assert nomes(TestClient(main.app).get('/cerebros')) == [('local', True), ('claude', True), ('codex', False)] + APIS


def test_pausa_aparece_com_o_motivo_e_retomar_tira(monkeypatch):
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: True)
    cerebros.pausar('claude', time.time() + 600, 'a cota acabou')
    cliente = TestClient(main.app)
    claude = next(c for c in cliente.get('/cerebros').json()['cerebros'] if c['nome'] == 'claude')
    assert claude['pausa']['motivo'] == 'a cota acabou' and claude['instalado']
    assert 'claude' not in roteador.escolher('oi')[1]

    r = cliente.post('/cerebros/claude/retomar')
    assert next(c for c in r.json()['cerebros'] if c['nome'] == 'claude')['pausa'] is None
    assert 'claude' in roteador.escolher('oi')[1]
    assert cliente.post('/cerebros/gpt/retomar').status_code == 404


def test_cli_ausente_aparece_como_nao_instalado():
    # conftest: nenhum CLI "instalado".
    r = TestClient(main.app).get('/cerebros').json()['cerebros']
    assert {c['nome']: c['instalado'] for c in r} == {'claude': False, 'codex': False, 'local': True, **{n: False for n, _ in APIS}}
    assert {c['nome']: c['tipo'] for c in r}['groq'] == 'api'
