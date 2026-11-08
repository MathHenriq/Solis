"""Extração e uso das memórias, com o Ollama trocado por respostas fixas."""
import asyncio
import json

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
    # Devolve o que guardou: é o texto do "Memória guardada" na tela.
    assert asyncio.run(memoria.aprender('m', None, 'Trabalho na Syngenta faz dois anos', [])) == ['Trabalha na Syngenta.']
    assert textos() == [('Trabalha na Syngenta.', 'Trabalho', False)]


def test_nao_duplica_o_que_ja_sabe(monkeypatch):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    perguntas = responde(monkeypatch, [{'texto': 'trabalha na syngenta', 'tema': 'Trabalho'}])
    assert asyncio.run(memoria.aprender('m', None, 'na Syngenta, como eu disse', [])) == []
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
    assert asyncio.run(memoria.aprender('m', None, 'Anote: minha cor preferida é verde', [])) == [
        'Anote: minha cor preferida é verde'
    ]
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
    assert json.loads(r.text.splitlines()[-1])['erro'] == 'ollama_indisponivel'
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


def test_memoria_que_mudou_substitui_a_antiga_sem_apagar(monkeypatch):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    [antiga] = banco.memorias()
    perguntas = responde(monkeypatch, [
        {'texto': 'Trabalha na Vale.', 'tema': 'Trabalho', 'privada': False, 'substitui': antiga['id']},
    ])
    asyncio.run(memoria.aprender('m', None, 'saí da Syngenta, agora trabalho na Vale', []))

    assert [m['texto'] for m in banco.memorias()] == ['Trabalha na Vale.']
    # O modelo viu a antiga com o número dela.
    assert f'{antiga["id"]}: Trabalha na Syngenta.' in perguntas[0]
    # E ela continua no banco, marcada — se a substituição foi engano, dá pra voltar.
    linha = banco._con().execute('SELECT substituida_por FROM memorias WHERE id = ?', (antiga['id'],)).fetchone()
    assert linha['substituida_por'] is not None


def test_numero_que_o_modelo_nao_viu_nao_substitui_nada(monkeypatch):
    banco.adicionar_memoria('Gosta de chá.', 'Preferências', False, None)
    responde(monkeypatch, [{'texto': 'Mora em Campinas.', 'tema': 'Casa', 'privada': False, 'substitui': 999}])
    asyncio.run(memoria.aprender('m', None, 'moro em Campinas', []))
    assert {m['texto'] for m in banco.memorias()} == {'Gosta de chá.', 'Mora em Campinas.'}


def test_atualizar_memoria_privada_continua_privada(monkeypatch):
    banco.adicionar_memoria('Toma remédio X.', 'Saúde', False, None, privada=True)
    [antiga] = banco.memorias()
    responde(monkeypatch, [{'texto': 'Toma remédio Y.', 'tema': 'Saúde', 'privada': False, 'substitui': antiga['id']}])
    asyncio.run(memoria.aprender('m', None, 'troquei o remédio pelo Y', []))
    [nova] = banco.memorias()
    assert nova['texto'] == 'Toma remédio Y.' and nova['privada']


def test_pedido_nao_e_atendido_por_memoria_repetida_de_outro_assunto(monkeypatch):
    """O llama3.2:3b devolvia uma memória guardada qualquer, e o pedido se perdia."""
    banco.adicionar_memoria('Tem uma loja e quer emitir NF-e.', 'Trabalho', False, None)
    responde(monkeypatch, [{'texto': 'Tem uma loja e quer emitir NF-e.', 'tema': 'Trabalho'}])
    novas = asyncio.run(memoria.aprender('m', None, 'grave: minha cor preferida é verde', []))
    assert novas == ['grave: minha cor preferida é verde']
    assert ('grave: minha cor preferida é verde', memoria.TEMA_PEDIDO, True) in textos()


