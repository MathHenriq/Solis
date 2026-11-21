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
    assert 'cotacao' in nomes and 'clima' in nomes
