"""Cotação e clima direto da fonte (solis/dados_ao_vivo.py): a AwesomeAPI e o
Open-Meteo, simulados. Os sites de cotação vinham vazios sem JavaScript, e o
cérebro chutava (a Groq deu o dólar a R$ 6,67)."""
import asyncio

import httpx
import pytest

from solis import corpo, dados_ao_vivo as d


def test_cotacao_em_reais_com_a_hora_e_os_nomes_que_ele_fala():
    pedidos = []

    def api(req):
        pedidos.append(str(req.url))
        return httpx.Response(200, json={
            'USDBRL': {'bid': '5.9488', 'create_date': '2026-11-20 15:18:54', 'pctChange': '0.22'},
            'BTCBRL': {'bid': '368195', 'create_date': '2026-11-21 18:16:00', 'pctChange': '4.09'}})
    texto = asyncio.run(d.cotacao('dólar e bitcoin', httpx.MockTransport(api)))
    assert pedidos == [d.COTACAO_URL.format(pares='USD-BRL,BTC-BRL')]
    assert 'Dólar: R$ 5,95 (compra), atualizado em 20/11 às 15:18, variação de +0,22% no dia' in texto
    assert 'Bitcoin: R$ 368.195,00' in texto


def test_clima_acha_a_cidade_e_diz_agora_e_o_dia():
    def api(req):
        if 'geocoding' in str(req.url):
            return httpx.Response(200, json={'results': [{'name': 'Ribeirão Preto', 'admin1': 'São Paulo',
                                                          'country': 'Brasil', 'latitude': -21.2, 'longitude': -47.8}]})
        return httpx.Response(200, json={
            'current': {'temperature_2m': 28.4, 'apparent_temperature': 29.1, 'weather_code': 3,
                        'relative_humidity_2m': 58, 'wind_speed_10m': 14},
            'daily': {'temperature_2m_max': [31.2], 'temperature_2m_min': [21.6],
                      'precipitation_probability_max': [70], 'weather_code': [61]}})
    texto = asyncio.run(d.clima('Ribeirão Preto', httpx.MockTransport(api)))
    assert texto.startswith('Ribeirão Preto, São Paulo, Brasil: agora 28 °C (sensação de 29 °C), nublado')
    assert 'máxima de 31 °C, mínima de 22 °C, 70% de chance de chuva (chuva fraca)' in texto


def test_sem_cidade_ou_cidade_que_nao_existe_diz_o_que_falta():
    with pytest.raises(d.SemDado, match='faltou a cidade'):
        asyncio.run(d.clima(''))
    vazio = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    with pytest.raises(d.SemDado, match='não achei a cidade'):
        asyncio.run(d.clima('Xyzópolis', vazio))


def test_as_duas_sao_ferramentas_do_solis_pra_todos_os_cerebros():
    nomes = [f.nome for f in corpo.DO_SOLIS]
    assert 'cotacao' in nomes and 'clima' in nomes and 'jogos' in nomes


def _evento(id_, data, estado, casa, gols_casa, fora, gols_fora, relogio=''):
    def lado(nome, gols, onde):
        return {'homeAway': onde, 'team': {'displayName': nome},
                **({'score': {'displayValue': gols}} if gols is not None else {})}
    return {'id': id_, 'date': data, 'league': {'name': 'Campeonato Brasileiro'},
            'competitions': [{'venue': {'fullName': 'Maracanã'},
                              'status': {'displayClock': relogio,
                                         'type': {'state': estado, 'completed': estado == 'post'}},
                              'competitors': [lado(fora, gols_fora, 'away'), lado(casa, gols_casa, 'home')]}]}