def test_pedido_de_algo_que_ja_sabia_esta_atendido(monkeypatch):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    responde(monkeypatch, [{'texto': 'Trabalha na Syngenta.', 'tema': 'Trabalho'}])
    assert asyncio.run(memoria.aprender('m', None, 'grave que eu trabalho na Syngenta', [])) == []
    assert len(banco.memorias()) == 1


def test_o_que_conta_como_falar_do_pedido():
    assert memoria._fala_de('Trabalha na Syngenta.', 'anote: entrei na Syngenta')
    assert not memoria._fala_de('Prefere respostas curtas.', 'grave: minha cor preferida é verde')
    # Verbo de pedido e palavra vazia não contam como assunto.
    assert not memoria._fala_de('Grave isso sobre a loja.', 'grave isso sobre o carro')


# — Busca textual (FTS5) ————————————————————————————————————————————————————————

def test_busca_sem_acento_por_prefixo_e_todas_as_palavras():
    a = banco.adicionar_memoria('Trabalha na Syngenta como analista.', 'Trabalho', False, None)
    b = banco.adicionar_memoria('Prefere respostas curtas, em tópicos.', 'Preferências de comunicação', False, None)
    banco.adicionar_memoria('Mora em Campinas.', 'Moradia', False, None)
    ids = lambda q: [m['id'] for m in banco.buscar_memorias(q)]
    assert ids('synge') == [a]
    assert ids('TOPICOS') == [b]                 # sem acento e sem caixa
    assert ids('comunicacao') == [b]             # o tema também conta
    assert ids('analista syngenta') == [a]       # todas as palavras
    assert ids('analista campinas') == []
    assert len(ids('')) == 3                     # sem palavra: todas


def test_busca_deixa_de_fora_a_substituida_e_a_apagada():
    velha = banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    nova = banco.adicionar_memoria('Trabalha na Vale.', 'Trabalho', False, None, substitui=velha)
    assert [m['id'] for m in banco.buscar_memorias('trabalha')] == [nova]
    banco.apagar_memoria(nova)
    assert banco.buscar_memorias('vale') == []
    # Esquecida a nova, a antiga volta a valer.
    assert [m['id'] for m in banco.buscar_memorias('trabalha')] == [velha]


def test_busca_com_aspas_e_simbolos_nao_quebra():
    banco.adicionar_memoria('Estuda C++ e "Python".', 'Estudos', False, None)
    assert len(banco.buscar_memorias('"python')) == 1
    assert len(banco.buscar_memorias('c++ AND OR NOT')) == 0  # operadores viram texto
    assert banco.buscar_memorias('***') == banco.memorias()


def test_memoria_de_antes_da_migracao_entra_no_indice(tmp_path):
    import sqlite3
    caminho = tmp_path / 'antigo.db'
    with sqlite3.connect(caminho) as c:
        c.executescript(banco.ESQUEMA)
        for sql in banco.MIGRACOES[:4]:
            c.executescript(sql)
        c.execute("INSERT INTO memorias (texto, tema, criada) VALUES ('Mora em Sorocaba.', 'Moradia', '2026-11-01')")
        c.execute('PRAGMA user_version = 4')
    banco.usar(caminho)
    assert [m['texto'] for m in banco.buscar_memorias('sorocaba')] == ['Mora em Sorocaba.']


def test_rota_busca_memorias():
    banco.adicionar_memoria('Mora em Campinas.', 'Moradia', False, None)
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    cliente = TestClient(main.app)
    assert [m['texto'] for m in cliente.get('/memorias', params={'q': 'campi'}).json()['memorias']] == ['Mora em Campinas.']
    assert len(cliente.get('/memorias').json()['memorias']) == 2


def test_esquecer_a_nova_devolve_a_antiga():
    velha = banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    nova = banco.adicionar_memoria('Trabalha na Vale.', 'Trabalho', False, None, substitui=velha)
    assert [m['id'] for m in banco.memorias()] == [nova]
    assert TestClient(main.app).delete(f'/memorias/{nova}').json() == {'ok': True}
    assert [m['id'] for m in banco.memorias()] == [velha]
