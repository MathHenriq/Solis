"""Cérebros externos e roteador, sem chamar CLI de verdade.

As linhas do Claude são de uma chamada real ao Claude Code 2.1 (enxugadas); as
do Codex, do exemplo da documentação dele."""
import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from solis import banco, cerebros, main, memoria, ollama, roteador

CLAUDE_REAL = [
    {'type': 'system', 'subtype': 'init'},
    {'type': 'stream_event', 'event': {'type': 'content_block_delta', 'index': 0,
                                       'delta': {'type': 'text_delta', 'text': 'ok, '}}},
    {'type': 'stream_event', 'event': {'type': 'content_block_delta', 'index': 0,
                                       'delta': {'type': 'text_delta', 'text': 'funcionou'}}},
    {'type': 'rate_limit_event', 'rate_limit_info': {'status': 'allowed', 'resetsAt': 1793406000}},
    {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'ok, funcionou'},
]
CODEX_DOC = [
    {'type': 'thread.started', 'thread_id': '0199a213'},
    {'type': 'turn.started'},
    {'type': 'item.completed', 'item': {'id': 'item_1', 'type': 'agent_message', 'text': 'Deixa eu ver.'}},
    {'type': 'item.completed', 'item': {'id': 'item_3', 'type': 'agent_message', 'text': 'A resposta final.'}},
    {'type': 'turn.completed', 'usage': {'output_tokens': 122}},
]


def saida(monkeypatch, eventos, recebido=None):
    """Troca o processo pelo que ele teria escrito, uma linha JSON por evento."""
    async def falso(comando, entrada, *_):
        if recebido is not None:
            recebido.append((comando, entrada))
        for e in eventos:
            yield json.dumps(e) + '\n'
    monkeypatch.setattr(cerebros, '_linhas', falso)
    monkeypatch.setattr(cerebros.shutil, 'which', lambda nome: f'/bin/{nome}')


async def juntar(fluxo):
    return ''.join([p async for p in fluxo])


def eventos(r) -> list[dict]:
    return [json.loads(linha) for linha in r.text.splitlines()]


def texto(r) -> str:
    return ''.join(e.get('texto', '') for e in eventos(r))


@pytest.fixture(autouse=True)
def _cli_sem_ferramentas(monkeypatch):
    """Estes testes simulam o CLI só de conversa — o caminho de reserva do
    Claude. O agente (Agent SDK) tem os seus em test_agente.py."""
    monkeypatch.setattr(cerebros, 'USAR_AGENTE', False)


def test_claude_le_os_pedacos_do_stream(monkeypatch):
    recebido = []
    saida(monkeypatch, CLAUDE_REAL, recebido)
    texto = asyncio.run(juntar(cerebros.claude('sistema', 'pergunta')))
    assert texto == 'ok, funcionou'
    comando, entrada = recebido[0]
    # O prompt vai pela entrada padrão, nunca na linha de comando.
    assert entrada == 'pergunta' and 'pergunta' not in comando
    assert comando[comando.index('--tools') + 1] == ''


def test_claude_com_cota_acabando_sai_da_fila_ate_renovar(monkeypatch):
    eventos = [*CLAUDE_REAL[:2], {'type': 'rate_limit_event', 'rate_limit_info': {'status': 'rejected', 'resetsAt': 2e9}}]
    saida(monkeypatch, eventos)
    asyncio.run(juntar(cerebros.claude('s', 'p')))
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: True)
    assert not cerebros.disponivel('claude')


def test_claude_com_erro_falha(monkeypatch):
    saida(monkeypatch, [{'type': 'result', 'is_error': True, 'result': 'usage limit'}])
    with pytest.raises(cerebros.CerebroFalhou):
        asyncio.run(cerebros.abrir('claude', 's', 'p'))
    assert cerebros._fora_ate['claude'] > 0  # e fica de lado um tempo


def test_codex_vale_a_ultima_mensagem_do_turno(monkeypatch):
    recebido = []
    saida(monkeypatch, CODEX_DOC, recebido)
    assert asyncio.run(juntar(cerebros.codex('sistema', 'pergunta'))) == 'A resposta final.'
    comando, entrada = recebido[0]
    assert comando[-1] == '-' and '--sandbox' in comando and entrada.startswith('sistema')


def test_codex_sem_resposta_falha_antes_da_primeira_palavra(monkeypatch):
    saida(monkeypatch, [{'type': 'turn.started'}, {'type': 'turn.failed', 'error': {'message': 'limit'}}])
    with pytest.raises(cerebros.CerebroFalhou):
        asyncio.run(cerebros.abrir('codex', 's', 'p'))


