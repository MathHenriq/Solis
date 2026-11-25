"""O Vigia medido com rede de verdade (25/11/2026), num banco temporário e sem
mostrar aviso no Windows.

    backend/.venv/Scripts/python design/vigia/medir.py mecanica
        Um site de verdade no PC (http.server) cai e volta, 3 vezes, com o laço de
        verdade e os tempos em escala (INTERVALO 20 s, CONFIRMA 5 s, VOLTA 2 s):
        quanto tempo da queda até o aviso, e da volta até o "voltou".
    backend/.venv/Scripts/python design/vigia/medir.py falsos [minutos]
        Sites públicos estáveis conferidos a cada minuto: quantas olhadas falharam
        e quantos avisos (alarmes falsos) sairiam.
"""
import asyncio
import datetime as dt
import http.server
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from solis import avisos, banco, vigia  # noqa: E402

AVISOS: list[tuple[float, str]] = []


async def _mostrar(titulo, texto, tag):
    AVISOS.append((time.monotonic(), texto))
    print(f'   [{time.strftime("%H:%M:%S")}] AVISO: {texto}')
    return True


def _preparar():
    banco.usar(Path(tempfile.mkdtemp()) / 'medir.db')
    avisos.mostrar = _mostrar
    avisos.ligados = lambda: True


class _Servidor:
    def __init__(self, porta):
        self.porta, self.httpd = porta, None

    def ligar(self):
        class Calado(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', self.porta), Calado)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def desligar(self):
        self.httpd.shutdown()
        self.httpd.server_close()


async def _esperar_aviso(antes: int, prazo: float) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < prazo:
        if len(AVISOS) > antes:
            return AVISOS[-1][0] - t0
        await asyncio.sleep(0.2)
    return None


async def mecanica() -> None:
    _preparar()
    vigia.INTERVALO, vigia.CONFIRMA, vigia.VOLTA = dt.timedelta(seconds=20), dt.timedelta(seconds=5), 2
    porta = 8799
    srv = _Servidor(porta)
    srv.ligar()
    vigia.adicionar(f'http://127.0.0.1:{porta}', 'Site de teste')
    laco = asyncio.create_task(vigia.vigiar())
    await asyncio.sleep(3)
    quedas, voltas = [], []
    for i in range(3):
        await asyncio.sleep(7 + i * 6)  # cai num ponto diferente do ciclo a cada vez
        antes = len(AVISOS)
        srv.desligar()
        print(f'{time.strftime("%H:%M:%S")} derrubei o site (volta {i + 1})')
        quedas.append(await _esperar_aviso(antes, 60))
        antes = len(AVISOS)
        srv = _Servidor(porta)
        srv.ligar()
        print(f'{time.strftime("%H:%M:%S")} liguei de novo')
        voltas.append(await _esperar_aviso(antes, 60))
    laco.cancel()
    print(f'\nda queda ao aviso (s): {[round(x, 1) if x else None for x in quedas]} '
          f'(limite em escala: INTERVALO + CONFIRMA + VOLTA = 27 s)')
    print(f'da volta ao "voltou" (s): {[round(x, 1) if x else None for x in voltas]}')
    print('com os tempos de verdade (5 min, 30 s, 30 s): o aviso sai em no máximo 6 min, 3 min em média.')


PUBLICOS = ['google.com', 'pt.wikipedia.org', 'github.com', 'vercel.com', 'www.gov.br', 'www.uol.com.br',
            'g1.globo.com', 'www.mercadolivre.com.br']


async def falsos(minutos: int) -> None:
    _preparar()
    for s in PUBLICOS:
        vigia.adicionar(s)
    olhadas, falhas = 0, []
    fim = time.monotonic() + minutos * 60
    agora = dt.datetime.now().replace(microsecond=0)
    while time.monotonic() < fim:
        pendentes = vigia.sites()
        resultados = await asyncio.gather(*(vigia.conferir_site(s) for s in pendentes))
        for s, r in zip(pendentes, resultados):
            olhadas += 1
            if not r['ok']:
                falhas.append((s['nome'], r['motivo']))
                print(f'   falhou: {s["nome"]}: {r["motivo"]}')
            await vigia.registrar(s, r, agora)
            if not r['ok']:  # a segunda olhada, como no laço, 30 s depois
                await asyncio.sleep(30)
                r2 = await vigia.conferir_site(s)
                olhadas += 1
                agora += dt.timedelta(seconds=30)
                await vigia.registrar(next(x for x in vigia.sites() if x['id'] == s['id']), r2, agora)
        await asyncio.sleep(60)
        agora += dt.timedelta(seconds=60)
    tempos = [s['ms'] for s in vigia.sites() if s.get('ms')]
    print(f'\n{olhadas} olhadas em {len(PUBLICOS)} sites por {minutos} min: {len(falhas)} falharam, '
          f'{len([a for a in AVISOS if "caiu" in a[1]])} alarmes falsos.')
    print(f'tempo da última resposta de cada um (ms): {sorted(tempos)}')


if __name__ == '__main__':
    modo = sys.argv[1] if len(sys.argv) > 1 else 'mecanica'
    asyncio.run(mecanica() if modo == 'mecanica' else falsos(int(sys.argv[2]) if len(sys.argv) > 2 else 30))
