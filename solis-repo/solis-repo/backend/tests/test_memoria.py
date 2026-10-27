"""Extração e uso das memórias, com o Ollama trocado por respostas fixas."""
import asyncio

from fastapi.testclient import TestClient

from solis import banco, main, memoria, ollama


def responde(monkeypatch, memorias=None, falha=False):
    """Troca a pergunta de extração por uma resposta fixa, e guarda o que foi perguntado."""
    perguntas = []

    async def falso(modelo, instrucao, texto, esquema):
        perguntas.append(texto)
        if falha:
            raise ollama.OllamaIndisponivel()
        return {'memorias': memorias or []}
    monkeypatch.setattr(ollama, 'responder_json', falso)
    return perguntas


def textos():
    return [(m['texto'], m['tema'], m['pedido']) for m in banco.memorias()]


def test_guarda_o_que_o_modelo_extraiu(monkeypatch):
    responde(monkeypatch, [{'texto': 'Trabalha na Syngenta.', 'tema': 'Trabalho'}])
    asyncio.run(memoria.aprender('m', None, 'Trabalho na Syngenta faz dois anos', []))
    assert textos() == [('Trabalha na Syngenta.', 'Trabalho', False)]


def test_nao_duplica_o_que_ja_sabe(monkeypatch):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    perguntas = responde(monkeypatch, [{'texto': 'trabalha na syngenta', 'tema': 'Trabalho'}])
    asyncio.run(memoria.aprender('m', None, 'na Syngenta, como eu disse', []))
    assert len(banco.memorias()) == 1
    # E o modelo foi avisado do que já existe.
    assert 'Trabalha na Syngenta.' in perguntas[0]


def test_pedido_e_marcado_como_pedido(monkeypatch):
    perguntas = responde(monkeypatch, [{'texto': 'Trabalha na Syngenta.', 'tema': 'Trabalho'}])
    asyncio.run(memoria.aprender('m', None, 'Então grave, atuo na Syngenta', []))
    assert textos() == [('Trabalha na Syngenta.', 'Trabalho', True)]
    assert 'PEDIU' in perguntas[0]


def test_pedido_sobrevive_ao_modelo_nao_achar_nada(monkeypatch):
    responde(monkeypatch, [])
    asyncio.run(memoria.aprender('m', None, 'Anote: minha cor preferida é verde', []))
    assert textos() == [('Anote: minha cor preferida é verde', memoria.TEMA_PEDIDO, True)]


def test_pedido_sobrevive_ao_ollama_fora(monkeypatch):
    responde(monkeypatch, falha=True)
    asyncio.run(memoria.aprender('m', None, 'lembre que eu prefiro chá', []))
    assert [t for t, *_ in textos()] == ['lembre que eu prefiro chá']


def test_sem_pedido_e_sem_nada_novo_nao_guarda(monkeypatch):
    responde(monkeypatch, [])
    asyncio.run(memoria.aprender('m', None, 'qual a capital da França?', []))
    assert textos() == []


def test_o_que_e_e_o_que_nao_e_pedido():
    assert memoria.eh_pedido('Então grave, atuo na Syngenta')
    assert memoria.eh_pedido('Lembre-se disso: sou canhoto')
    assert not memoria.eh_pedido('você lembra o que eu disse?')
    assert not memoria.eh_pedido('Você grave as conversas?')   # pergunta, mesmo com o verbo
    assert not memoria.eh_pedido('ele guarda as conversas')


def test_memorias_vao_no_prompt_da_conversa():
    s = ollama.sistema([{'texto': 'Trabalha na Syngenta.'}])
    assert s.startswith(ollama.SISTEMA) and '- Trabalha na Syngenta.' in s
    assert 'Ainda não há memórias' in ollama.sistema([])


def test_rotas_de_memoria():
    banco.adicionar_memoria('Prefere chá.', 'Preferências', True, None)
    cliente = TestClient(main.app)
    [m] = cliente.get('/memorias').json()['memorias']
    assert (m['texto'], m['pedido']) == ('Prefere chá.', True)
    assert cliente.delete(f'/memorias/{m["id"]}').json() == {'ok': True}
    assert cliente.get('/memorias').json() == {'memorias': []}
    assert cliente.delete(f'/memorias/{m["id"]}').status_code == 404


def test_pedido_com_ollama_fora_na_conversa(monkeypatch):
    async def fora(*_, **__):
        raise ollama.OllamaIndisponivel()
    monkeypatch.setattr(ollama, 'conversar', fora)
    cliente = TestClient(main.app)
    cid = cliente.post('/conversas').json()['id']
    r = cliente.post(f'/conversas/{cid}/mensagens', json={'modelo': 'm', 'texto': 'grave que eu moro em Campinas'})
    assert r.status_code == 503
    assert [t for t, *_ in textos()] == ['grave que eu moro em Campinas']


def test_modelo_marca_o_que_e_sensivel(monkeypatch):
    responde(monkeypatch, [
        {'texto': 'Tem asma.', 'tema': 'Saúde', 'privada': True},
        {'texto': 'Gosta de chá.', 'tema': 'Preferências', 'privada': False},
    ])
    asyncio.run(memoria.aprender('m', None, 'tenho asma e gosto de chá', []))
    assert {m['texto']: m['privada'] for m in banco.memorias()} == {'Tem asma.': True, 'Gosta de chá.': False}


def test_dizer_que_e_privado_vale_mesmo_se_o_modelo_discordar(monkeypatch):
    responde(monkeypatch, [{'texto': 'Ganha 5 mil por mês.', 'tema': 'Trabalho', 'privada': False}])
    asyncio.run(memoria.aprender('m', None, 'isso é privado: ganho 5 mil por mês', []))
    assert [m['privada'] for m in banco.memorias()] == [True]


def test_pedido_cru_privado_continua_privado(monkeypatch):
    responde(monkeypatch, falha=True)
    asyncio.run(memoria.aprender('m', None, 'grave, é segredo: a senha do wifi é abc123', []))
    [m] = banco.memorias()
    assert m['privada'] and m['tema'] == memoria.TEMA_PEDIDO


def test_o_que_conta_como_pedido_de_sigilo():
    assert memoria.eh_privado('Isso é confidencial')
    assert memoria.eh_privado('guarda como privada')
    assert not memoria.eh_privado('o carro é prateado')