def test_jogos_do_time_principal_com_o_ultimo_o_ao_vivo_e_o_proximo():
    """21/11/2026: pela busca, a Groq deu o "último jogo do Flamengo" com um trecho
    de 26/10; o de hoje (Palmeiras 1 x 1) estava numa página que só vem com JavaScript."""
    pedidos = []

    def api(req):
        pedidos.append(req.url)
        if 'search' in req.url.path:
            assert req.url.params['query'] == 'Flamengo'  # "mengão" vira o nome que a fonte acha
            return httpx.Response(200, json={'results': [{'type': 'team', 'contents': [
                {'uid': 's:600~t:18467', 'displayName': 'Flamengo U20', 'sport': 'soccer',
                 'defaultLeagueSlug': 'bra.brasileiro_u20'},
                {'uid': 's:600~t:819', 'displayName': 'Flamengo', 'sport': 'soccer', 'defaultLeagueSlug': 'bra.1'}]}]})
        assert '/teams/819/' in req.url.path
        if req.url.params.get('fixture'):
            return httpx.Response(200, json={'events': [
                _evento('4', '2026-11-29T19:00Z', 'pre', 'Coritiba', None, 'Flamengo', None)]})
        return httpx.Response(200, json={'events': [
            _evento('1', '2026-11-04T22:30Z', 'post', 'Flamengo', '3', 'Grêmio', '1'),
            _evento('2', '2026-11-18T23:30Z', 'post', 'Flamengo', '2', 'Athletico-PR', '1'),
            _evento('3', '2026-11-21T19:30Z', 'post', 'Palmeiras', '1', 'Flamengo', '1'),
            _evento('5', '2026-11-22T20:00Z', 'in', 'Flamengo', '0', 'Vasco', '0', "12'")]})
    texto = asyncio.run(d.jogos('mengão', httpx.MockTransport(api)))
    ligas = sorted({p.path.split('/')[-4] for p in pedidos if 'schedule' in p.path})
    assert ligas == ['all', 'bra.1']  # a liga do time e todas (as copas), sem repetir os jogos
    assert texto.splitlines() == [
        'Flamengo (horário de Brasília):',
        "Ao vivo agora: Flamengo 0 x 0 Vasco, 12', Campeonato Brasileiro (Maracanã).",
        'Último jogo: Palmeiras 1 x 1 Flamengo, sábado, 21/11 às 16:30, Campeonato Brasileiro (Maracanã), encerrado.',
        'Antes: Flamengo 2 x 1 Athletico-PR (quarta, 18/11, Campeonato Brasileiro (Maracanã)); '
        'Flamengo 3 x 1 Grêmio (quarta, 04/11, Campeonato Brasileiro (Maracanã)).',
        'Próximo jogo: Coritiba x Flamengo, domingo, 29/11 às 16:00, Campeonato Brasileiro (Maracanã).']


def test_time_que_nao_existe_manda_procurar_na_web():
    vazio = httpx.MockTransport(lambda req: httpx.Response(200, json={'results': []}))
    with pytest.raises(d.SemDado, match='não achei o time'):
        asyncio.run(d.jogos('Xyzópolis FC', vazio))
    assert 'Procure na web' in asyncio.run(corpo._jogos({'equipe': ''}))
    # "equipe", não "time" (o gpt-oss lia em inglês e mandava a hora).
    jogos = next(f for f in corpo.DO_SOLIS if f.nome == 'jogos')
    assert list(jogos.parametros['properties']) == ['equipe']


def test_a_conta_com_datas_e_do_relogio_e_nao_de_cabeca(monkeypatch):
    """21/11/2026, pela voz: o gpt-oss-20b disse "quarenta e quatro dias" pro Natal (eram 34)."""
    from datetime import date
    monkeypatch.setattr(corpo, '_hoje', lambda: date(2026, 11, 21))

    def conta(**args):
        return asyncio.run(corpo._datas(args))
    assert conta(data='25/12') == 'Hoje é sábado, 21/11/2026. sexta, 25/12/2026: faltam 34 dias.'
    assert conta(data='25 de dezembro').endswith('faltam 34 dias.')
    # Sem ano e já passou: a próxima vez que a data chega. Com o ano: quanto faz.
    assert conta(data='01/01').endswith('sexta, 01/01/2027: faltam 41 dias.')
    assert conta(data='01/01/2026').endswith('foi há 324 dias.')
    assert conta(data='2026-11-21').endswith('é hoje.')
    assert conta(dias='45').endswith('Daqui a 45 dias: terça, 05/01/2027.')
    assert 'Não entendi a data' in conta(data='semana que vem')
    assert 'datas' in [f.nome for f in corpo.DO_SOLIS]
