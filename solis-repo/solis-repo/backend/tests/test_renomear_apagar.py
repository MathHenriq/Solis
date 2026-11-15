"""Renomear e apagar conversa (docs/PARIDADE.md)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solis import agente, banco, main


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    trabalho = tmp_path / 'trabalho'
    trabalho.mkdir()
    monkeypatch.setattr(agente, '_pasta_trabalho', lambda: trabalho)
    return TestClient(main.app)


def test_renomear(cliente):
    c = banco.nova_conversa()
    banco.adicionar(c, 'pessoa', 'oi')
    r = cliente.patch(f'/conversas/{c}', json={'titulo': '  Viagem   pra Bahia  '})
    assert r.json() == {'id': c, 'titulo': 'Viagem pra Bahia'}
    assert banco.titulo(c) == 'Viagem pra Bahia'
    assert cliente.patch(f'/conversas/{c}', json={'titulo': '   '}).status_code == 400
    assert cliente.patch('/conversas/99999', json={'titulo': 'x'}).status_code == 404


def test_apagar_leva_mensagens_e_anexos_e_deixa_as_memorias(cliente):
    a = cliente.post('/anexos?nome=nota.txt', content=b'x').json()
    c = banco.nova_conversa()
    m = banco.adicionar(c, 'pessoa', 'guarda isso')
    banco.guardar_anexos(m, [a])
    banco.adicionar(c, 'solis', 'guardei')
    memoria = banco.adicionar_memoria('O Matheus gosta de café.', 'gostos', False, c)
    banco.guardar_sessao_claude(c, 's1')
    assert cliente.delete(f'/conversas/{c}').json() == {'ok': True}
    assert not banco.existe(c) and banco.mensagens(c) == [] and banco.sessao_claude(c) is None
    assert not Path(a['caminho']).exists()
    if memoria is not None:
        assert any('café' in x['texto'] for x in banco.memorias())
    assert cliente.delete(f'/conversas/{c}').status_code == 404


def test_nao_apaga_respondendo(cliente):
    import asyncio
    c = banco.nova_conversa()
    main._paradas[c] = asyncio.Event()
    try:
        assert cliente.delete(f'/conversas/{c}').status_code == 409
    finally:
        main._paradas.pop(c, None)
