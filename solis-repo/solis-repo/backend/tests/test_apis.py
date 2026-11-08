"""Cérebros por API (solis/apis.py), com o serviço simulado — nenhum teste sai
pra rede nem gasta cota de ninguém."""
import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from solis import apis, banco, cerebros, cofre, main, roteador


class Gravador:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


def servico(rota):
    """Transporte falso: `rota(request) -> httpx.Response`."""
    return httpx.MockTransport(rota)


def sse(*eventos):
    linhas = [f'data: {json.dumps(e)}' for e in eventos] + ['data: [DONE]']
    return '\n\n'.join(linhas) + '\n\n'


def coletar(gerador):
    async def junta():
        return [p async for p in gerador]
    return asyncio.run(junta())


# --- escolha do modelo -------------------------------------------------------

def test_groq_e_mistral_pela_preferencia():
    assert apis._escolher('groq', ['llama-3.3-70b-versatile', 'openai/gpt-oss-120b']) == 'openai/gpt-oss-120b'
    assert apis._escolher('mistral', ['codestral-latest', 'mistral-small-latest']) == 'mistral-small-latest'
    # Nenhum preferido: o primeiro que o serviço tem, em vez de nada.
    assert apis._escolher('groq', ['outro-modelo']) == 'outro-modelo'


def test_gemini_pega_o_flash_mais_novo_que_conversa():
    ids = ['gemini-2.5-flash', 'gemini-3.0-flash-lite', 'gemini-3.0-flash-preview-tts',
           'gemini-3.0-flash', 'gemini-2.5-pro', 'gemini-3.1-flash-preview']
    # O estável vence o preview, mesmo mais velho; lite e tts ficam de fora.
    assert apis._escolher('gemini', ids) == 'gemini-3.0-flash'
    assert apis._escolher('gemini', ['gemini-3.1-flash-preview']) == 'gemini-3.1-flash-preview'


def test_openrouter_so_os_gratis():
    ids = ['openai/gpt-oss-120b', 'mistralai/x:free', 'qwen/qwen3-235b:free']
    assert apis._escolher('openrouter', ids) == 'qwen/qwen3-235b:free'
    assert apis._escolher('openrouter', ['openai/gpt-oss-120b']) is None


# --- chave -------------------------------------------------------------------

def test_chave_recusada_nao_e_guardada():
    t = servico(lambda req: httpx.Response(401))
    with pytest.raises(apis.ChaveRecusada):
        asyncio.run(apis.guardar_chave('groq', 'gsk_errada', t))
    assert not apis.tem_chave('groq')


def test_gemini_cai_pra_lista_nativa_quando_o_formato_openai_recusa():
    def rota(req):
        if req.url.path.endswith('/openai/models'):
            return httpx.Response(401)
        assert req.headers['x-goog-api-key'] == 'AIza_boa'
        return httpx.Response(200, json={'models': [
            {'name': 'models/gemini-2.5-flash', 'supportedGenerationMethods': ['generateContent']},
            {'name': 'models/text-embedding-004', 'supportedGenerationMethods': ['embedContent']},
        ]})
    assert asyncio.run(apis.guardar_chave('gemini', 'AIza_boa', servico(rota))) == 'gemini-2.5-flash'

    def recusa(req):
        return httpx.Response(401) if 'openai' in req.url.path else httpx.Response(400)
    with pytest.raises(apis.ChaveRecusada):
        asyncio.run(apis.guardar_chave('gemini', 'errada', servico(recusa)))


def test_chave_boa_fica_selada_com_o_modelo(tmp_path):
    vistos = []

    def rota(req):
        vistos.append((req.url, req.headers['authorization']))
        return httpx.Response(200, json={'data': [{'id': 'openai/gpt-oss-120b'}]})

    assert asyncio.run(apis.guardar_chave('groq', 'gsk_boa', servico(rota))) == 'openai/gpt-oss-120b'
    assert vistos == [(httpx.URL('https://api.groq.com/openai/v1/models'), 'Bearer gsk_boa')]
    assert apis.tem_chave('groq') and apis.modelo('groq') == 'openai/gpt-oss-120b'
    if cofre.DISPONIVEL:
        assert cofre.selado(banco.ajuste('chave:groq'))
        banco._con().execute('PRAGMA wal_checkpoint(TRUNCATE)')
        assert b'gsk_boa' not in (tmp_path / 'solis.db').read_bytes()


