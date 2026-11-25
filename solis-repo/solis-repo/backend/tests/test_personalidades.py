"""As personalidades (personalidades.py, 25/11/2026): Jarvis, Eva, Ed e o Assessor
com voz, jeito e memória próprios, pra qualquer cérebro."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from solis import banco, fala, main, ollama, personalidades as p, roteador


# — quem responde ——————————————————————————————————————————————————————————————————

@pytest.mark.parametrize('frase, quem', [
    # Pelo nome, do jeito que sai do Whisper.
    ('Ed, monta um treino de peito pra hoje', 'ed'),
    ('Solis, Ed, quanto de proteína eu como por dia?', 'ed'),
    ('Oi Eva, posso te contar uma coisa?', 'eva'),
    ('Jarvis, o que o Claude está fazendo agora?', 'jarvis'),
    ('Jarbas, roda os testes do projeto', 'jarvis'),
    ('Assessor, o que eu tenho amanhã?', 'assessor'),
    ('Solis, chama o Ed', 'ed'),
    ('quero falar com a Eva', 'eva'),
    ('passa pro Jarvis', 'jarvis'),
    ('volta pro Solis', 'solis'),
    # Pelo assunto, sem dizer o nome.
    ('gastei 50 no mercado', 'assessor'),
    ('quanto eu gastei esse mês?', 'assessor'),
    ('me lembra de pagar o boleto amanhã às 9', 'assessor'),
    ('marca uma reunião na sexta às 15h', 'assessor'),
    ('o que tem na minha agenda amanhã?', 'assessor'),
    ('monta um treino de perna pra mim', 'ed'),
    ('quantas calorias tem um pão francês?', 'ed'),
    ('quero emagrecer 5 kg até o fim do ano', 'ed'),
    ('treinei costas hoje e tô com dor muscular', 'ed'),
    ('tô esgotado com o meu trabalho', 'eva'),
    ('meu chefe não reconhece nada do que eu faço', 'eva'),
    ('me ajuda a montar um plano de carreira', 'eva'),
    ('como eu me preparo pra uma entrevista de emprego?', 'eva'),
    ('o deploy do site deu erro', 'jarvis'),
    ('faz um commit com o que mudou', 'jarvis'),
    ('esse código em python está lento', 'jarvis'),
    ('o site está fora do ar?', 'jarvis'),
    # O que o Solis já reconhece como rotina (os pedidos rápidos) é do Assessor;
    # no empate, o dono do assunto ganha ("tarefa" ali é palavra solta).
    ('o que eu tenho pra fazer hoje?', 'assessor'),
    ('marca dentista dia 3 às 10h', 'assessor'),
    ('lança 45 de farmácia', 'assessor'),
    ('o Claude Code travou no meio da tarefa', 'jarvis'),
    ('recebi uma proposta de emprego em outra empresa', 'eva'),
    # O geral fica com o Solis.
    ('qual é a capital da Austrália?', 'solis'),
    ('quanto está o dólar hoje?', 'solis'),
    ('que horas são?', 'solis'),
    ('abre o Spotify', 'solis'),
    ('quem ganhou o jogo do Flamengo?', 'solis'),
])
def test_quem_responde_numa_conversa_nova(frase, quem):
    assert p.quem(frase, None) == quem


def test_quem_esta_falando_continua_ate_outra_ser_chamada():
    # Sem nome e sem assunto de outra: quem estava falando continua.
    assert p.quem('e pra amanhã?', 'ed') == 'ed'
    assert p.quem('Solis, que horas são?', 'eva') == 'eva'
    assert p.quem('qual é a capital da Austrália?', 'jarvis') == 'jarvis'
    # O assunto de outra passa a vez; empate fica com quem está.
    assert p.quem('gastei 80 no cinema', 'eva') == 'assessor'
    assert p.quem('meu chefe pediu o deploy pra hoje', 'eva') == 'eva'
    assert p.quem('meu chefe pediu o deploy pra hoje', 'jarvis') == 'jarvis'
    # O "Solis" do começo é a palavra de chamar, não um chamado.
    assert p.chamado('Solis, que horas são?') is None
    assert p.chamado('Ed Sheeran é bom?') == 'ed'  # o nome no começo é chamado (raro, aceito)


def test_a_nota_diz_quem_responde_e_o_solis_nao_leva_nota():
    assert p.nota(p.SOLIS) == ''
    nota = p.nota(p.de('ed'), entrou=True)
    assert 'o Ed' in nota and 'treinador' in nota and 'Aqui é o Ed' in nota
    assert 'Aqui é' not in p.nota(p.de('ed'), entrou=False)
    # A nota não dispara as regras do roteador (pergunta de arquivo, servidor citado).
    for x in p.TODAS.values():
        assert not roteador.do_pc(p.nota(x, True))


# — pela conversa: a nota chega no cérebro, a resposta fica com quem respondeu —————

class _CerebroFalso:
    """Guarda o que cada cérebro de nuvem recebeu."""

    def __init__(self, monkeypatch, resposta='Bora: supino 4x10.'):
        self.pedidos = []

        async def abrir(nome, sistema, prompt, etapas, **_):
            self.pedidos.append(prompt)

            async def fluxo():
                yield resposta
            return fluxo()
        from solis import cerebros
        monkeypatch.setattr(cerebros, 'abrir', abrir)
        monkeypatch.setattr(cerebros, 'disponivel', lambda nome: nome == 'groq')
        monkeypatch.setattr(roteador, '_ordem', lambda: ['groq'])
        monkeypatch.setattr(roteador, 'com_corpo', lambda nome: False)


def _mandar(c, conversa, texto):
    r = c.post(f'/conversas/{conversa}/mensagens', json={'texto': texto})
    return [json.loads(l) for l in r.text.splitlines() if l]


def test_pela_conversa_o_ed_responde_com_o_jeito_dele_e_fica_na_conversa(monkeypatch):
    falso = _CerebroFalso(monkeypatch)
    c = TestClient(main.app)
    conversa = c.post('/conversas').json()['id']
    linhas = _mandar(c, conversa, 'Ed, monta um treino de peito')
    [etapa] = [l for l in linhas if l.get('etapa') == 'personalidade']
    assert (etapa['quem'], etapa['nome'], etapa['entrou']) == ('ed', 'Ed', True)
    assert 'Quem responde agora é o Ed' in falso.pedidos[0] and 'Aqui é o Ed' in falso.pedidos[0]
    # A segunda, sem nome: ainda o Ed, sem se apresentar de novo.
    _mandar(c, conversa, 'e quantas séries de cada?')
    assert 'Quem responde agora é o Ed' in falso.pedidos[1] and 'Aqui é o Ed' not in falso.pedidos[1]
    # O histórico mostra pro cérebro quem disse o quê.
    assert 'Ed (do Solis): Bora: supino 4x10.' in falso.pedidos[1]
    assert [m.get('personalidade') for m in banco.mensagens(conversa)] == [None, 'ed', None, 'ed']
    assert banco.personalidade_da_conversa(conversa) == 'ed'
    # Fica no banco só o que ele escreveu (a nota vai só pro cérebro).
    assert banco.mensagens(conversa)[0]['texto'] == 'Ed, monta um treino de peito'


def test_o_lancamento_rapido_e_do_assessor(monkeypatch):
    _CerebroFalso(monkeypatch)
    c = TestClient(main.app)
    conversa = c.post('/conversas').json()['id']
    _mandar(c, conversa, 'gastei 50 no mercado')
    assert banco.mensagens(conversa)[-1]['personalidade'] == 'assessor'


def test_o_local_recebe_a_nota_no_sistema_e_o_estilo_tambem(monkeypatch):
    """O local recebe o histórico, não a mensagem com as notas: antes, o estilo
    escolhido nunca chegava nele."""
    vistos = {}

    async def conversar(modelo, historico, *a, projeto='', **k):
        vistos['projeto'] = projeto

        async def fluxo():
            yield 'ok'
        return fluxo()
    monkeypatch.setattr(ollama, 'conversar', conversar)
    asyncio.run(roteador.responder(['local'], 'qwen3:8b', banco.nova_conversa(), [], [], [], None, 'oi',
                                   notas='[NOTA DO JEITO]'))
    assert vistos['projeto'].endswith('[NOTA DO JEITO]')


# — a memória: cada um escreve na sua área, todos leem ——————————————————————————————

def test_a_memoria_fica_na_area_de_quem_aprendeu_e_aparece_marcada():
    banco.adicionar_memoria('Treina 4 vezes por semana.', 'Treino', False, None, area='ed')
    banco.adicionar_memoria('Mora em Uberlândia.', 'Pessoal', False, None)
    por_texto = {m['texto']: m['area'] for m in banco.memorias()}
    assert por_texto == {'Treina 4 vezes por semana.': 'ed', 'Mora em Uberlândia.': None}
    texto = ollama.contexto(banco.memorias())
    assert '- Treina 4 vezes por semana. (anotada pelo Ed)' in texto and '- Mora em Uberlândia.\n' in texto + '\n'


def test_o_aprendizado_grava_na_area_de_quem_respondeu(monkeypatch):
    from solis import memoria

    async def extrair(*a, **k):
        return {'memorias': [{'texto': 'Está com 82 kg.', 'tema': 'Saúde'}]}

    async def parecidas(*a, **k):
        return []
    monkeypatch.setattr(memoria, 'extrair', extrair)
    monkeypatch.setattr(memoria.busca, 'memorias_parecidas', parecidas)
    asyncio.run(memoria.aprender('qwen3:8b', banco.nova_conversa(), 'tô com 82 kg', [], area='ed'))
    [m] = banco.memorias()
    assert (m['texto'], m['area']) == ('Está com 82 kg.', 'ed')


# — a voz de cada um ————————————————————————————————————————————————————————————————

def _cadeia_falsa(monkeypatch, falha=()):
    ouvidas = []

    def voz(nome):
        async def f(texto, lingua_, voz=None, **_):
            ouvidas.append((nome, voz))
            if nome in falha:
                raise fala.SemVoz('cota')
            return nome.encode()
        return f
    monkeypatch.setattr(fala, 'NUVEM', [('fish', 'audio/mpeg', voz('fish')), ('gemini', 'audio/wav', voz('gemini')),
                                        ('ava', 'audio/mpeg', voz('ava'))])
    monkeypatch.setattr(fala, 'LOCAL', [('kokoro', 'audio/wav', voz('kokoro'))])
    fala._cache.clear()
    fala._fora_ate.clear()
    return ouvidas


def test_cada_um_fala_na_voz_dele_em_cada_camada(monkeypatch):
    ouvidas = _cadeia_falsa(monkeypatch, falha=('gemini', 'ava'))
    asyncio.run(fala.falar('Bora treinar.', quem='ed'))
    # A Fish (a voz do Solis) fica de fora: com ela, as quatro soariam iguais.
    assert ouvidas == [('gemini', 'Fenrir'), ('ava', 'pt-BR-AntonioNeural'), ('kokoro', ('pm_santa', 1.05))]
    ouvidas.clear()
    asyncio.run(fala.falar('Oi.', quem='solis'))
    assert ouvidas[0] == ('fish', None)  # o Solis segue com a cadeia de sempre


def test_sem_quem_a_voz_e_de_quem_esta_falando_na_conversa(monkeypatch):
    ouvidas = _cadeia_falsa(monkeypatch)
    conversa = banco.nova_conversa()
    banco.guardar_personalidade(conversa, 'eva')
    asyncio.run(fala.falar('Te entendo.', conversa))
    assert ouvidas == [('gemini', 'Sulafat')]


def test_aos_pedacos_a_voz_g_e_a_da_personalidade(monkeypatch):
    vozes = []

    async def g(texto, chave, voz=None):
        vozes.append(voz)

        async def pedacos():
            yield b'mp3'
        return pedacos()
    monkeypatch.setattr(fala, '_gemini_aos_pedacos', g)
    fala._fora_ate.clear()
    fala._cache.clear()
    _, _, quem = asyncio.run(fala.falar_aos_pedacos('Anotado.', quem='assessor'))
    assert (quem, vozes) == ('gemini-flash', ['Schedar'])


def test_a_frase_fixa_e_gravada_na_voz_de_cada_um():
    assert fala._arquivo_da_frase('pesquisa', 'mp3', 'ed') != fala._arquivo_da_frase('pesquisa', 'mp3', 'eva')
    assert fala._arquivo_da_frase('pesquisa', 'mp3') == fala._arquivo_da_frase('pesquisa', 'mp3', 'solis')


def test_as_vozes_sao_todas_diferentes_em_cada_camada():
    """Reconhecer quem fala sem olhar a tela: nenhuma voz repetida no Gemini nem no
    Edge. No PC só há 3 vozes em português pras 5 (a diferença é a velocidade)."""
    todas = list(p.TODAS.values())
    assert len({x.gemini for x in todas}) == len(todas)
    assert len({x.edge for x in todas}) == len(todas)
    assert len({x.kokoro for x in todas}) == len(todas)
    assert all(x.gemini in fala.VOZES_GEMINI for x in todas)


# — ao vivo: a sessão do Gemini Live na voz de quem responde ———————————————————————————

def test_ao_vivo_a_sessao_abre_na_voz_de_quem_responde(monkeypatch):
    from test_pedido_ao_vivo import GeminiFalso, _chamar, _escuta
    _escuta(monkeypatch, texto='Ed, me dá uma dica de treino')
    conversa = banco.nova_conversa()
    with TestClient(main.app).websocket_connect('/escuta') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'conversa': conversa, 'falar': True}))
        _chamar(ws)
        assert ws.receive_json()['quem'] == 'ed'
        ws.receive_json()
        ws.receive_bytes()
        assert ws.receive_json()['quem'] == 'ed'
    # A do "Solis" abriu na voz do Solis; o pedido chamou o Ed, e abriu outra na voz dele.
    assert [(g.voz, g.quem) for g in GeminiFalso.criadas] == [('Aoede', 'solis'), ('Fenrir', 'ed')]
    assert GeminiFalso.criadas[0].fechada and GeminiFalso.criadas[1].entrou
    assert banco.personalidade_da_conversa(conversa) == 'ed'
    assert banco.mensagens(conversa)[-1]['personalidade'] == 'ed'


def test_ao_vivo_o_sistema_leva_o_jeito_dela():
    from solis import pedido_ao_vivo
    s = pedido_ao_vivo.sistema(None, 'eva', entrou=True)
    assert 'Quem responde agora é a Eva' in s and 'Aqui é a Eva' in s
    assert 'Quem responde' not in pedido_ao_vivo.sistema(None)
