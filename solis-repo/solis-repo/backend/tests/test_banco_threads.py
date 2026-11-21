"""O banco usado por várias threads ao mesmo tempo (solis/banco.py, _con).
Era uma conexão só pra todas, e duas threads nela quebravam: visto em
20/11/2026, o login de um servidor MCP salvava numa thread enquanto a tela
listava em outra ("sqlite3.InterfaceError: bad parameter or other API
misuse"). Agora cada thread tem a sua, no mesmo arquivo."""
import threading
from concurrent.futures import ThreadPoolExecutor

from solis import banco


def test_varias_threads_lendo_e_escrevendo_ao_mesmo_tempo():
    erros = []
    comeco = threading.Barrier(8)

    def trabalhar(i):
        comeco.wait()
        try:
            for n in range(150):
                banco.guardar_ajuste(f'teste:{i}', {'n': n, 'texto': 'x' * 200})
                assert banco.ajuste(f'teste:{i}')['n'] == n
                banco.ajuste(f'teste:{(i + 1) % 8}')
        except Exception as e:  # noqa: BLE001 — o teste conta os erros
            erros.append(repr(e))

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(trabalhar, range(8)))
    assert erros == []
    assert [banco.ajuste(f'teste:{i}')['n'] for i in range(8)] == [149] * 8


def test_o_que_uma_thread_escreve_a_outra_le_e_trocar_de_banco_vale_pra_todas(tmp_path):
    banco.guardar_ajuste('compartilhado', 1)
    lido = []
    t = threading.Thread(target=lambda: lido.append(banco.ajuste('compartilhado')))
    t.start()
    t.join()
    assert lido == [1]
    # Com outro arquivo (como nos testes), as threads passam pro novo.
    with ThreadPoolExecutor(1) as ex:
        assert ex.submit(banco.ajuste, 'compartilhado').result() == 1
        banco.usar(tmp_path / 'outro.db')
        assert ex.submit(banco.ajuste, 'compartilhado').result() is None
