"""Ler, criar e editar arquivos pelo corpo (solis/editar.py): Read, Write e
Edit, as mesmas do Claude, com o mesmo cartão e o diff. Antes só o Claude
editava (PARIDADE.md). A Groq é simulada; o disco é uma pasta de teste."""
import asyncio
import json

import httpx

from solis import agente, apis, banco, cofre, corpo, editar, roteador


class Gravador:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


def sse(*eventos):
    return '\n\n'.join([f'data: {json.dumps(e)}' for e in eventos] + ['data: [DONE]']) + '\n\n'


def resposta(*eventos):
    return httpx.Response(200, text=sse(*eventos), headers={'content-type': 'text/event-stream'})


def chamada(nome, argumentos, id_='c1'):
    return {'choices': [{'delta': {'tool_calls': [
        {'index': 0, 'id': id_, 'type': 'function', 'function': {'name': nome, 'arguments': json.dumps(argumentos)}}]}}]}


def texto(t):
    return {'choices': [{'delta': {'content': t}}]}


def com_chave():
    banco.guardar_ajuste('chave:groq', cofre.selar('gsk_x'))
    banco.guardar_ajuste('modelo:groq', 'openai/gpt-oss-120b')


def conversa_no_projeto(pasta, modo='pedir'):
    conversa = banco.nova_conversa()
    banco.guardar_projeto(conversa, str(pasta), modo)
    return conversa


def rodar(conversa, pedidos_do_modelo, aprovar=None):
    """A Groq pede as ferramentas em ordem e termina com "Pronto."; `aprovar`:
    True/False pra cada cartão que aparecer (None: nenhum cartão esperado)."""
    com_chave()
    vistos = []

    def rota(req):
        vistos.append(json.loads(req.content))
        n = len(vistos)
        if n <= len(pedidos_do_modelo):
            nome, args = pedidos_do_modelo[n - 1]
            return resposta(chamada(nome, args, f'c{n}'))
        return resposta(texto('Pronto.'))

    g = Gravador()

    async def tudo():
        fluxo = apis.responder('groq', 'sis', 'mexe no arquivo', g, httpx.MockTransport(rota),
                               corpo=corpo.Corpo(conversa, g, navegar=False, cerebro='groq'))
        tarefa = asyncio.ensure_future(_juntar(fluxo))
        respondidos = 0
        while not tarefa.done():
            cartoes = [d for e, d in g.lista if e == 'aprovacao']
            if len(cartoes) > respondidos:
                agente.responder_aprovacao(cartoes[respondidos]['id'], aprovar[respondidos])
                respondidos += 1
            await asyncio.sleep(0.01)
        return await tarefa

    saida = asyncio.run(tudo())
    # O que cada ferramenta devolveu ao modelo (as mensagens 'tool' do último pedido).
    devolvido = [m['content'] for m in vistos[-1]['messages'] if m.get('role') == 'tool']
    return saida, g, devolvido, vistos


async def _juntar(fluxo):
    return ''.join([p async for p in fluxo])


def test_le_no_projeto_sem_cartao_e_edita_com_o_cartao_e_o_diff(tmp_path):
    (tmp_path / 'conta.py').write_text('def soma(a, b):\n    return a + b\n', encoding='utf-8')
    conversa = conversa_no_projeto(tmp_path)
    saida, g, devolvido, vistos = rodar(conversa, [
        ('Read', {'file_path': 'conta.py'}),
        ('Edit', {'file_path': 'conta.py', 'old_string': 'def soma', 'new_string': 'def somar'}),
    ], aprovar=[True])
    assert saida == 'Pronto.'
    assert (tmp_path / 'conta.py').read_text(encoding='utf-8') == 'def somar(a, b):\n    return a + b\n'
    cartoes = [d for e, d in g.lista if e == 'aprovacao']
    assert len(cartoes) == 1 and cartoes[0]['ferramenta'] == 'Edit' and cartoes[0]['cerebro'] == 'groq'
    assert '-def soma' in cartoes[0]['diff'] and '+def somar' in cartoes[0]['diff']
    assert 'return a + b' in devolvido[0] and '<<<INÍCIO DO ARQUIVO>>>' in devolvido[0]
    assert devolvido[1].startswith('Editei ')
    # As ferramentas foram pro modelo com os nomes do Claude, e o sistema fala delas.
    nomes = [t['function']['name'] for t in vistos[0]['tools']]
    assert {'Read', 'Write', 'Edit'} <= set(nomes)
    passos = [d for e, d in g.lista if e == 'ferramenta']
    assert [(p['ferramenta'], p['ok']) for p in passos] == [('Read', True), ('Edit', True)]


def test_edicao_que_vai_falhar_nem_chega_ao_matheus(tmp_path):
    (tmp_path / 'a.txt').write_text('um\ndois\ndois\n', encoding='utf-8')
    conversa = conversa_no_projeto(tmp_path)
    _, g, devolvido, _ = rodar(conversa, [
        ('Edit', {'file_path': 'a.txt', 'old_string': 'três', 'new_string': '3'}),
        ('Edit', {'file_path': 'a.txt', 'old_string': 'dois', 'new_string': '2'}),
        ('Edit', {'file_path': 'nao_existe.txt', 'old_string': 'x', 'new_string': 'y'}),
    ])
    assert not [d for e, d in g.lista if e == 'aprovacao']
    assert devolvido[0].startswith('Não achei o old_string') and 'aparece 2 vezes' in devolvido[1]
    assert devolvido[2].startswith('Não existe')
    assert (tmp_path / 'a.txt').read_text(encoding='utf-8') == 'um\ndois\ndois\n'


