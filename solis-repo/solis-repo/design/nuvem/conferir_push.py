"""Confere a cifra do push do Solis (backend/solis/push.py) contra a implementação
de referência da Mozilla (http_ece), como um celular faria ao receber, e a
assinatura VAPID contra a chave pública do servidor.

26/11/2026: 200 de 200 avisos decifrados (de 0 a ~2.600 bytes, com acento
e emoji); assinatura conferida.

Rodar (a http_ece fica numa pasta à parte, fora do projeto):
    pip install --no-deps --target <pasta> http-ece==1.2.1
    $env:SOLIS_CONFERIR_PATH = 'backend;<pasta>'; backend/.venv/Scripts/python -I design/nuvem/conferir_push.py
(com -I o PYTHONPATH não vale: as pastas vão em SOLIS_CONFERIR_PATH, separadas por ;)
"""
import base64
import json
import os
import secrets
import sys
import tempfile

for p in os.environ.get('SOLIS_CONFERIR_PATH', '').split(os.pathsep):
    if p:
        sys.path.insert(0, p)

import http_ece  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature  # noqa: E402

os.environ['SOLIS_BANCO'] = os.path.join(tempfile.mkdtemp(), 'solis.db')
from solis import banco, push  # noqa: E402

banco.usar(__import__('pathlib').Path(os.environ['SOLIS_BANCO']))


def b64(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b'=').decode()


def de_b64(t: str) -> bytes:
    return base64.urlsafe_b64decode(t + '=' * (-len(t) % 4))


certos = 0
for n in range(200):
    # O "celular": a chave dele e o segredo, como o PushSubscription entrega.
    celular = ec.generate_private_key(ec.SECP256R1())
    p256dh = b64(celular.public_key().public_bytes(serialization.Encoding.X962,
                                                   serialization.PublicFormat.UncompressedPoint))
    auth = secrets.token_bytes(16)
    texto = ('Ação às 14h · 🌅 ' * (n * 3))[: n * 10].encode('utf-8')  # até ~2.600 bytes
    corpo = push.cifrar(p256dh, b64(auth), texto)
    aberto = http_ece.decrypt(corpo, private_key=celular, auth_secret=auth, version='aes128gcm')
    assert aberto == texto, n
    certos += 1
print(f'cifra: {certos} de 200 decifrados pela http_ece')

# A assinatura VAPID: o JWT confere com a chave pública que vai no cabeçalho.
cabecalho = push._assinatura('https://fcm.googleapis.com/fcm/send/abc')
t = cabecalho.split('t=')[1].split(',')[0]
k = cabecalho.split('k=')[1]
assert k == push.chave_publica()
cabeca, corpo_jwt, assinatura = t.split('.')
claims = json.loads(de_b64(corpo_jwt))
assert claims['aud'] == 'https://fcm.googleapis.com' and claims['sub'].startswith('mailto:')
bruta = de_b64(assinatura)
publica = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), de_b64(k))
publica.verify(encode_dss_signature(int.from_bytes(bruta[:32], 'big'), int.from_bytes(bruta[32:], 'big')),
               f'{cabeca}.{corpo_jwt}'.encode(), ec.ECDSA(hashes.SHA256()))
print('vapid: assinatura confere com a chave pública;', claims)
