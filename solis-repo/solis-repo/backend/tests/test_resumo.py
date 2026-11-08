"""Conversa longa: o começo vira resumo, sem buraco entre o resumo e o fim."""
import asyncio

from solis import banco, ollama, resumo


def conversa_de(n: int) -> int:
    cid = banco.nova_conversa()
    for i in range(n):
        banco.adicionar(cid, 'pessoa' if i % 2 == 0 else 'solis', f'mensagem {i}')
    return cid


def resume_com(monkeypatch, texto='- resumo'):
    pedidos = []

    async def falso(modelo, instrucao, pedido, **_):
        pedidos.append(pedido)
        return texto
    monkeypatch.setattr(ollama, 'responder_texto', falso)
    return pedidos


def test_conversa_curta_nao_resume(monkeypatch):
    pedidos = resume_com(monkeypatch)
    cid = conversa_de(resumo.JANELA + resumo.LOTE)
    asyncio.run(resumo.resumir('m', cid))
    assert pedidos == [] and banco.resumo(cid) == (None, 0)


def test_passou_do_lote_resume_as_velhas_e_deixa_a_janela(monkeypatch):
    pedidos = resume_com(monkeypatch, '- decidiram usar SQLite')
    cid = conversa_de(resumo.JANELA + resumo.LOTE + 1)
    asyncio.run(resumo.resumir('m', cid))

    texto, mensagens, ate = resumo.para_o_modelo(cid)
    assert texto == '- decidiram usar SQLite'
    assert len(mensagens) == resumo.JANELA
    # Sem buraco: a primeira que vai inteira é a seguinte à última resumida.
    assert mensagens[0]['id'] == ate + 1
    # 31 mensagens: as 11 mais velhas (0 a 10) vão pro resumo, as 20 seguintes não.
    assert 'mensagem 0' in pedidos[0]
    assert pedidos[0].endswith(f'mensagem {resumo.LOTE}')
    assert f'mensagem {resumo.LOTE + 1}' not in pedidos[0]


def test_o_resumo_seguinte_parte_do_anterior(monkeypatch):
    pedidos = resume_com(monkeypatch, '- primeiro')
    cid = conversa_de(resumo.JANELA + resumo.LOTE + 1)
    asyncio.run(resumo.resumir('m', cid))
    for i in range(resumo.LOTE + 1):
        banco.adicionar(cid, 'pessoa', f'nova {i}')
    asyncio.run(resumo.resumir('m', cid))
    assert len(pedidos) == 2 and '- primeiro' in pedidos[1]
    assert 'mensagem 0' not in pedidos[1]  # o que já está no resumo não volta


def test_resumo_falhando_nao_deixa_o_historico_crescer_sem_fim():
    cid = conversa_de(100)
    asyncio.run(resumo.resumir('m', cid))  # o conftest deixa o modelo "indisponível"
    texto, mensagens, _ = resumo.para_o_modelo(cid)
    assert texto is None and len(mensagens) == resumo.JANELA + resumo.LOTE


def test_resumo_vai_no_prompt():
    s = ollama.sistema([], None, '- decidiram usar SQLite')
    assert 'Resumo do começo desta conversa' in s and '- decidiram usar SQLite' in s


# — Título ——————————————————————————————————————————————————————————————————————

def test_titulo_curto_sai_da_primeira_troca_e_fica(monkeypatch):
    pedidos = resume_com(monkeypatch, 'Título: "Sistema de NF-e da loja."\nEscolhi esse porque...')
    cid = banco.nova_conversa()
    banco.adicionar(cid, 'pessoa', 'Quais documentos eu preciso pra emitir NF-e na loja?')
    banco.adicionar(cid, 'solis', 'Certificado A1, inscrição estadual e credenciamento na SEFAZ.')
    assert asyncio.run(resumo.titular('m', cid)) == 'Sistema de NF-e da loja'
    assert banco.conversas()[0]['titulo'] == 'Sistema de NF-e da loja'
    assert 'emitir NF-e' in pedidos[0]
    # Com título, não pergunta de novo.
    assert asyncio.run(resumo.titular('m', cid)) is None and len(pedidos) == 1


def test_sem_resposta_ainda_nao_ha_titulo(monkeypatch):
    pedidos = resume_com(monkeypatch, 'Qualquer')
    cid = banco.nova_conversa()
    banco.adicionar(cid, 'pessoa', 'oi')
    assert asyncio.run(resumo.titular('m', cid)) is None and pedidos == []


def test_ollama_fora_fica_a_primeira_fala_e_tenta_de_novo_depois(monkeypatch):
    cid = banco.nova_conversa()
    banco.adicionar(cid, 'pessoa', 'Me ajuda com o plano da semana')
    banco.adicionar(cid, 'solis', 'Claro.')
    # O conftest já deixa o Ollama "fora".
    assert asyncio.run(resumo.titular('m', cid)) is None
    assert banco.conversas()[0]['titulo'] == 'Me ajuda com o plano da semana'
    resume_com(monkeypatch, 'Plano da semana')
    assert asyncio.run(resumo.titular('m', cid)) == 'Plano da semana'


def test_titulo_longo_e_cortado_numa_palavra():
    longo = 'Uma conversa muito comprida sobre ' + 'assuntos variados ' * 6
    t = resumo._limpar_titulo(longo)
    assert len(t) <= resumo.TITULO_MAX and longo.startswith(t) and not t.endswith(' ')
    assert resumo._limpar_titulo('trabalho na syngenta') == 'Trabalho na syngenta'


def test_titulo_pede_sem_raciocinio():
    # _perguntar e não responder_texto: o conftest troca o responder_texto.
    import json

    import httpx
    pedido = []

    def chat(req):
        pedido.append(json.loads(req.content))
        return httpx.Response(200, json={'message': {'content': 'Plano da semana'}})
    t = asyncio.run(ollama._perguntar('qwen3:8b', 'i', 'x', None, httpx.MockTransport(chat), pensar=False))
    assert t == 'Plano da semana' and pedido[0]['think'] is False
    # Quem não pede não manda o campo: o aprendizado e o resumo seguem iguais.
    asyncio.run(ollama._perguntar('m', 'i', 'x', None, httpx.MockTransport(chat)))
    assert 'think' not in pedido[1]
