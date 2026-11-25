"""O Vigia (vigia.py, 25/11/2026): confere os sites do Matheus e avisa quando um cai."""
import asyncio
import datetime as dt

import httpx
import pytest

from solis import avisos, corpo, personalidades, vigia

AGORA = dt.datetime(2026, 11, 25, 14, 0, 0)


@pytest.fixture
def site(monkeypatch):
    """Um site falso: `estado['status']` é o que ele responde (ou uma exceção)."""
    estado = {'status': 200, 'texto': '<h1>Loja do Matheus</h1>', 'pedidos': 0}

    def responder(pedido):
        estado['pedidos'] += 1
        if isinstance(estado['status'], Exception):
            raise estado['status']
        return httpx.Response(estado['status'], text=estado['texto'])
    monkeypatch.setattr(vigia, '_transporte', httpx.MockTransport(responder))
    monkeypatch.setattr(vigia, '_vencimento_do_certificado', lambda url: dt.date(2027, 3, 1))
    avisados = []

    async def mostrar(titulo, texto, tag):
        avisados.append((titulo, texto))
        return True
    monkeypatch.setattr(avisos, 'mostrar', mostrar)
    monkeypatch.setattr(avisos, 'ligados', lambda: True)
    estado['avisados'] = avisados
    return estado


def _volta(agora):
    return asyncio.run(vigia.uma_volta(agora))


def test_o_endereco_falado_vira_um_site():
    assert vigia.normalizar('meusite.com.br') == 'https://meusite.com.br'
    assert vigia.normalizar('http://loja.com/') == 'http://loja.com'
    assert vigia.normalizar('https://loja.com/status') == 'https://loja.com/status'
    for ruim in ('', 'meu site', 'oi'):
        with pytest.raises(vigia.EnderecoInvalido):
            vigia.normalizar(ruim)


def test_caiu_avisa_depois_de_duas_olhadas_e_avisa_quando_volta(site):
    vigia.adicionar('loja.com.br', 'Loja')
    assert _volta(AGORA) == []  # no ar
    site['status'] = 503
    # A queda: a olhada de 5 min depois falha, mas ainda não avisa...
    assert _volta(AGORA + dt.timedelta(minutes=5)) == []
    # ...e a segunda, 30 s depois, confirma e avisa.
    [aviso] = _volta(AGORA + dt.timedelta(minutes=5, seconds=30))
    assert aviso == 'Loja caiu: erro 503 (fora do ar ou sobrecarregado). Conferi duas vezes, a última às 14h05.'
    assert site['avisados'] == [('Jarvis · Vigia', aviso)]
    # Fora: não repete o aviso a cada olhada.
    assert _volta(AGORA + dt.timedelta(minutes=10, seconds=30)) == []
    site['status'] = 200
    [volta] = _volta(AGORA + dt.timedelta(minutes=15, seconds=30))
    assert volta == 'Loja voltou ao ar às 14h15, depois de 10 min fora.'
    [s] = vigia.sites()
    assert s['estado'] == 'no_ar' and len(s['quedas']) == 1
    assert 'Nos últimos 7 dias: 1 queda, 10 min fora.' in vigia.descrever(s, AGORA + dt.timedelta(hours=1))


def test_um_tropeco_so_nao_acorda_ninguem(site):
    vigia.adicionar('loja.com.br')
    _volta(AGORA)
    site['status'] = httpx.ReadTimeout('lento')
    assert _volta(AGORA + dt.timedelta(minutes=5)) == []
    site['status'] = 200
    assert _volta(AGORA + dt.timedelta(minutes=5, seconds=30)) == []
    assert site['avisados'] == [] and vigia.sites()[0]['estado'] == 'no_ar'


