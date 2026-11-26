"""Os avisos no celular: o Web Push do próprio navegador (26/11/2026).

No PC o aviso é a notificação do Windows (avisos.py). No servidor (o cérebro
na nuvem) não há Windows: o aviso vai pro celular — e pra qualquer navegador que
o Matheus ligou em Configurações → Avisos no celular — pelo Web Push, o mesmo
que os sites usam. Por que este canal (comparado em 26/11/2026):

- grátis, sem app pra instalar e sem conta em serviço nenhum: o celular já tem;
- o conteúdo vai criptografado de ponta a ponta (RFC 8291): o serviço de push do
  navegador (Google no Android/Chrome, Apple no iPhone) só vê um envelope;
- o mesmo canal serve pra qualquer cliente, quando o Solis for vendido.
No iPhone, o navegador só recebe com o Solis na Tela de Início (é como a Apple faz).

Feito aqui, sem a pywebpush (que traz aiohttp e requests junto): o protocolo é
curto e fechado — RFC 8291 (a cifra, aes128gcm), RFC 8188 (o formato) e RFC 8292
(a assinatura do servidor, VAPID) — e o Solis já tem a criptografia e o httpx.
Conferido contra a implementação de referência (http_ece) em
design/nuvem/conferir_push.py.

As chaves do servidor (VAPID) nascem na primeira vez; a privada fica selada no
cofre. Cada aparelho ligado é uma inscrição (o endereço do serviço de push e as
chaves do aparelho), guardada selada também. Inscrição que o serviço diz que
acabou (404/410: o Matheus tirou a permissão, trocou de celular) sai sozinha.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import time
from urllib.parse import urlsplit

import httpx

from . import banco, cofre

log = logging.getLogger('solis.push')

CHAVE_VAPID = 'push_vapid'
CHAVE_INSCRICOES = 'push_inscricoes'
# Quem assina o pedido (VAPID "sub"): o serviço de push só usa pra contato em
# caso de abuso. Nada do Matheus vai pra fora sem ele pedir: o padrão é um
# endereço que não existe (.invalid, RFC 2606).
CONTATO = os.environ.get('SOLIS_PUSH_CONTATO', 'mailto:avisos@solis.invalid')
VALIDADE = 12 * 3600       # a assinatura vale 12 h (o máximo é 24 h)
GUARDA = 24 * 3600         # o serviço guarda o aviso até o aparelho ligar
REGISTRO = 4096            # tamanho do registro aes128gcm (um só basta)
MAXIMO = 4096              # o corpo inteiro, que os serviços de push aceitam
TEXTO_MAX = 600            # caracteres do texto do aviso (a notificação mostra bem menos)
PRAZO = httpx.Timeout(10.0, connect=5.0)
_transporte: httpx.AsyncBaseTransport | None = None  # os testes trocam


class InscricaoInvalida(ValueError):
    pass


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b'=').decode('ascii')


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + '=' * (-len(texto) % 4))


def _ec():
    from cryptography.hazmat.primitives.asymmetric import ec
    return ec


def _ponto(chave_publica) -> bytes:
    from cryptography.hazmat.primitives import serialization
    return chave_publica.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


# — As chaves do servidor (VAPID) ————————————————————————————————————————————

def _vapid():
    """A chave privada do servidor (P-256), criada na primeira vez e selada no cofre."""
    ec = _ec()
    guardada = banco.ajuste(CHAVE_VAPID)
    if guardada:
        aberta = cofre.abrir(guardada)
        if aberta != cofre.ILEGIVEL:
            return ec.derive_private_key(int.from_bytes(_de_b64(aberta), 'big'), ec.SECP256R1())
        log.warning('push: a chave do servidor não abriu (banco de outro computador?): criando outra')
    privada = ec.generate_private_key(ec.SECP256R1())
    valor = privada.private_numbers().private_value.to_bytes(32, 'big')
    banco.guardar_ajuste(CHAVE_VAPID, cofre.selar(_b64(valor)))
    # Chave nova: as inscrições feitas com a velha não valem mais.
    banco.guardar_ajuste(CHAVE_INSCRICOES, None)
    return privada


def chave_publica() -> str:
    """A que o navegador usa pra se inscrever (applicationServerKey), em base64url."""
    return _b64(_ponto(_vapid().public_key()))


def _assinatura(endpoint: str, agora: float | None = None) -> str:
    """O cabeçalho Authorization do VAPID (RFC 8292): um JWT ES256 pro serviço de push."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    ec = _ec()
    partes = urlsplit(endpoint)
    cabeca = _b64(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())
    corpo = _b64(json.dumps({'aud': f'{partes.scheme}://{partes.netloc}',
                             'exp': int((agora or time.time()) + VALIDADE),
                             'sub': CONTATO}, separators=(',', ':')).encode())
    privada = _vapid()
    der = privada.sign(f'{cabeca}.{corpo}'.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    jwt = f'{cabeca}.{corpo}.{_b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}'
    return f'vapid t={jwt}, k={_b64(_ponto(privada.public_key()))}'


# — A cifra (RFC 8291 + 8188, aes128gcm) ————————————————————————————————————————

def _hkdf(sal: bytes, ikm: bytes, info: bytes, tamanho: int) -> bytes:
    prk = hmac.new(sal, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b'\x01', hashlib.sha256).digest()[:tamanho]


def cifrar(p256dh: str, auth: str, dados: bytes, sal: bytes | None = None, efemera=None) -> bytes:
    """O corpo do push, cifrado pro aparelho. `sal` e `efemera` só nos testes."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ec = _ec()
    do_aparelho = _de_b64(p256dh)
    segredo = _de_b64(auth)
    if len(do_aparelho) != 65 or len(segredo) != 16:
        raise InscricaoInvalida('chaves do aparelho com tamanho errado')
    publica_aparelho = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), do_aparelho)
    efemera = efemera or ec.generate_private_key(ec.SECP256R1())
    minha = _ponto(efemera.public_key())
    compartilhado = efemera.exchange(ec.ECDH(), publica_aparelho)
    ikm = _hkdf(segredo, compartilhado, b'WebPush: info\x00' + do_aparelho + minha, 32)
    sal = sal or secrets.token_bytes(16)
    cek = _hkdf(sal, ikm, b'Content-Encoding: aes128gcm\x00', 16)
    nonce = _hkdf(sal, ikm, b'Content-Encoding: nonce\x00', 12)
    # Um registro só: os dados + o delimitador do último registro (0x02).
    cifrado = AESGCM(cek).encrypt(nonce, dados + b'\x02', None)
    corpo = sal + struct.pack('!IB', REGISTRO, len(minha)) + minha + cifrado
    # Os serviços de push aceitam até 4096 bytes no corpo inteiro (cabeçalho junto).
    if len(corpo) > MAXIMO:
        raise ValueError(f'aviso grande demais pra um push ({len(corpo)} bytes; o máximo é {MAXIMO})')
    return corpo


# — Os aparelhos ligados ————————————————————————————————————————————————————

def inscricoes() -> list[dict]:
    guardadas = banco.ajuste(CHAVE_INSCRICOES)
    if not guardadas:
        return []
    aberto = cofre.abrir(guardadas)
    if aberto == cofre.ILEGIVEL:
        return []
    return json.loads(aberto)


def _guardar(lista: list[dict]) -> None:
    banco.guardar_ajuste(CHAVE_INSCRICOES, cofre.selar(json.dumps(lista)) if lista else None)


def _id(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()[:12]


def _aparelho(agente: str) -> str:
    """Um nome curto pro aparelho, pelo navegador que se inscreveu."""
    a = agente or ''
    sistema = next((n for t, n in (('iPhone', 'iPhone'), ('iPad', 'iPad'), ('Android', 'Android'),
                                   ('Windows', 'Windows'), ('Mac OS', 'Mac'), ('Linux', 'Linux')) if t in a), '')
    navegador = next((n for t, n in (('Edg/', 'Edge'), ('Firefox/', 'Firefox'), ('Chrome/', 'Chrome'),
                                     ('Safari/', 'Safari')) if t in a), 'Navegador')
    return f'{navegador} no {sistema}' if sistema else navegador


def inscrever(inscricao: dict, agente: str = '') -> dict:
    """Guarda (ou atualiza) o aparelho. `inscricao`: o JSON do PushSubscription."""
    endpoint = str(inscricao.get('endpoint') or '')
    chaves = inscricao.get('keys') or {}
    if not endpoint.startswith('https://') or not chaves.get('p256dh') or not chaves.get('auth'):
        raise InscricaoInvalida('inscrição sem endereço https ou sem as chaves do aparelho')
    try:
        cifrar(chaves['p256dh'], chaves['auth'], b'teste')  # as chaves servem?
    except (ValueError, TypeError) as e:
        raise InscricaoInvalida(f'as chaves do aparelho não servem: {e}') from e
    novo = {'id': _id(endpoint), 'endpoint': endpoint, 'p256dh': chaves['p256dh'], 'auth': chaves['auth'],
            'aparelho': _aparelho(agente), 'criada': time.strftime('%Y-%m-%dT%H:%M:%S')}
    lista = [i for i in inscricoes() if i['endpoint'] != endpoint] + [novo]
    _guardar(lista)
    return publica(novo)


def remover(id_ou_endpoint: str) -> bool:
    lista = inscricoes()
    resto = [i for i in lista if id_ou_endpoint not in (i['id'], i['endpoint'])]
    _guardar(resto)
    return len(resto) < len(lista)


def publica(i: dict) -> dict:
    """O que a tela pode ver de uma inscrição (sem as chaves)."""
    return {'id': i['id'], 'aparelho': i['aparelho'], 'criada': i['criada']}


# — Mandar ————————————————————————————————————————————————————————————————

async def enviar(titulo: str, texto: str, tag: str) -> int:
    """Manda pra todos os aparelhos ligados. Devolve quantos o serviço aceitou."""
    lista = inscricoes()
    if not lista:
        return 0
    dados = json.dumps({'titulo': titulo[:120], 'texto': texto[:TEXTO_MAX], 'tag': tag[-64:]},
                       ensure_ascii=False).encode('utf-8')
    aceitos, acabaram = 0, []
    async with httpx.AsyncClient(timeout=PRAZO, transport=_transporte) as cliente:
        for i in lista:
            try:
                r = await cliente.post(i['endpoint'], content=cifrar(i['p256dh'], i['auth'], dados), headers={
                    'Authorization': _assinatura(i['endpoint']),
                    'Content-Encoding': 'aes128gcm',
                    'Content-Type': 'application/octet-stream',
                    'TTL': str(GUARDA),
                    'Urgency': 'high',
                })
            except httpx.HTTPError as e:
                log.warning('push: %s não respondeu: %s', i['aparelho'], e)
                continue
            if r.status_code in (404, 410):
                log.info('push: a inscrição de %s acabou (%s): saindo da lista', i['aparelho'], r.status_code)
                acabaram.append(i['endpoint'])
            elif r.is_success:
                aceitos += 1
            else:
                log.warning('push: %s recusou (%s): %s', i['aparelho'], r.status_code, r.text[:200])
    if acabaram:
        _guardar([i for i in inscricoes() if i['endpoint'] not in acabaram])
    return aceitos
