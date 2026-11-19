"""O modelo local com o corpo do Solis (roteador._corpo_local): o meio-termo
medido em 19/11/2026 — as do Solis e o terminal nos pedidos que não são de
arquivo, só pros modelos que passaram (o qwen3:8b). Ollama simulado."""
import asyncio
import json

import httpx

from solis import banco, corpo, ollama, pc, roteador
from solis.etapas import Etapas


def _responder_local(monkeypatch, modelo, mensagem):
    vistos = {}

    async def conversar(m, historico, memorias, trechos, resumo, **kw):
        vistos.update(kw, modelo=m)

        async def gen():
            yield 'ok'
        return gen()
    monkeypatch.setattr(ollama, 'conversar', conversar)

    async def ir():
        fluxo, _ = await roteador.responder(['local'], modelo, 1, [], [], [], None, mensagem)
        return ''.join([p async for p in fluxo])
    asyncio.run(ir())
    return vistos


def test_o_qwen_recebe_o_corpo_sem_arquivo_tela_e_navegador(monkeypatch):
    v = _responder_local(monkeypatch, 'qwen3:8b', 'Roda o git --version pra mim.')
    c = v['o_corpo']
    assert isinstance(c, corpo.Corpo) and v['ferramentas'] is True
    assert not c.arquivos and not c.tela and not c.navegar and c.cerebro == 'local'


def test_pergunta_de_arquivo_continua_so_com_as_de_arquivo(monkeypatch, tmp_path):
    (tmp_path / 'Documentos').mkdir()
    pc.guardar_pastas([str(tmp_path / 'Documentos')])
    pc.ligar(True)
    v = _responder_local(monkeypatch, 'qwen3:8b', 'Qual a multa do meu contrato de aluguel?')
    assert v['o_corpo'] is None and v['ferramentas'] is True


def test_o_llama_fica_sem_o_corpo(monkeypatch):
    """Medido: anotou "Haiku sobre o outono" pedindo só um haiku."""
    v = _responder_local(monkeypatch, 'llama3.2:3b', 'Roda o git --version pra mim.')
    assert v['o_corpo'] is None


def test_pela_voz_o_caminho_rapido_nao_muda(monkeypatch):
    assert roteador._modo_local('Que horas são?', voz=True, modelo='qwen3:8b') == {'ferramentas': False, 'pensar': False}


def test_o_laco_do_local_usa_o_corpo_e_aceita_o_nome_sem_prefixo():
    pedidos = []

    def ollama_falso(request):
        c = json.loads(request.content)
        pedidos.append(c)
        if len(pedidos) == 1:
            # O modelo pequeno às vezes esquece o prefixo mcp__solis__.
            linhas = [{'message': {'content': '', 'tool_calls': [{'function': {'name': 'criar_lembrete', 'arguments': {
                'texto': 'Comprar pão', 'dia': '', 'hora': ''}}}]}, 'done': True}]
        else:
            linhas = [{'message': {'content': 'Anotei.'}, 'done': True}]
        return httpx.Response(200, content='\n'.join(json.dumps(l) for l in linhas).encode())

    async def rodar():
        etapas = Etapas(3)
        c = corpo.Corpo(3, etapas, navegar=False, cerebro='local')
        c.arquivos = c.tela = False
        fluxo = await ollama.conversar('qwen3:8b', [{'papel': 'pessoa', 'texto': 'anota comprar pão'}],
                                       transporte=httpx.MockTransport(ollama_falso), etapas=etapas,
                                       ferramentas=True, conversa=3, o_corpo=c)
        return ''.join([p async for p in fluxo]), etapas.lista

    texto, lista = asyncio.run(rodar())
    assert texto == 'Anotei.'
    nomes = [t['function']['name'] for t in pedidos[0]['tools']]
    assert 'mcp__solis__criar_lembrete' in nomes and 'PowerShell' in nomes and 'mcp__solis__ler_arquivo' not in nomes
    assert 'ferramentas do Solis (mcp__solis__)' in pedidos[0]['messages'][0]['content']
    assert [t['texto'] for t in banco.tarefas_abertas(5)] == ['Comprar pão']
    assert [e['ferramenta'] for e in lista if e['etapa'] == 'ferramenta'] == ['mcp__solis__criar_lembrete']