def test_write_recusado_nao_cria_nada_e_aprovado_cria(tmp_path):
    conversa = conversa_no_projeto(tmp_path)
    _, _, devolvido, _ = rodar(conversa, [('Write', {'file_path': 'novo.md', 'content': '# Oi\n'})], aprovar=[False])
    assert devolvido == ['O Matheus recusou.'] and not (tmp_path / 'novo.md').exists()
    _, g, devolvido, _ = rodar(conversa, [('Write', {'file_path': 'sub/novo.md', 'content': '# Oi\n'})],
                               aprovar=[True])
    assert (tmp_path / 'sub' / 'novo.md').read_text(encoding='utf-8') == '# Oi\n'
    assert devolvido[0].startswith('Criei ')
    assert '+# Oi' in next(d for e, d in g.lista if e == 'aprovacao')['diff']


def test_modo_planejar_nao_escreve_e_aceitar_nao_pede(tmp_path):
    (tmp_path / 'b.txt').write_text('velho\n', encoding='utf-8')
    conversa = conversa_no_projeto(tmp_path, 'planejar')
    _, g, devolvido, _ = rodar(conversa, [('Edit', {'file_path': 'b.txt', 'old_string': 'velho', 'new_string': 'novo'})])
    assert 'modo planejar' in devolvido[0] and not [d for e, d in g.lista if e == 'aprovacao']
    banco.guardar_projeto(conversa, str(tmp_path), 'aceitar')
    _, g, devolvido, _ = rodar(conversa, [('Edit', {'file_path': 'b.txt', 'old_string': 'velho', 'new_string': 'novo'})])
    assert not [d for e, d in g.lista if e == 'aprovacao']
    assert (tmp_path / 'b.txt').read_text(encoding='utf-8') == 'novo\n'


def test_ler_fora_das_pastas_pede(tmp_path):
    fora = tmp_path / 'fora'
    fora.mkdir()
    (fora / 'segredo.txt').write_text('42\n', encoding='utf-8')
    projeto = tmp_path / 'projeto'
    projeto.mkdir()
    conversa = conversa_no_projeto(projeto)
    _, g, devolvido, _ = rodar(conversa, [('Read', {'file_path': str(fora / 'segredo.txt')})], aprovar=[False])
    cartao = next(d for e, d in g.lista if e == 'aprovacao')
    assert cartao['ferramenta'] == 'Read' and devolvido == ['O Matheus recusou.']


def test_arquivo_do_windows_com_crlf_edita_e_mantem_o_fim_de_linha(tmp_path):
    (tmp_path / 'w.txt').write_bytes(b'linha um\r\nlinha dois\r\n')
    entrada = {'file_path': str(tmp_path / 'w.txt'), 'old_string': 'linha um\nlinha dois', 'new_string': 'a\nb'}
    editar.conferir_edicao(entrada, None)
    editar.editar(entrada, None)
    assert (tmp_path / 'w.txt').read_bytes() == b'a\r\nb\r\n'
    editar.escrever({'file_path': str(tmp_path / 'w.txt'), 'content': 'x\ny\n'}, None)
    assert (tmp_path / 'w.txt').read_bytes() == b'x\r\ny\r\n'


def test_o_sistema_da_groq_fala_de_editar_e_nao_diz_que_nao_escreve():
    sistema = roteador.sistema_para('groq', com_o_corpo=True, editar=True)
    assert 'Read, Write, Edit' in sistema
    notas = roteador.notas_do_cerebro('groq', [], com_o_corpo=True, editar=True)
    assert 'não escreve arquivos' not in notas and 'não lê nem escreve' not in notas and 'não roda comandos' in notas


def test_write_por_cima_sem_ler_e_recusado_e_depois_de_ler_passa(tmp_path):
    """Medido em 20/11/2026: o qwen3:8b chamou Write só com a função nova e o
    arquivo perdia o resto. Como no Claude Code: reescrever inteiro, só lido."""
    (tmp_path / 'conta.py').write_text('def soma(a, b):\n    return a + b\n', encoding='utf-8')
    conversa = conversa_no_projeto(tmp_path)
    _, g, devolvido, _ = rodar(conversa, [('Write', {'file_path': 'conta.py', 'content': 'def multiplica(a, b): ...\n'})])
    assert 'já existe e você não leu' in devolvido[0] and not [d for e, d in g.lista if e == 'aprovacao']
    assert (tmp_path / 'conta.py').read_text(encoding='utf-8').startswith('def soma')
    novo = 'def soma(a, b):\n    return a + b\n\n\ndef multiplica(a, b):\n    return a * b\n'
    _, _, devolvido, _ = rodar(conversa, [('Read', {'file_path': 'conta.py'}),
                                          ('Write', {'file_path': 'conta.py', 'content': novo})], aprovar=[True])
    assert (tmp_path / 'conta.py').read_text(encoding='utf-8') == novo