def test_processo_de_verdade_entrega_linha_a_linha(monkeypatch, tmp_path):
    """O Popen com thread, de verdade, com um Python no lugar do CLI."""
    monkeypatch.setattr(banco, 'caminho_padrao', lambda: tmp_path / 'solis.db')
    script = 'import sys; dado = sys.stdin.read(); print("eco:" + dado); print("fim")'

    async def rodar():
        return [l async for l in cerebros._linhas([sys.executable, '-c', script], 'olá ção')]
    assert asyncio.run(rodar()) == ['eco:olá ção\n', 'fim\n']


# — Roteador ———————————————————————————————————————————————————————————————————

def test_comando_escolhe_e_sai_do_texto():
    assert roteador.escolher('/claude explica recursão') == ('explica recursão', ['claude'], True)
    assert roteador.escolher('/LOCAL oi') == ('oi', ['local'], True)
    # Só o comando, sem pergunta, não é comando.
    assert roteador.escolher('/claude')[2] is False


def test_sigilo_vai_so_pro_local(monkeypatch):
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: True)
    assert roteador.escolher('isso é privado: tenho asma')[1] == ['local']


def test_ordem_pula_quem_nao_esta_instalado(monkeypatch):
    monkeypatch.setattr(roteador, 'ORDEM', ['claude', 'codex', 'local'])
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: nome == 'codex')
    assert roteador.escolher('oi')[1] == ['codex', 'local']


def cerebro_falso(monkeypatch, respostas: dict, recebido: list):
    """`respostas`: nome → texto, ou None pra falhar."""
    async def abrir(nome, sistema, prompt, etapas=None, sessao=None):
        recebido.append((nome, prompt))
        if respostas.get(nome) is None:
            raise cerebros.CerebroFalhou(nome)

        async def gen():
            yield respostas[nome]
        return gen()
    monkeypatch.setattr(cerebros, 'abrir', abrir)
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: True)


def local_falso(monkeypatch, texto='resposta local'):
    async def conversar(modelo, mensagens, memorias=None, trechos=None, resumo=None, **_):
        async def gen():
            yield texto
        return gen()
    monkeypatch.setattr(ollama, 'conversar', conversar)

    async def nada(*_, **__):
        pass
    monkeypatch.setattr(memoria, 'aprender', nada)


def test_cai_pro_proximo_e_diz_quem_respondeu(monkeypatch):
    recebido = []
    monkeypatch.setattr(roteador, 'ORDEM', ['claude', 'codex', 'local'])
    cerebro_falso(monkeypatch, {'claude': None, 'codex': 'resposta do codex'}, recebido)
    local_falso(monkeypatch)
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']

    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'oi'})
    assert texto(r) == 'resposta do codex'
    # As etapas dizem quem tentou, quem caiu e por quê, e quem respondeu.
    etapas = [(e['etapa'], e.get('cerebro')) for e in eventos(r) if 'etapa' in e]
    assert etapas[:6] == [
        ('guardada', None), ('memoria', None), ('cerebro', 'claude'), ('queda', 'claude'), ('cerebro', 'codex'), ('fim', 'codex'),
    ]
    assert [e['motivo'] for e in eventos(r) if e.get('etapa') == 'queda'] == ['claude']
    assert [n for n, _ in recebido] == ['claude', 'codex']
    assert banco.mensagens(cid)[-1]['cerebro'] == 'codex'


def test_forcado_que_falha_nao_cai_pra_outro(monkeypatch):
    cerebro_falso(monkeypatch, {'claude': None}, [])
    local_falso(monkeypatch)
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']

    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': '/claude oi'})
    ultimo = eventos(r)[-1]
    assert (ultimo['erro'], ultimo['cerebro']) == ('cerebro_indisponivel', 'Claude')
    # O que foi dito fica guardado, sem o comando.
    assert [m['texto'] for m in banco.mensagens(cid)] == ['oi']


def test_ollama_fora_nao_impede_a_nuvem(monkeypatch):
    monkeypatch.setattr(roteador, 'ORDEM', ['claude', 'local'])
    cerebro_falso(monkeypatch, {'claude': 'da nuvem'}, [])
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']
    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': '', 'texto': 'oi'})
    assert texto(r) == 'da nuvem'


def test_nada_privado_vai_pra_nuvem(monkeypatch):
    recebido = []
    monkeypatch.setattr(roteador, 'ORDEM', ['claude'])
    cerebro_falso(monkeypatch, {'claude': 'ok'}, recebido)
    banco.adicionar_memoria('Tem asma.', 'Saúde', False, None, privada=True)
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    cid = banco.nova_conversa()
    segredo = banco.adicionar(cid, 'pessoa', 'minha senha é abc123')
    banco.adicionar(cid, 'solis', 'Anotei abc123.')
    banco.marcar_privada(segredo)
    banco.guardar_resumo(cid, '- falaram da senha', 0)

    TestClient(main.app).post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'e o trabalho?'})
    [(_, prompt)] = recebido
    assert 'Trabalha na Syngenta.' in prompt and 'e o trabalho?' in prompt
    for vazou in ('asma', 'abc123', 'falaram da senha'):
        assert vazou not in prompt


