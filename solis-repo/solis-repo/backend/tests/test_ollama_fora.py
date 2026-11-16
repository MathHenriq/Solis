"""O Ollama fora não custa mais 2 s por consulta, e o Solis liga ele se estiver parado."""
import asyncio

import httpx
import pytest

from solis import ollama




def test_lembra_que_o_ollama_esta_fora(monkeypatch):
    tentativas = []

    class Recusa(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            tentativas.append(1)
            raise httpx.ConnectError('recusado', request=request)

    async def pai(self, request):
        return await Recusa().handle_async_request(request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', pai)
    ollama.esquecer_fora()

    async def perguntar():
        async with httpx.AsyncClient(base_url='http://127.0.0.1:1', transport=ollama._Guardado()) as c:
            with pytest.raises(httpx.ConnectError):
                await c.get('/api/tags')
    asyncio.run(perguntar())
    asyncio.run(perguntar())
    assert len(tentativas) == 1 and ollama.fora()


def test_liga_o_ollama_parado(monkeypatch):
    estado = {'no_ar': False, 'popen': []}

    async def instalados():
        if not estado['no_ar']:
            raise ollama.OllamaIndisponivel()
        return {'qwen3:8b'}
    monkeypatch.setattr(ollama, 'instalados', instalados)
    monkeypatch.setattr(ollama, '_executavel', lambda: 'C:/ollama.exe')
    monkeypatch.setattr(ollama, 'LIGAR', True)

    import subprocess

    def popen(cmd, **kw):
        estado['popen'].append(cmd)
        estado['no_ar'] = True
    monkeypatch.setattr(subprocess, 'Popen', popen)
    assert asyncio.run(ollama.ligar_se_parado(espera=2)) == 'ligou'
    assert estado['popen'] == [['C:/ollama.exe', 'serve']]
    assert asyncio.run(ollama.ligar_se_parado()) == 'ja'
    monkeypatch.setattr(ollama, '_executavel', lambda: None)
    estado['no_ar'] = False
    assert asyncio.run(ollama.ligar_se_parado()) == 'sem'


def test_passado_o_prazo_a_pergunta_nao_paga_a_porta_e_a_sonda_confere(monkeypatch):
    """16/11/2026: na voz as perguntas vêm a mais de 60 s uma da outra, e cada
    uma pagava os 2 s da porta recusada. Passado o prazo, quem confere é a sonda."""
    tentativas, sondas = [], []

    async def pai(self, request):
        tentativas.append(1)
        raise httpx.ConnectError('recusado', request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', pai)
    porta = {'abre': False}

    def abre():
        sondas.append(1)
        return porta['abre']
    monkeypatch.setattr(ollama, '_porta_abre', abre)
    ollama.esquecer_fora()

    async def perguntar():
        async with httpx.AsyncClient(base_url='http://127.0.0.1:1', transport=ollama._Guardado()) as c:
            with pytest.raises(httpx.ConnectError):
                await c.get('/api/tags')
        if ollama._sonda:
            await ollama._sonda

    asyncio.run(perguntar())
    assert tentativas == [1] and ollama.fora()
    monkeypatch.setattr(ollama, '_fora_ate', 0.0)  # o prazo passou
    asyncio.run(perguntar())
    # A pergunta falhou na hora, sem tentar a porta; a sonda olhou (e ele segue fora).
    assert tentativas == [1] and sondas == [1] and ollama.fora()
    asyncio.run(perguntar())
    assert sondas == [1]  # sonda de novo só depois de SONDA_S
    porta['abre'] = True
    monkeypatch.setattr(ollama, '_sondado', 0.0)
    asyncio.run(perguntar())
    assert sondas == [1, 1] and not ollama.fora()
