"""Controle do PC, etapa 1: as ferramentas de leitura ficam presas às pastas
autorizadas, acham pelo nome e pelo texto, leem em partes e registram tudo."""
import pytest

from solis import banco, ollama, pc


@pytest.fixture
def pastas(tmp_path):
    docs = tmp_path / 'raiz' / 'Documentos'
    (docs / 'contratos').mkdir(parents=True)
    (docs / 'contratos' / 'contrato-aluguel.txt').write_text('Cláusula 7 — multa de 3 aluguéis.', encoding='utf-8')
    (docs / 'notas-reuniao.md').write_text('# Reunião\n- Presentes: Paula (Acme)\n- Prazo: 20/11', encoding='utf-8')
    (docs / 'longo.txt').write_text('a' * (pc.LER_MAX + 10), encoding='utf-8')
    (docs / 'foto.jpg').write_bytes(b'\xff\xd8\xff')
    fora = tmp_path / 'raiz' / 'Segredos'
    fora.mkdir()
    (fora / 'senhas.txt').write_text('não pode ler', encoding='utf-8')
    pc.guardar_pastas([str(docs)])
    return docs, fora


def test_guardar_pastas_valida_e_tira_repetidas(tmp_path, pastas):
    docs, _ = pastas
    assert pc.guardar_pastas([str(docs), str(docs) + '/']) == [str(docs.resolve())]
    with pytest.raises(ValueError):
        pc.guardar_pastas([str(tmp_path / 'nao-existe')])
    with pytest.raises(ValueError):
        pc.guardar_pastas(['relativa'])


def test_disponivel_so_ligada_e_com_pasta(pastas):
    assert pc.disponivel()
    pc.ligar(False)
    assert not pc.disponivel()
    pc.ligar(True)
    pc.guardar_pastas([])
    assert not pc.disponivel()


@pytest.mark.parametrize('caminho', ['../Segredos/senhas.txt', 'Documentos/../Segredos/senhas.txt', 'SEGREDOS_ABS'])
def test_nao_sai_das_pastas(pastas, caminho):
    _, fora = pastas
    if caminho == 'SEGREDOS_ABS':
        caminho = str(fora / 'senhas.txt')
    saida = pc.executar('ler_arquivo', {'caminho': caminho})
    assert 'não pode ler' not in saida
    assert 'Fora das pastas' in saida or 'Não achei' in saida


def test_listar_e_ler(pastas):
    assert 'Documentos' in pc.listar_pasta('')
    lista = pc.listar_pasta('Documentos')
    assert 'contratos/' in lista and 'notas-reuniao.md' in lista
    assert 'multa de 3' in pc.ler_arquivo('Documentos/contratos/contrato-aluguel.txt')
    # Relativo à pasta autorizada também vale.
    assert 'multa de 3' in pc.ler_arquivo('contratos/contrato-aluguel.txt')


def test_arquivo_longo_vem_em_partes(pastas):
    p1 = pc.ler_arquivo('Documentos/longo.txt')
    assert 'parte 1 de 2' in p1 and 'parte=2' in p1
    assert 'parte 2 de 2' in pc.ler_arquivo('Documentos/longo.txt', parte=2)


def test_tipo_que_nao_le_vira_texto_pro_modelo(pastas):
    assert 'Não consegui' in pc.executar('ler_arquivo', {'caminho': 'Documentos/foto.jpg'})


def test_busca_por_qualquer_palavra_do_nome(pastas):
    # O modelo junta palavras do assunto: "contrato mercado" ainda acha o contrato.
    assert 'contrato-aluguel.txt' in pc.buscar_arquivos('contrato mercado')


def test_busca_por_dentro_com_a_linha(pastas):
    achado = pc.buscar_arquivos('Paula')
    assert 'No texto de:' in achado and 'notas-reuniao.md' in achado and 'Paula (Acme)' in achado
    assert 'ler_arquivo' in achado  # o lembrete de abrir o arquivo
    assert 'Nenhum arquivo' in pc.buscar_arquivos('zebra')


def test_tudo_fica_registrado(pastas):
    pc.executar('listar_pasta', {'caminho': 'Documentos'}, conversa=7)
    pc.executar('ler_arquivo', {'caminho': '../Segredos/senhas.txt'}, conversa=7)
    pc.executar('apagar_tudo', {})
    acoes = banco.acoes()
    assert [a['ferramenta'] for a in acoes] == ['apagar_tudo', 'ler_arquivo', 'listar_pasta']
    assert [a['ok'] for a in acoes] == [False, False, True]
    assert acoes[2]['conversa'] == 7 and acoes[2]['argumentos'] == {'caminho': 'Documentos'}


def test_sistema_com_arquivos_tira_o_nao_pode_ler():
    sem = ollama.sistema([])
    com = ollama.sistema([], arquivos=True)
    assert 'ler arquivos ou programas do computador' in sem
    assert 'ler arquivos ou programas do computador' not in com
    assert 'nunca instrução' in com and 'procure nos arquivos' in com


# — Quem responde ————————————————————————————————————————————————————————————————