def test_aprender_privado_marca_a_mensagem_e_a_resposta(monkeypatch):
    async def extrai(modelo, instrucao, texto, esquema):
        return {'memorias': [{'texto': 'Tem asma.', 'tema': 'Saúde', 'privada': True, 'substitui': 0}]}
    monkeypatch.setattr(ollama, 'responder_json', extrai)
    cid = banco.nova_conversa()
    pergunta = banco.adicionar(cid, 'pessoa', 'tenho asma')
    banco.adicionar(cid, 'solis', 'Entendi, asma.')
    banco.adicionar(cid, 'pessoa', 'e o tempo hoje?')

    asyncio.run(memoria.aprender('m', cid, 'tenho asma', [], pergunta))
    assert [m['privada'] for m in banco.mensagens(cid)] == [True, True, False]


# — Etapas ——————————————————————————————————————————————————————————————————————

class Gravador:
    def __init__(self):
        self.vistas = []

    def marcar(self, etapa, **dados):
        self.vistas.append((etapa, dados))


def test_processo_de_verdade_marca_quando_sobe_e_quando_escreve(monkeypatch, tmp_path):
    monkeypatch.setattr(banco, 'caminho_padrao', lambda: tmp_path / 'solis.db')
    g = Gravador()

    async def rodar():
        return [l async for l in cerebros._linhas([sys.executable, '-c', 'print("oi")'], '', g, 'claude')]
    asyncio.run(rodar())
    assert g.vistas == [('processo', {'cerebro': 'claude'}), ('primeira_linha', {'cerebro': 'claude'})]


def test_claude_pensando_e_primeira_palavra(monkeypatch):
    pensa = {'type': 'stream_event', 'event': {'delta': {'type': 'thinking_delta', 'thinking': 'hmm'}}}
    saida(monkeypatch, [CLAUDE_REAL[0], pensa, pensa, *CLAUDE_REAL[1:]])
    g = Gravador()

    async def rodar():
        return await juntar(await cerebros.abrir('claude', 's', 'p', g))
    # O raciocínio não vaza pro texto, e "pensando" é marcado uma vez só.
    assert asyncio.run(rodar()) == 'ok, funcionou'
    assert [e for e, _ in g.vistas] == ['pensando', 'primeira_palavra']


def test_cli_que_nao_sobe_cai_com_o_motivo(monkeypatch, tmp_path):
    """Processo de verdade que nunca escreve: travado subindo (MCP, login...)."""
    monkeypatch.setattr(banco, 'caminho_padrao', lambda: tmp_path / 'solis.db')
    monkeypatch.setattr(cerebros, 'PRIMEIRA_LINHA_S', 0.3)

    async def rodar():
        return [l async for l in cerebros._linhas([sys.executable, '-c', 'import time; time.sleep(30)'], '')]
    with pytest.raises(cerebros.CerebroFalhou, match='não escreveu nada em 0.3 s'):
        asyncio.run(rodar())


def test_cli_que_cala_no_meio_cai_com_o_motivo(monkeypatch, tmp_path):
    monkeypatch.setattr(banco, 'caminho_padrao', lambda: tmp_path / 'solis.db')
    monkeypatch.setattr(cerebros, 'SILENCIO_S', {'claude': 0.3})
    script = 'import time; print("oi", flush=True); time.sleep(30)'

    async def rodar():
        return [l async for l in cerebros._linhas([sys.executable, '-c', script], '', cerebro='claude')]
    with pytest.raises(cerebros.CerebroFalhou, match='ficou 0.3 s calado'):
        asyncio.run(rodar())


def test_claude_termina_no_fim_da_mensagem(monkeypatch):
    """O que vem depois do message_stop (o result, uns segundos depois) nem é
    lido: a resposta acabou ali."""
    fim = {'type': 'stream_event', 'event': {'type': 'message_stop'}}
    depois = {'type': 'result', 'is_error': True, 'result': 'nunca lido'}
    saida(monkeypatch, [*CLAUDE_REAL[:3], fim, depois])
    assert asyncio.run(juntar(cerebros.claude('s', 'p'))) == 'ok, funcionou'


def test_local_marca_pensando_e_primeira_palavra():
    import httpx
    from test_conversa import chat_falso
    g = Gravador()

    async def rodar():
        fluxo = await ollama.conversar('m', [], transporte=httpx.MockTransport(chat_falso([])), etapas=g)
        return await juntar(await roteador._primeira_palavra(fluxo, g))
    assert asyncio.run(rodar()) == 'Olá, Matheus.'
    assert [e for e, _ in g.vistas] == ['pensando', 'primeira_palavra']
