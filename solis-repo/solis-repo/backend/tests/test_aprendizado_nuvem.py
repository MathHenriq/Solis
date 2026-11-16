"""O aprendizado na Groq quando o Ollama está fora (decisão do Matheus,
16/11/2026): só o que não é privado, e sem o privado no que vai junto. E o
teste do aprendizado, que mede sem guardar nada."""
import asyncio
import json

import httpx

from solis import aprendizado_teste, apis, banco, busca, cerebros, cofre, memoria, ollama, roteador


def com_groq():
    banco.guardar_ajuste('chave:groq', cofre.selar('gsk_x'))
    banco.guardar_ajuste('modelo:groq', 'openai/gpt-oss-120b')
    cerebros._fora_ate.pop('groq', None)


def groq_falsa(monkeypatch, resposta: dict):
    """Troca a chamada JSON da Groq; devolve a lista do que ela recebeu."""
    pedidos = []

    async def responder_json(nome, sistema, prompt, esquema, qual=None, transporte=None):
        pedidos.append({'nome': nome, 'prompt': prompt, 'qual': qual})
        return resposta
    monkeypatch.setattr(apis, 'responder_json', responder_json)
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: True)
    return pedidos


def aprender(mensagem, contexto=(), mensagem_id=None, conversa=None):
    conversa = conversa or banco.nova_conversa()
    return asyncio.run(memoria.aprender('', conversa, mensagem, list(contexto), mensagem_id))


def test_ollama_fora_aprende_na_groq_sem_o_privado(monkeypatch):
    com_groq()
    publica = banco.adicionar_memoria('Mora em Campinas.', 'Casa', False, None)
    banco.adicionar_memoria('Faz terapia às quintas.', 'Saúde', False, None, privada=True)

    async def parecidas(texto, quantas):
        return banco.memorias()
    monkeypatch.setattr(busca, 'memorias_parecidas', parecidas)
    pedidos = groq_falsa(monkeypatch, {'memorias': [{'texto': 'Mora em Curitiba.', 'tema': 'Casa', 'privada': False,
                                                     'substitui': publica}], 'tarefas': [], 'compromissos': []})
    contexto = [{'papel': 'pessoa', 'texto': 'meu segredo é X', 'privada': True},
                {'papel': 'solis', 'texto': 'Certo.', 'privada': False}]
    novas = aprender('Me mudei pra Curitiba.', contexto)
    assert novas == ['Mora em Curitiba.']
    [p] = pedidos
    assert p['nome'] == 'groq' and p['qual'] == memoria.MODELO_NUVEM
    # Nada privado foi junto: nem a memória, nem a fala de antes.
    assert 'terapia' not in p['prompt'] and 'segredo' not in p['prompt'] and 'Campinas' in p['prompt']
    textos = [m['texto'] for m in banco.memorias()]
    assert 'Mora em Curitiba.' in textos and 'Mora em Campinas.' not in textos


def test_mensagem_privada_nao_vai_pra_groq(monkeypatch):
    com_groq()
    pedidos = groq_falsa(monkeypatch, {'memorias': [{'texto': 'x', 'tema': 'y', 'privada': False, 'substitui': 0}]})
    assert aprender('Isso é privado: minha senha do banco é 1234.') == []
    cid = banco.nova_conversa()
    mid = banco.adicionar(cid, 'pessoa', 'Meu salário é tal.', privada=True)
    assert aprender('Meu salário é tal.', mensagem_id=mid, conversa=cid) == []
    assert pedidos == []


def test_sem_a_groq_nada_e_aprendido(monkeypatch):
    pedidos = groq_falsa(monkeypatch, {'memorias': [{'texto': 'x', 'tema': 'y', 'privada': False, 'substitui': 0}]})
    assert aprender('Eu trabalho com dados.') == []  # sem a chave
    com_groq()
    cerebros.pausar('groq', motivo='o limite grátis acabou')
    assert aprender('Eu trabalho com dados.') == []  # pausada
    assert pedidos == []


def test_com_a_groq_aprendendo_o_aviso_de_desligado_sai(monkeypatch):
    monkeypatch.setattr(ollama, '_fora', True)
    monkeypatch.setattr(cerebros, 'instalado', lambda nome: True)
    assert roteador.NOTA_SEM_APRENDIZADO in roteador.notas_do_cerebro('gemini', [])
    com_groq()
    assert memoria.aprende_agora()
    assert roteador.NOTA_SEM_APRENDIZADO not in roteador.notas_do_cerebro('gemini', [])


def test_responder_json_espera_o_limite_e_refaz_o_json_que_saiu_do_esquema(monkeypatch):
    com_groq()
    monkeypatch.setattr(apis, 'FUNDO_ESPERA_MAX', 0.01)
    respostas = iter([
        httpx.Response(429, headers={'retry-after': '0'}),
        httpx.Response(400, text='{"error":{"code":"json_validate_failed"}}'),
        httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'memorias': []})}}]}),
    ])
    corpos = []

    def rota(req):
        corpos.append(json.loads(req.content))
        return next(respostas)
    r = asyncio.run(apis.responder_json('groq', 's', 'p', {'type': 'object'}, qual='openai/gpt-oss-20b',
                                        transporte=httpx.MockTransport(rota)))
    assert r == {'memorias': []} and len(corpos) == 3
    assert corpos[0]['model'] == 'openai/gpt-oss-20b'
    assert corpos[0]['response_format']['type'] == 'json_schema'
    # O limite do fundo não pausa a Groq da conversa.
    assert cerebros.disponivel('groq') or not cerebros.instalado('groq')


def test_o_teste_do_aprendizado_pontua_sem_guardar(monkeypatch):
    async def extrair(onde, modelo, mensagem, candidatas, contexto, agora, antiga=None, pedido=False):
        return {'memorias': [], 'tarefas': [], 'compromissos': []}
    monkeypatch.setattr(memoria, 'extrair', extrair)
    r = asyncio.run(aprendizado_teste.medir('groq', 'm'))
    # "nada" passa; quem esperava algo falha — e nada foi guardado.
    nada = sum(1 for _, _, e in aprendizado_teste.CASOS if e.get('nada'))
    assert r['resumo']['certos'] == nada and banco.memorias() == []


def test_pontuar_confere_substituicao_dia_e_sigilo():
    p = aprendizado_teste.pontuar
    assert p({'memoria': ['curitiba'], 'substitui': 7},
             {'memorias': [{'texto': 'Mora em Curitiba.', 'substitui': 7}]})[0]
    assert not p({'memoria': ['curitiba'], 'substitui': 7},
                 {'memorias': [{'texto': 'Mora em Curitiba.', 'substitui': 0}]})[0]
    assert not p({'compromisso': (['dentista'], '2026-11-17', '15:00')},
                 {'compromissos': [{'titulo': 'Dentista', 'dia': '2026-11-18', 'hora': '15:00'}]})[0]
    assert not p({'memoria': ['diabetes'], 'privada': True},
                 {'memorias': [{'texto': 'Tem diabetes.', 'privada': False}]})[0]
    assert not p({'nada': True}, {'tarefas': [{'texto': 'algo'}]})[0]
