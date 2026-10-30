"""O servidor MCP de memória, chamado como um CLI o chamaria."""
import asyncio
import json

from solis import banco
from solis.servidor_mcp import servidor


def chamar(ferramenta: str, **argumentos):
    """O que o CLI receberia. No SDK 2, lista vem estruturada (embrulhada em
    {"result": ...}); dicionário vem como JSON em texto; texto, como texto."""
    resultado = asyncio.run(servidor.call_tool(ferramenta, argumentos))
    assert not resultado.is_error, resultado
    dado = resultado.structured_content
    if dado is not None:
        return dado['result'] if set(dado) == {'result'} else dado
    texto = resultado.content[0].text
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return texto


def test_perfil_nao_mostra_o_que_e_privado():
    banco.adicionar_memoria('Tem asma.', 'Saúde', False, None, privada=True)
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    perfil = chamar('memorias_do_matheus')
    assert [m['texto'] for m in perfil] == ['Trabalha na Syngenta.']


def test_busca_sem_embeddings_ainda_devolve_memorias_e_nunca_privadas():
    banco.adicionar_memoria('Tem asma.', 'Saúde', False, None, privada=True)
    banco.adicionar_memoria('Gosta de chá.', 'Preferências', False, None)
    achado = chamar('buscar_na_memoria', assunto='saúde')
    assert [m['texto'] for m in achado['memorias']] == ['Gosta de chá.']
    assert achado['trechos'] == []


def test_guardar_entra_no_solis_como_pedido():
    resposta = chamar('guardar_memoria', texto='Usa Windows 11.', tema='Computador')
    assert 'Usa Windows 11.' in str(resposta)
    [m] = banco.memorias()
    assert (m['texto'], m['tema'], m['pedido'], m['privada']) == ('Usa Windows 11.', 'Computador', True, False)


def test_guardar_dito_em_sigilo_fica_privado():
    chamar('guardar_memoria', texto='Isso é privado: a senha do wifi é x.', tema='Casa')
    assert banco.memorias()[0]['privada']