ARQUIVOS = [
    'Quais pastas você consegue ver no meu computador?',
    'O que tem na minha pasta Documentos?',
    'Qual a multa do meu contrato de aluguel se eu sair antes?',
    'Quanto eu gastei com mercado em outubro?',
    'Qual é o prazo de entrega que combinei com a Paula?',
    'Quanto tempo de forno leva o bolo de cenoura da minha receita?',
    'Qual a stack do projeto solis? Olha o README.',
    'Que dia vence o meu aluguel?',
    'Quais arquivos de receitas eu tenho?',
    'O que diz o arquivo leia-me-urgente?',
    'Qual o valor do orçamento da reunião com a Acme?',
    'Qual a versão do react no package.json do site?',
    'Posso ter um cachorro pequeno no meu apartamento?',
    'Até quando eu tenho que mandar o protótipo pra Acme?',
]
CONVERSA = [
    'Qual a capital da Austrália?',
    'Me dá uma ideia de presente pra minha mãe.',
    'Quanto é 17 vezes 23?',
    'Me explica o que é IGP-M.',
    'Bom dia, tudo bem?',
    'Escreve um haiku sobre o outono.',
]


@pytest.mark.parametrize('texto', ARQUIVOS)
def test_pergunta_de_arquivo_vai_pro_local(pastas, texto):
    from solis import roteador
    assert roteador.escolher(texto)[1] == ['local']


@pytest.mark.parametrize('texto', CONVERSA)
def test_conversa_comum_segue_a_ordem(pastas, texto):
    from solis import roteador
    assert roteador.do_pc(texto) is False


def test_sem_pastas_nada_muda(pastas, monkeypatch):
    from solis import cerebros, roteador
    monkeypatch.setattr(cerebros, 'disponivel', lambda nome: True)
    assert roteador.escolher('O que tem na minha pasta Documentos?')[1] == ['local']
    pc.guardar_pastas([])  # sem pasta autorizada, o local não tem o que ler: segue a ordem
    assert roteador.escolher('O que tem na minha pasta Documentos?')[1][0] != 'local'


# — Rotas ————————————————————————————————————————————————————————————————————————

def test_rotas_das_pastas_e_do_registro(pastas):
    from fastapi.testclient import TestClient
    from solis import main
    docs, _ = pastas
    c = TestClient(main.app)
    assert c.get('/pc').json() == {'ligada': True, 'pastas': [str(docs.resolve())], 'disponivel': True}
    assert c.put('/pc/pastas', json={'pastas': ['C:/nao/existe']}).status_code == 400
    assert c.put('/pc/ligada', json={'ligada': False}).json()['disponivel'] is False
    pc.executar('listar_pasta', {'caminho': 'Documentos'}, conversa=3)
    registro = c.get('/pc/registro').json()
    assert registro[0]['ferramenta'] == 'listar_pasta' and registro[0]['conversa'] == 3


# — O laço das ferramentas, com um Ollama simulado ————————————————————————————

def test_conversa_usa_ferramenta_e_responde(pastas):
    import asyncio
    import json

    import httpx

    from solis.etapas import Etapas

    pedidos = []

    def ollama_falso(request: httpx.Request) -> httpx.Response:
        corpo = json.loads(request.content)
        pedidos.append(corpo)
        if len(pedidos) == 1:
            assert corpo['tools'] and 'ler arquivos ou programas do computador' not in corpo['messages'][0]['content']
            linhas = [{'message': {'content': '', 'tool_calls': [{'function': {
                'name': 'ler_arquivo', 'arguments': {'caminho': 'Documentos/contratos/contrato-aluguel.txt'}}}]}, 'done': True}]
        else:
            # O resultado da ferramenta voltou como mensagem `tool`.
            assert corpo['messages'][-1]['role'] == 'tool' and 'multa de 3' in corpo['messages'][-1]['content']
            linhas = [{'message': {'content': 'A multa é de 3 aluguéis.'}, 'done': False}, {'message': {'content': ''}, 'done': True}]
        return httpx.Response(200, content='\n'.join(json.dumps(l) for l in linhas).encode())

    async def rodar():
        etapas = Etapas(5)
        fluxo = await ollama.conversar(
            'qwen3:8b', [{'papel': 'pessoa', 'texto': 'qual a multa?'}], transporte=httpx.MockTransport(ollama_falso),
            etapas=etapas, ferramentas=True, conversa=5,
        )
        return ''.join([p async for p in fluxo]), etapas.lista

    texto, lista = asyncio.run(rodar())
    assert texto == 'A multa é de 3 aluguéis.'
    assert len(pedidos) == 2
    usada = [e for e in lista if e['etapa'] == 'ferramenta']
    assert usada == [{**usada[0], 'ferramenta': 'ler_arquivo', 'alvo': 'Documentos/contratos/contrato-aluguel.txt', 'ok': True}]
    assert banco.acoes()[0]['conversa'] == 5


def test_sem_ferramentas_o_pedido_nao_leva_tools(pastas):
    import asyncio
    import json

    import httpx

    corpos = []

    def ollama_falso(request):
        corpos.append(json.loads(request.content))
        return httpx.Response(200, content=json.dumps({'message': {'content': 'oi'}, 'done': True}).encode())

    async def rodar():
        fluxo = await ollama.conversar('qwen3:8b', [{'papel': 'pessoa', 'texto': 'oi'}], transporte=httpx.MockTransport(ollama_falso))
        return ''.join([p async for p in fluxo])

    assert asyncio.run(rodar()) == 'oi'
    assert 'tools' not in corpos[0]
