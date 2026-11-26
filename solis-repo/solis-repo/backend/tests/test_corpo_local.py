"""O modelo local com o corpo do Solis (roteador._corpo_local): o meio-termo
medido em 19/11/2026 — as do Solis e o terminal nos pedidos que não são de
arquivo, só pros modelos que passaram (o qwen3:8b). Ollama simulado."""
import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest

from solis import banco, corpo, ollama, pc, roteador
from solis.etapas import Etapas

# Do corpo do PC: só existe no Windows (no servidor Linux, quem mexe no PC é o
# próprio PC). 26/11/2026.
so_no_windows = pytest.mark.skipif(os.name != 'nt', reason='corpo do PC: só no Windows')


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


@so_no_windows
def test_o_qwen_recebe_o_corpo_com_navegador_e_tela_sem_arquivo_nem_mcp(monkeypatch):
    """Medido em 19/11/2026: 12/13 e 13/13 com o navegador e a tela, sem piorar o resto."""
    from solis import navegador, tela
    monkeypatch.setattr(tela, 'ligada', lambda: True)
    monkeypatch.setattr(navegador, 'escolhido', lambda: 'msedge')
    monkeypatch.setattr(navegador, '_cli', lambda: Path(__file__))  # "instalado", em qualquer máquina
    v = _responder_local(monkeypatch, 'qwen3:8b', 'Roda o git --version pra mim.')
    c = v['o_corpo']
    assert isinstance(c, corpo.Corpo) and v['ferramentas'] is True
    assert not c.arquivos and not c.mcp and c.tela and c.navegar and c.cerebro == 'local'
    # Medido em 20/11/2026: editar, a internet (WebFetch) e as skills também.
    assert c.editar and c.web and c.skills
    # E os ajudantes, no mesmo modelo (medido em 20/11/2026).
    assert c.modelo == 'qwen3:8b' and c.tem('Agent')
    c._skills = [{'nome': 'plano-de-aula', 'descricao': 'Gera o plano de aula da semana.'}]
    instrucoes = corpo.instrucoes_local(c)
    assert 'você TEM internet' in instrucoes and 'PRIMEIRO chame mcp__solis__tela_ler' in instrucoes
    assert 'PRIMEIRO Read, depois Edit' in instrucoes and 'E WebFetch' in instrucoes
    assert 'plano-de-aula — Gera o plano de aula da semana.' in instrucoes


def test_com_as_ferramentas_o_local_nao_diz_que_nao_tem_internet():
    pedidos = []

    def ollama_falso(request):
        pedidos.append(json.loads(request.content))
        return httpx.Response(200, content=json.dumps({'message': {'content': 'ok'}, 'done': True}).encode())

    async def rodar():
        c = corpo.Corpo(3, Etapas(3), navegar=False, cerebro='local')
        c.arquivos = c.tela = False
        fluxo = await ollama.conversar('qwen3:8b', [{'papel': 'pessoa', 'texto': 'oi'}],
                                       transporte=httpx.MockTransport(ollama_falso), ferramentas=True, o_corpo=c)
        return ''.join([p async for p in fluxo])
    asyncio.run(rodar())
    sistema = pedidos[0]['messages'][0]['content']
    assert ollama.NAO_PODE not in sistema and 'o que não estiver nas suas ferramentas' in sistema
    # As ferramentas ocupam ~2.600 tokens: no padrão (4.096) a página lida empurrava a pergunta pra fora.
    assert pedidos[0]['options'] == {'num_ctx': ollama.CONTEXTO}


def test_o_ollama_caiu_depois_da_ferramenta_e_a_resposta_nao_sai_em_branco():
    """Visto em 20/11/2026: leu o arquivo, a conexão caiu, e a resposta voltava vazia."""
    vezes = []

    def ollama_falso(request):
        vezes.append(1)
        if len(vezes) == 1:
            msg = {'content': '', 'tool_calls': [{'function': {'name': 'mcp__solis__hora', 'arguments': {}}}]}
            return httpx.Response(200, content=json.dumps({'message': msg, 'done': True}).encode())
        raise httpx.ConnectError('caiu', request=request)

    async def rodar():
        c = corpo.Corpo(3, Etapas(3), navegar=False, cerebro='local')
        c.arquivos = c.tela = False
        fluxo = await ollama.conversar('qwen3:8b', [{'papel': 'pessoa', 'texto': 'que horas são?'}],
                                       transporte=httpx.MockTransport(ollama_falso), ferramentas=True, o_corpo=c)
        return ''.join([p async for p in fluxo])
    assert asyncio.run(rodar()) == ollama.CAIU_NO_MEIO


def test_pensou_e_nao_escreveu_nada_nao_sai_em_branco():
    """Visto com o qwen3:8b e a tela: a resposta voltava vazia."""
    def ollama_falso(request):
        linhas = [{'message': {'content': '', 'thinking': 'hmm'}, 'done': False}, {'message': {'content': ''}, 'done': True}]
        return httpx.Response(200, content='\n'.join(json.dumps(l) for l in linhas).encode())

    async def rodar():
        fluxo = await ollama.conversar('qwen3:8b', [{'papel': 'pessoa', 'texto': 'clica em salvar'}],
                                       transporte=httpx.MockTransport(ollama_falso), ferramentas=True)
        return ''.join([p async for p in fluxo])
    assert asyncio.run(rodar()).startswith('Não consegui responder isso agora')


def test_pergunta_de_arquivo_continua_so_com_as_de_arquivo(monkeypatch, tmp_path):
    (tmp_path / 'Documentos').mkdir()
    pc.guardar_pastas([str(tmp_path / 'Documentos')])
    pc.ligar(True)
    v = _responder_local(monkeypatch, 'qwen3:8b', 'Qual a multa do meu contrato de aluguel?')
    assert v['o_corpo'] is None and v['ferramentas'] is True


def test_numa_conversa_de_projeto_o_pedido_de_arquivo_vai_com_o_corpo_pra_editar(monkeypatch, tmp_path):
    """Medido em 20/11/2026: com a pasta do projeto, 10/10 nas edições pelo corpo."""
    (tmp_path / 'Documentos').mkdir()
    pc.guardar_pastas([str(tmp_path / 'Documentos')])
    pc.ligar(True)
    conversa = banco.nova_conversa()
    assert not roteador._corpo_local('qwen3:8b', 'No conta.py, troca soma por somar.', conversa)
    banco.guardar_projeto(conversa, str(tmp_path), 'pedir')
    assert roteador._corpo_local('qwen3:8b', 'No conta.py, troca soma por somar.', conversa)
    assert not roteador._corpo_local('llama3.2:3b', 'No conta.py, troca soma por somar.', conversa)


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
    assert 'mcp__solis__criar_lembrete' in nomes and 'mcp__solis__ler_arquivo' not in nomes
    assert ('PowerShell' in nomes) == (os.name == 'nt')  # o terminal do PC é o do Windows
    assert 'ferramentas do Solis (mcp__solis__)' in pedidos[0]['messages'][0]['content']
    assert [t['texto'] for t in banco.tarefas_abertas(5)] == ['Comprar pão']
    assert [e['ferramenta'] for e in lista if e['etapa'] == 'ferramenta'] == ['mcp__solis__criar_lembrete']