def test_rota_guarda_liga_e_nunca_devolve_a_chave(monkeypatch):
    async def lista(nome, chave, transporte=None):
        return ['openai/gpt-oss-120b']
    monkeypatch.setattr(apis, 'listar', lista)
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: nome in cerebros.CLIS or apis.tem_chave(nome))
    cliente = TestClient(main.app)

    r = cliente.put('/cerebros/groq/chave', json={'chave': '  gsk_segredo  '})
    assert r.status_code == 200 and 'gsk_segredo' not in r.text
    groq = next(c for c in r.json()['cerebros'] if c['nome'] == 'groq')
    assert (groq['ligado'], groq['instalado'], groq['modelo']) == (True, True, 'openai/gpt-oss-120b')
    assert groq['site'].startswith('https://console.groq.com')
    assert 'groq' in roteador.escolher('oi')[1]
    assert roteador.escolher('/groq oi') == ('oi', ['groq'], True)

    r = cliente.delete('/cerebros/groq/chave')
    groq = next(c for c in r.json()['cerebros'] if c['nome'] == 'groq')
    assert (groq['ligado'], groq['instalado'], groq['modelo']) == (False, False, None)


def test_rota_diz_o_que_deu_errado(monkeypatch):
    cliente = TestClient(main.app)
    assert cliente.put('/cerebros/claude/chave', json={'chave': 'x'}).status_code == 404
    assert cliente.put('/cerebros/groq/chave', json={'chave': '  '}).json() == {'erro': 'chave_vazia'}

    async def recusa(*_, **__):
        raise apis.ChaveRecusada()
    monkeypatch.setattr(apis, 'listar', recusa)
    assert cliente.put('/cerebros/groq/chave', json={'chave': 'x'}).json() == {'erro': 'chave_recusada'}

    async def fora(*_, **__):
        raise apis.ProvedorFora('ConnectError')
    monkeypatch.setattr(apis, 'listar', fora)
    r = cliente.put('/cerebros/groq/chave', json={'chave': 'x'})
    assert (r.status_code, r.json()['erro']) == (502, 'provedor_fora')


# --- resposta ----------------------------------------------------------------

def com_chave(nome='groq', modelo='openai/gpt-oss-120b'):
    banco.guardar_ajuste(f'chave:{nome}', cofre.selar('gsk_x'))
    banco.guardar_ajuste(f'modelo:{nome}', modelo)


def test_resposta_em_pedacos_e_raciocinio_vira_etapa():
    com_chave()
    pedidos = []

    def rota(req):
        pedidos.append(json.loads(req.content))
        corpo = sse(
            {'choices': [{'delta': {'reasoning': 'hmm'}}]},
            {'choices': [{'delta': {'content': 'Bom '}}]},
            {'choices': [{'delta': {}}]},
            {'choices': [{'delta': {'content': 'dia.'}}]},
        )
        return httpx.Response(200, text=corpo, headers={'content-type': 'text/event-stream'})

    g = Gravador()
    assert ''.join(coletar(apis.responder('groq', 'sis', 'oi', g, servico(rota)))) == 'Bom dia.'
    [p] = pedidos
    assert p['model'] == 'openai/gpt-oss-120b' and p['stream'] is True
    assert p['messages'] == [{'role': 'system', 'content': 'sis'}, {'role': 'user', 'content': 'oi'}]
    assert [e for e, _ in g.lista] == ['pedido', 'pensando']


def test_limite_gratis_pausa_ate_quando_o_servico_disse():
    com_chave()
    t = servico(lambda req: httpx.Response(429, headers={'retry-after': '30'}))
    with pytest.raises(cerebros.CerebroFalhou):
        coletar(apis.responder('groq', 's', 'p', transporte=t))
    pausa = cerebros.pausa('groq')
    assert pausa['motivo'] == 'o limite grátis acabou'
    assert 25 < pausa['ate'] - time.time() <= 30


def test_abrir_nao_troca_a_pausa_certa_pela_padrao(monkeypatch):
    """O retry-after de 30 s não pode virar 30 min no abrir()."""
    async def responde(nome, sistema, prompt, etapas=None):
        cerebros.pausar(nome, time.time() + 30, 'o limite grátis acabou')
        raise cerebros.CerebroFalhou('o limite grátis acabou')
        yield  # pragma: no cover
    monkeypatch.setattr(apis, 'responder', responde)
    with pytest.raises(cerebros.CerebroFalhou):
        asyncio.run(cerebros.abrir('groq', 's', 'p'))
    assert cerebros.pausa('groq')['ate'] - time.time() <= 30


def test_chave_recusada_na_resposta_pausa_um_dia():
    com_chave()
    t = servico(lambda req: httpx.Response(401))
    with pytest.raises(cerebros.CerebroFalhou, match='chave foi recusada'):
        coletar(apis.responder('groq', 's', 'p', transporte=t))
    assert cerebros.pausa('groq')['ate'] - time.time() > 23 * 3600


def test_sem_chave_falha_sem_chamar_ninguem():
    with pytest.raises(cerebros.CerebroFalhou, match='sem chave'):
        coletar(apis.responder('gemini', 's', 'p', transporte=servico(lambda req: 1 / 0)))