def test_a_pagina_que_abre_quebrada_tambem_e_queda(site):
    vigia.adicionar('loja.com.br', 'Loja', palavra='Loja do Matheus')
    _volta(AGORA)
    site['texto'] = '<h1>Application error</h1>'
    _volta(AGORA + dt.timedelta(minutes=5))
    [aviso] = _volta(AGORA + dt.timedelta(minutes=5, seconds=30))
    assert 'a página abriu, mas sem "Loja do Matheus"' in aviso


@pytest.mark.parametrize('erro, motivo', [
    (httpx.ConnectTimeout('x'), 'não respondeu em 10 s'),
    (httpx.ConnectError('[Errno 11001] getaddrinfo failed'), 'o endereço não existe mais (DNS)'),
    (httpx.ConnectError('[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired'),
     'erro no certificado de segurança (https)'),
    (httpx.ConnectError('[WinError 10061] conexão recusada'), 'recusou a conexão'),
])
def test_o_motivo_em_palavras(site, erro, motivo):
    site['status'] = erro
    s = vigia.adicionar('loja.com.br')
    assert asyncio.run(vigia.conferir_site(s))['motivo'] == motivo


def test_so_confere_quem_venceu(site):
    vigia.adicionar('a.com.br')
    _volta(AGORA)
    assert vigia.vencidos(AGORA + dt.timedelta(minutes=4)) == []
    assert len(vigia.vencidos(AGORA + dt.timedelta(minutes=5))) == 1
    site['status'] = 500
    _volta(AGORA + dt.timedelta(minutes=5))
    # Depois de uma falha, a segunda olhada vem logo (30 s), não em 5 min.
    assert len(vigia.vencidos(AGORA + dt.timedelta(minutes=5, seconds=30))) == 1


def test_o_certificado_perto_de_vencer_avisa_uma_vez(site, monkeypatch):
    monkeypatch.setattr(vigia, '_vencimento_do_certificado', lambda url: dt.date(2026, 12, 5))
    vigia.adicionar('loja.com.br', 'Loja')
    [aviso] = _volta(AGORA)
    assert aviso.startswith('O certificado de Loja vence em 10 dias (05/12)')
    assert _volta(AGORA + dt.timedelta(days=1)) == []  # já avisou esse vencimento


def test_pelas_ferramentas_do_solis_com_qualquer_cerebro(site):
    r = asyncio.run(corpo._vigiar_site({'endereco': 'loja.com.br', 'nome': 'Loja'}))
    assert r.startswith('Vigiando. Loja (https://loja.com.br): no ar (respondeu em') and 'a cada 5 minutos' in r
    assert asyncio.run(corpo._sites_vigiados({})).startswith('O site está no ar.')
    assert 'Parei de vigiar Loja' in asyncio.run(corpo._parar_de_vigiar({'site': 'loja.com.br'}))
    assert 'Nenhum site' in asyncio.run(corpo._sites_vigiados({}))
    assert 'não parece um site' in asyncio.run(corpo._vigiar_site({'endereco': 'meu site'}))
    nomes = {f.nome for f in corpo.DO_SOLIS}
    assert {'vigiar_site', 'sites_vigiados', 'parar_de_vigiar'} <= nomes


def test_vigiar_site_e_assunto_do_jarvis():
    assert personalidades.quem('vigia o site loja.com.br', None) == 'jarvis'
    assert personalidades.quem('meus sites estão no ar?', None) == 'jarvis'
    assert personalidades.quem('abre o site da Netflix', None) == 'solis'


@pytest.mark.parametrize('status', [429, 401])
def test_limitando_ou_pedindo_login_esta_no_ar(site, status):
    """25/11/2026: o Mercado Livre respondeu 429 sendo conferido a cada minuto. É o
    site no ar limitando acessos: avisar que caiu seria alarme falso."""
    vigia.adicionar('loja.com.br')
    site['status'] = status
    for minutos in (0, 5, 10):
        assert _volta(AGORA + dt.timedelta(minutes=minutos)) == []
    assert vigia.sites()[0]['estado'] == 'no_ar' and site['avisados'] == []
