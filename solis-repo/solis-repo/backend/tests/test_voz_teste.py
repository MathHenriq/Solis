"""O teste de qualidade da escuta (docs/IDEIAS.md): a gravação com roteiro, a
escuta rodando sobre ela como ao vivo, e a contagem contra o roteiro."""
import array
import asyncio
import io
import json
import math
import wave
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from solis import ativacao, main, voz_teste

TAXA = 16000


def _wav(amostras) -> bytes:
    saida = io.BytesIO()
    with wave.open(saida, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(array.array('h', amostras).tobytes())
    return saida.getvalue()


def _gravacao(trechos: list[tuple[float, float]], duracao: float) -> array.array:
    """Ruído baixo de fundo com "falas" (um tom alto) nos trechos dados."""
    a = array.array('h', (int(30 * math.sin(i * 0.37)) for i in range(int(duracao * TAXA))))
    for ini, fim in trechos:
        for i in range(int(ini * TAXA), int(fim * TAXA)):
            a[i] = int(9000 * math.sin(2 * math.pi * 220 * i / TAXA))
    return a


def test_roteiro_intercala_chamadas_e_trechos_sem():
    r = voz_teste.roteiro()
    tipos = [p['tipo'] for p in r['passos']]
    assert tipos.count('chamada') == 12 and tipos.count('sem') == 6
    assert r['passos'][0]['inicio'] == voz_teste.INICIO + voz_teste.PREPARO
    assert all(b['inicio'] >= a['fim'] for a, b in zip(r['passos'], r['passos'][1:]))
    assert 150 < r['duracao'] < 260  # uns 3 a 4 minutos


def test_parecido_ignora_acento_e_pontuacao():
    assert voz_teste.parecido('Que horas são?', 'que horas sao') == 1.0
    assert voz_teste.parecido('Quero ação', 'que horas são') < voz_teste.PARECIDO


@pytest.mark.parametrize('ouvido, esperado, certo', [
    ('Que horas são?', 'que horas são', True),
    ('Desliga a MCP.', 'desliga a música', False),          # parecia 83% e passava
    ('Pesquisa o preço do delar hoje.', 'pesquisa o preço do dólar hoje', True),
    ('Quanto marca registrada 15 vezes TRS?', 'quanto é quinze vezes três', False),
    ('', 'que horas são', False),
    ('Me lembra de beber água daqui a 20 minutos.', 'me lembra de beber água daqui a vinte minutos', True),
    ('A nota que gastei 30 reais no almoço.', 'anota que gastei trinta reais no almoço', True),
    ('Que horas é sua?', 'que horas são', False),
])
def test_entendeu_olha_as_palavras_do_pedido(ouvido, esperado, certo):
    assert voz_teste.entendeu(ouvido, esperado) is certo


def test_guardar_recusa_o_que_nao_e_a_gravacao():
    with pytest.raises(voz_teste.TesteInvalido, match='WAV'):
        voz_teste.guardar(b'nada')
    with pytest.raises(voz_teste.TesteInvalido, match='curta'):
        voz_teste.guardar(_wav([0] * TAXA))


def test_a_escuta_roda_na_gravacao_como_ao_vivo(monkeypatch):
    """Duas "falas": a primeira tem "Solis" e o pedido de uma vez; a segunda não."""
    amostras = _gravacao([(4.0, 5.2), (10.0, 11.0)], 15.0)
    ouvidos = iter(['Solis, que horas são?', 'O sol está forte', 'O sol está forte'])

    async def falso(tipo, audio):
        return next(ouvidos), 0.5
    eventos = asyncio.run(voz_teste.rodar_escuta(amostras, falso))
    tipos = [(e['tipo'], e.get('texto')) for e in eventos]
    # A segunda fala, sem "Solis", fica guardada como descartada (com o que ele ouviu).
    # Conferida cedo e, inteira, no fim (RECONFERIR): duas vezes descartada.
    assert tipos == [('ativou', None), ('texto', 'Que horas são?'), ('descartado', None), ('descartado', None)]
    assert eventos[2]['ouviu'] == 'O sol está forte'
    # A cascata: conferido com RASCUNHO_SILENCIO de silêncio, e como é pergunta,
    # sai em FIM_CEDO — o texto fica pronto com o Whisper daquela conferência,
    # sem esperar os FIM_SILENCIO nem transcrever de novo (antes: ~6,6 s).
    assert 5.2 < eventos[1]['t'] < 5.2 + ativacao.FIM_CEDO + 0.1
    assert eventos[1]['pronto'] == pytest.approx(5.2 + ativacao.RASCUNHO_SILENCIO + 0.5, abs=0.1)


def test_pontuar_conta_acertos_falsos_e_tempo(monkeypatch):
    passos = [
        {'i': 0, 'tipo': 'chamada', 'mostrar': '', 'esperado': 'que horas são', 'inicio': 2.0, 'fim': 8.0},
        {'i': 1, 'tipo': 'chamada', 'mostrar': '', 'esperado': 'o que eu tenho amanhã', 'inicio': 10.0, 'fim': 16.0},
        {'i': 2, 'tipo': 'sem', 'mostrar': '', 'esperado': '', 'inicio': 18.0, 'fim': 24.0},
    ]
    eventos = [
        {'tipo': 'ativou', 't': 5.0, 'pronto': 5.4, 'ouviu': 'Solis que horas são'},
        {'tipo': 'texto', 't': 5.0, 'pronto': 5.4, 'texto': 'Que horas são?'},
        {'tipo': 'ativou', 't': 20.0, 'pronto': 20.3, 'ouviu': 'Sol is forte'},
    ]
    monkeypatch.setattr(voz_teste, '_fim_da_fala', lambda a, ini, fim, ate=None: 4.0 if fim == 8.0 else 13.0)
    r = voz_teste.pontuar(passos, eventos, array.array('h'))
    assert r['resumo'] == {'chamadas': 2, 'acordou': 1, 'entendeu': 1, 'falsos': 1, 'trechos_sem': 1,
                           'latencia_mediana': 1.4, 'latencia_max': 1.4, 'passou': False}
    assert r['passos'][0]['latencia'] == 1.4 and r['passos'][2]['ouviu'] == ['Sol is forte']


def test_rotas(monkeypatch):
    medidos = []

    async def medir(id_, motor='atual', transcrever=None):
        medidos.append((id_, motor))
        (voz_teste.pasta() / id_ / f'medida-{motor}.json').write_text(json.dumps({'resumo': {'acordou': 1}}))
        return {}
    monkeypatch.setattr(voz_teste, 'medir', medir)
    cli = TestClient(main.app)
    assert len(cli.get('/voz/teste/roteiro').json()['passos']) == 18
    passos = [{'i': 0, 'tipo': 'chamada', 'esperado': 'que horas são', 'inicio': 5.1, 'fim': 13.2}]
    r = cli.post('/voz/teste', content=_wav([0] * (12 * TAXA)), headers={'X-Solis-Roteiro': quote(json.dumps(passos))})
    id_ = r.json()['id']
    assert r.json()['duracao'] == 12.0 and medidos == [(id_, 'atual'), (id_, 'silero')]
    assert json.loads((voz_teste.pasta() / id_ / 'roteiro.json').read_text(encoding='utf-8'))['passos'] == passos
    assert cli.get('/voz/teste').json()['testes'][0]['medidas']['atual'] == {'acordou': 1}
    assert cli.get(f'/voz/teste/{id_}/medida/atual').json() == {'resumo': {'acordou': 1}}
    assert cli.get(f'/voz/teste/{id_}/medida/nada').status_code == 404
    assert cli.post('/voz/teste/99999/medir').status_code == 404
    assert cli.post('/voz/teste', content=b'x').status_code == 400
