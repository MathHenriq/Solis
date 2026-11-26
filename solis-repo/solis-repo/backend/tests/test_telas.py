"""Mais de um monitor (tela.py, 19/11/2026): o print e as coordenadas são da
tela escolhida (1 = a principal). Telas simuladas: nada olha a tela de verdade."""
import asyncio
import os

import pytest
from PIL import Image

from solis import corpo, tela

# Do corpo do PC: só existe no Windows (no servidor Linux, quem mexe no PC é o
# próprio PC). 26/11/2026.
so_no_windows = pytest.mark.skipif(os.name != 'nt', reason='corpo do PC: só no Windows')

DUAS = [{'x': 0, 'y': 0, 'largura': 1920, 'altura': 1080, 'principal': True},
        {'x': 1920, 'y': 0, 'largura': 1920, 'altura': 1080, 'principal': False}]


@pytest.fixture
def duas_telas(monkeypatch):
    monkeypatch.setattr(tela, 'monitores', lambda: [dict(m) for m in DUAS])


def test_sem_escolher_e_a_principal(duas_telas):
    assert tela._origem() == (0, 0) and tela._real(100, 100) == (141, 141)
    assert tela.descrever_telas() == ('Telas: 1 (principal, 1920x1080) e 2 (à direita, 1920x1080). '
                                      'Vendo a 1; pra outra, tela_ver com tela.')


def test_na_tela_2_o_ponto_do_print_cai_na_tela_2(duas_telas):
    tela.escolher_tela(2)
    # 1366 de largura no print: escala 1366/1920; (100, 100) do print → (141, 141) na tela 2.
    assert tela._origem() == (1920, 0) and tela._real(100, 100) == (2061, 141)
    assert 'Vendo a 2' in tela.descrever_telas()
    with pytest.raises(tela.TelaRecusada):
        tela.escolher_tela(3)
    with pytest.raises(tela.TelaRecusada):
        tela._real(1366, 10)  # fora da tela (o print vai de 0 a 1365)


def test_o_print_e_da_tela_escolhida(duas_telas, monkeypatch):
    from PIL import ImageGrab
    pedidos = []
    monkeypatch.setattr(ImageGrab, 'grab', lambda **k: pedidos.append(k) or Image.new('RGB', (1920, 1080)))
    tela.escolher_tela(2)
    tela._print()
    assert pedidos == [{'bbox': (1920, 0, 3840, 1080), 'all_screens': True}]


def test_o_recorte_do_cartao_e_no_print_da_tela(duas_telas, monkeypatch):
    monkeypatch.setattr(tela, '_print', lambda: Image.new('RGB', (1920, 1080), 'white'))
    tela.escolher_tela(2)
    assert tela.recorte_marcado(1300, 700).startswith('data:image/png;base64,')  # perto do canto: não sai da imagem


def test_uma_tela_so_nao_fala_de_telas(monkeypatch):
    monkeypatch.setattr(tela, 'monitores', lambda: [dict(DUAS[0])])
    assert tela.descrever_telas() == ''


@so_no_windows
def test_os_outros_cerebros_escolhem_a_tela_no_tela_ler(duas_telas, monkeypatch):
    from solis import ocr
    monkeypatch.setattr(tela, 'ligada', lambda: True)
    monkeypatch.setattr(tela, '_print', lambda: Image.new('RGB', (1920, 1080)))
    monkeypatch.setattr(tela, '_png', lambda imagem: b'png')
    monkeypatch.setattr(tela, 'janela_ativa', lambda: ('notepad.exe', 'Bloco de Notas'))

    async def linhas(png):
        return [(100, 100, 50, 20, 'Salvar')]
    monkeypatch.setattr(ocr, 'linhas_com_posicao', linhas)
    texto = asyncio.run(corpo.Corpo(1, navegar=False).rodar('mcp__solis__tela_ler', {'tela': 2}))
    assert tela._atual == 1 and 'Vendo a 2' in texto
    errado = asyncio.run(corpo.Corpo(1, navegar=False).rodar('mcp__solis__tela_ler', {'tela': 5}))
    assert 'não existe' in errado
