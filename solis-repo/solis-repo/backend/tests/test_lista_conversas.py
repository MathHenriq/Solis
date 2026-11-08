"""A lista de conversas do painel e voltar a uma conversa antiga."""
from fastapi.testclient import TestClient

from solis import banco, main


def conversa(*falas, titulo=None, origem='solis'):
    cid = banco.nova_conversa(origem=origem, titulo=titulo)
    for f in falas:
        banco.adicionar(cid, 'pessoa', f)
        banco.adicionar(cid, 'solis', 'ok')
    return cid


def test_lista_da_mais_recente_e_deixa_de_fora_as_vazias_e_importadas():
    a = conversa('Quais documentos eu preciso pra emitir NF-e na loja?')
    b = conversa('Estudos de pandas e SQL')
    banco.nova_conversa()  # criada e nunca usada
    conversa('Uma conversa do ChatGPT', titulo='Do ChatGPT', origem='chatgpt')
    lista = TestClient(main.app).get('/conversas').json()['conversas']
    assert [c['id'] for c in lista] == [b, a]
    assert lista[1]['titulo'] == 'Quais documentos eu preciso pra emitir NF-e na loja?'
    assert lista[0]['atualizada']


def test_continuar_uma_antiga_a_traz_pro_topo_e_ela_vira_a_atual():
    a = conversa('primeira')
    b = conversa('segunda')
    assert banco.ultima_conversa() == b
    banco.adicionar(a, 'pessoa', 'voltei nesta')
    assert banco.ultima_conversa() == a
    assert [c['id'] for c in banco.conversas()] == [a, b]


def test_titulo_numa_linha_e_cortado_numa_palavra():
    longo = 'Me ajuda a\n\nplanejar ' + 'a semana inteira de estudos ' * 5
    conversa(longo)
    [c] = banco.conversas()
    assert '\n' not in c['titulo'] and len(c['titulo']) <= banco.TITULO_MAX
    assert c['titulo'].startswith('Me ajuda a planejar a semana') and not c['titulo'].endswith(' ')


def test_busca_no_titulo_e_no_texto_sem_curinga():
    a = conversa('Sistema de NF-e da loja')
    b = conversa('Receita de pão', 'quanto de fermento? uns 50% do peso')
    cliente = TestClient(main.app)
    ids = lambda q: [c['id'] for c in cliente.get('/conversas', params={'q': q}).json()['conversas']]
    assert ids('nf-e') == [a]
    assert ids('FERMENTO') == [b]
    assert ids('50%') == [b]
    assert ids('5_%') == []  # o _ é letra, não curinga


def test_abrir_uma_conversa_antiga():
    a = conversa('primeira')
    conversa('segunda')
    cliente = TestClient(main.app)
    r = cliente.get(f'/conversas/{a}').json()
    assert r['id'] == a and [m['texto'] for m in r['mensagens']] == ['primeira', 'ok']
    assert cliente.get('/conversas/999').status_code == 404
    # A rota da atual continua respondendo (não é confundida com um id).
    assert cliente.get('/conversas/atual').status_code == 200
