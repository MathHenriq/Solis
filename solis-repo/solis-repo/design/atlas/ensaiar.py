"""O Atlas · Pesquisador de verdade, sem gravar nada (25/11/2026): coleta as
novidades da semana nas fontes, o primeiro cérebro da ordem do Matheus escolhe,
e o relatório aparece aqui, com os tempos. Nada vai pro banco nem pro Windows.

    backend/.venv/Scripts/python design/atlas/ensaiar.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from solis import pesquisador  # noqa: E402


async def main() -> None:
    import datetime as dt
    agora = dt.datetime.now().replace(microsecond=0)
    t0 = time.perf_counter()
    candidatas, contagem = await pesquisador.coletar(agora)
    t1 = time.perf_counter()
    print(f'coleta: {t1 - t0:.1f} s · de IA por fonte: {contagem} · na lista pro cérebro: {len(candidatas)}')
    print('cérebros na ordem:', pesquisador._cerebros())
    escolhidas, cerebro = await pesquisador.escolher(candidatas)
    t2 = time.perf_counter()
    print(f'escolha: {t2 - t1:.1f} s por {cerebro} · {len(escolhidas)} escolhidas')
    tamanho = len(pesquisador.SISTEMA) + len(pesquisador.PERFIL) + len(pesquisador._lista_pro_cerebro(candidatas))
    print(f'primeiro pedido pro cérebro: ~{tamanho // 4} tokens (o segundo leva as páginas: até ~3.000)\n')
    print(pesquisador.relatorio(escolhidas, candidatas, contagem, agora))
    urls = {x['url'] for x in candidatas}
    print(f'\nlinks que não vieram das fontes: {[x["url"] for x in escolhidas if x["url"] not in urls]}')


if __name__ == '__main__':
    asyncio.run(main())
