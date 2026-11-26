"""Os avisos no celular (push.py, 26/11/2026): o Web Push do navegador.

A cifra foi conferida contra a implementação de referência (http_ece) em
design/nuvem/conferir_push.py; aqui, o caminho inteiro com um "celular" falso:
inscrever, mandar, o celular decifrar, e a inscrição que acabou sair sozinha."""
import asyncio
import base64
import json
import secrets
import struct

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient

from solis import avisos, main, push

ENDERECO = 'https://fcm.googleapis.com/fcm/send/aparelho-1'
# O avisos.mostrar de verdade (o conftest troca por um falso em todo teste, pra
# nada aparecer na tela do Matheus); aqui ele roda, com o Windows simulado.
MOSTRAR = avisos.mostrar


def b64(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b'=').decode()


def ponto(publica) -> bytes:
    return publica.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


class Celular:
    """O navegador do celular: as chaves que o PushSubscription entrega, e decifrar o que chega."""

    def __init__(self, endereco=ENDERECO):
        self.privada = ec.generate_private_key(ec.SECP256R1())
        self.auth = secrets.token_bytes(16)
        self.endereco = endereco

    def inscricao(self) -> dict:
        return {'endpoint': self.endereco, 'keys': {'p256dh': b64(ponto(self.privada.public_key())), 'auth': b64(self.auth)}}

    def decifrar(self, corpo: bytes) -> dict:
        sal = corpo[:16]
        rs, tamanho = struct.unpack('!IB', corpo[16:21])
        do_servidor = corpo[21:21 + tamanho]
        assert rs == 4096 and tamanho == 65
        compartilhado = self.privada.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), do_servidor))
        ikm = push._hkdf(self.auth, compartilhado, b'WebPush: info\x00' + ponto(self.privada.public_key()) + do_servidor, 32)
        cek = push._hkdf(sal, ikm, b'Content-Encoding: aes128gcm\x00', 16)
        nonce = push._hkdf(sal, ikm, b'Content-Encoding: nonce\x00', 12)
        claro = AESGCM(cek).decrypt(nonce, corpo[21 + tamanho:], None)
        assert claro.endswith(b'\x02')
        return json.loads(claro[:-1])


@pytest.fixture
def servico(monkeypatch):
    """O serviço de push (o do Google, o da Apple): guarda o que recebeu; `status` é o que ele responde."""
    estado = {'pedidos': [], 'status': 201}

    def responder(pedido):
        estado['pedidos'].append(pedido)
        return httpx.Response(estado['status'])
    monkeypatch.setattr(push, '_transporte', httpx.MockTransport(responder))
    return estado


def test_a_chave_do_servidor_nasce_uma_vez_e_fica():
    chave = push.chave_publica()
    assert len(base64.urlsafe_b64decode(chave + '=')) == 65 and push.chave_publica() == chave


def test_inscricao_quebrada_e_recusada():
    for ruim in ({'endpoint': 'http://inseguro/x', 'keys': Celular().inscricao()['keys']},
                 {'endpoint': ENDERECO, 'keys': {}},
                 {'endpoint': ENDERECO, 'keys': {'p256dh': b64(b'curta'), 'auth': b64(b'x' * 16)}}):
        with pytest.raises(push.InscricaoInvalida):
            push.inscrever(ruim)
    assert push.inscricoes() == []


def test_o_aviso_chega_cifrado_e_o_celular_le(servico):
    celular = Celular()
    aparelho = push.inscrever(celular.inscricao(), 'Mozilla/5.0 (Linux; Android 15) Chrome/131.0 Mobile')
    assert aparelho['aparelho'] == 'Chrome no Android' and 'p256dh' not in aparelho
    assert asyncio.run(push.enviar('Jarvis · Vigia', 'Loja caiu: erro 503.', 'site-loja')) == 1
    [pedido] = servico['pedidos']
    assert str(pedido.url) == ENDERECO
    assert pedido.headers['content-encoding'] == 'aes128gcm' and pedido.headers['ttl'] == str(push.GUARDA)
    assert pedido.headers['authorization'].startswith('vapid t=') and pedido.headers['authorization'].endswith(f'k={push.chave_publica()}')
    assert b'Loja caiu' not in pedido.content  # o serviço de push só vê o envelope
    assert celular.decifrar(pedido.content) == {'titulo': 'Jarvis · Vigia', 'texto': 'Loja caiu: erro 503.', 'tag': 'site-loja'}


def test_inscricao_que_acabou_sai_sozinha(servico):
    push.inscrever(Celular().inscricao())
    servico['status'] = 410
    assert asyncio.run(push.enviar('Solis', 'oi', 't')) == 0
    assert push.inscricoes() == []


def test_o_mesmo_aparelho_se_inscrevendo_de_novo_nao_duplica(servico):
    celular = Celular()
    push.inscrever(celular.inscricao())
    push.inscrever(celular.inscricao())
    assert len(push.inscricoes()) == 1
    asyncio.run(push.enviar('Solis', 'oi', 't'))
    assert len(servico['pedidos']) == 1


def test_os_avisos_do_solis_vao_pro_celular_tambem(servico, monkeypatch):
    """O aviso do compromisso, do Vigia e do Atlas passa por avisos.mostrar: no PC,
    o Windows e o celular; no servidor, só o celular."""
    async def sem_windows(*_):
        return False
    monkeypatch.setattr(avisos, '_windows', sem_windows)
    monkeypatch.setattr(avisos, 'mostrar', MOSTRAR)
    celular = Celular()
    push.inscrever(celular.inscricao())
    assert asyncio.run(avisos.mostrar('Reunião', 'Às 14h, daqui a 10 min', 'compromisso:1'))
    assert celular.decifrar(servico['pedidos'][0].content)['titulo'] == 'Reunião'
    # Sem aparelho ligado e sem Windows, não chegou a lugar nenhum: a próxima volta tenta.
    push.remover(celular.endereco)
    assert not asyncio.run(avisos.mostrar('Reunião', 'Às 14h', 'compromisso:1'))


def test_pela_tela(servico):
    c = TestClient(main.app)
    assert c.get('/avisos/push').json() == {'chave': push.chave_publica(), 'aparelhos': []}
    celular = Celular()
    r = c.post('/avisos/push', json=celular.inscricao(), headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1'})
    assert r.json()['aparelho']['aparelho'] == 'Safari no iPhone'
    assert c.post('/avisos/push', json={'endpoint': 'x', 'keys': {}}).json()['erro'] == 'inscricao_invalida'
    teste = c.post('/avisos/push/testar').json()
    assert teste == {'entregues': 1, 'aparelhos': 1}
    assert celular.decifrar(servico['pedidos'][0].content)['titulo'] == 'Solis'
    [aparelho] = c.get('/avisos/push').json()['aparelhos']
    assert c.post('/avisos/push/remover', json={'quem': aparelho['id']}).json() == {'ok': True}
    assert c.post('/avisos/push/remover', json={'quem': aparelho['id']}).status_code == 404
