"""Estilos de resposta (docs/PARIDADE.md): Normal, Conciso, Explicativo, Formal
e os do Matheus; o escolhido vai como nota pro cérebro, não pra conversa."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from solis import banco, estilos, main, roteador


def test_normal_nao_manda_nota():
    assert estilos.atual()['id'] == 'normal' and estilos.nota() == ''
    estilos.escolher('conciso')
    assert estilos.nota().startswith('\n\n[Estilo de resposta escolhido pelo Matheus: Conciso.')
    with pytest.raises(estilos.EstiloInvalido):
        estilos.escolher('poetico')


def test_os_seus():
    e = estilos.salvar('  Como   amigo ', 'Escreva como um amigo próximo, leve.')
    assert e['nome'] == 'Como amigo' and e['seu'] and e['id'].startswith('seu-')
    estilos.escolher(e['id'])
    assert 'Como amigo' in estilos.nota()
    estilos.salvar('Como amigo', 'Mais leve ainda.', e['id'])
    assert 'Mais leve ainda.' in estilos.nota()
    with pytest.raises(estilos.EstiloInvalido, match='já existe'):
        estilos.salvar('conciso', 'x')
    with pytest.raises(estilos.EstiloInvalido, match='nome'):
        estilos.salvar(' ', 'x')
    with pytest.raises(estilos.EstiloInvalido, match='instruções'):
        estilos.salvar('Outro', '')
    # Apagar o escolhido volta pro Normal.
    assert estilos.apagar(e['id']) and estilos.atual()['id'] == 'normal'
    assert not estilos.apagar(e['id'])


def test_a_nota_vai_pro_cerebro_e_nao_fica_na_conversa(monkeypatch):
    recebido = {}

    async def responder(ordem, modelo, conversa, historico, memorias, trechos, resumo, mensagem, *_, notas='', **__):
        # A nota vai em `notas` (pro roteador pôr no fim da mensagem dos de nuvem
        # e no sistema do local), junto com a da personalidade.
        recebido['mensagem'] = mensagem + notas

        async def fluxo():
            yield 'Ok.'
        return fluxo(), 'local'
    monkeypatch.setattr(roteador, 'responder', responder)
    monkeypatch.setattr(roteador, '_ordem', lambda: ['local'])

    async def nada(*_, **__):
        return None
    monkeypatch.setattr(main, '_depois', nada)
    estilos.escolher('formal')
    conversa = banco.nova_conversa()

    async def mandar():
        r = await main.enviar(conversa, main.Envio(texto='Oi'))
        async for _ in r.body_iterator:
            pass
    asyncio.run(mandar())
    assert recebido['mensagem'].startswith('Oi') and 'Formal' in recebido['mensagem']
    assert banco.mensagens(conversa)[0]['texto'] == 'Oi'


def test_rotas():
    cli = TestClient(main.app)
    r = cli.get('/estilos').json()
    assert r['atual'] == 'normal' and [e['id'] for e in r['estilos']] == ['normal', 'conciso', 'explicativo', 'formal']
    novo = cli.post('/estilos', json={'nome': 'Como amigo', 'instrucoes': 'Leve.'}).json()
    assert cli.put('/estilos/atual', json={'id': novo['id']}).json()['atual'] == novo['id']
    assert cli.put('/estilos/atual', json={'id': 'nada'}).status_code == 404
    r = cli.put(f'/estilos/{novo["id"]}', json={'nome': 'Formal', 'instrucoes': 'x'})
    assert r.status_code == 400 and 'já existe' in r.json()['motivo']
    assert cli.delete(f'/estilos/{novo["id"]}').json() == {'ok': True}
    assert cli.delete(f'/estilos/{novo["id"]}').status_code == 404
    assert cli.get('/estilos').json()['atual'] == 'normal'
