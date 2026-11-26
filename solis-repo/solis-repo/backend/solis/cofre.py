"""O cofre: o que é privado fica criptografado no solis.db.

DPAPI do Windows (CryptProtectData), amarrada à conta do Matheus no Windows:
quem copiar o solis.db pra outro computador ou outra conta — um backup que
vaza, um notebook roubado com o disco lido por fora — não lê o que é privado.
Sem senha pra digitar e sem chave guardada em arquivo: quem segura a chave é o
próprio Windows, liberada no login.

O que isto NÃO protege, e é bom saber: um programa rodando na mesma conta,
com o Matheus logado, consegue pedir ao Windows pra abrir. É o mesmo nível do
que o Chrome faz com as senhas salvas.

O valor selado é texto, pra caber nas mesmas colunas: "cofre:v1:" + base64.
Selar o que já está selado não faz nada, e abrir o que não está selado devolve
como veio — então dá pra selar aos poucos, e os dados de antes continuam
legíveis.

Fora do Windows (o Solis como servidor, no Linux — 26/11/2026) não há DPAPI: o
valor é selado com AES-GCM ("cofre:v2:"), com uma chave de 32 bytes guardada num
arquivo só do usuário (permissão 600), FORA da pasta do banco: um backup ou uma
cópia do solis.db não leva a chave junto. Quem tiver o servidor inteiro (o disco
e a conta) abre, como no Windows. Sem a biblioteca `cryptography`, o texto fica
como está, com um aviso no log.
"""
import base64
import logging
import os
import secrets
import sys
from pathlib import Path

log = logging.getLogger('solis.cofre')

PREFIXO_WINDOWS = 'cofre:v1:'
PREFIXO_ARQUIVO = 'cofre:v2:'
WINDOWS = sys.platform == 'win32'
# O que este sistema grava ao selar.
PREFIXO = PREFIXO_WINDOWS if WINDOWS else PREFIXO_ARQUIVO

# Entropia própria do Solis: outro programa da mesma conta que chame a DPAPI
# sem ela não abre. Não é segredo (está aqui), mas tira o "abre qualquer um".
ENTROPIA = b'Solis: o que e privado'

# O que aparece no lugar de um valor que não abre — o banco foi copiado pra
# outra conta ou outro computador.
ILEGIVEL = '(privado — não abre neste computador)'

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _args = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
             wintypes.DWORD, ctypes.POINTER(_Blob)]
    _crypt32.CryptProtectData.argtypes = _args
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, *_args[2:]]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    # Nunca abrir janela pedindo nada: o servidor roda sem ninguém olhando.
    _SEM_JANELA = 0x1

    def _blob(dados: bytes) -> tuple['_Blob', ctypes.Array]:
        buf = ctypes.create_string_buffer(dados, len(dados))
        return _Blob(len(dados), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def _chamar(funcao, dados: bytes) -> bytes:
        entrada, _b1 = _blob(dados)
        entropia, _b2 = _blob(ENTROPIA)
        saida = _Blob()
        if not funcao(ctypes.byref(entrada), None, ctypes.byref(entropia), None, None, _SEM_JANELA, ctypes.byref(saida)):
            raise OSError(ctypes.get_last_error() or 'DPAPI falhou')
        try:
            return ctypes.string_at(saida.pbData, saida.cbData)
        finally:
            _kernel32.LocalFree(saida.pbData)

    def _proteger(dados: bytes) -> bytes:
        return _chamar(_crypt32.CryptProtectData, dados)

    def _desproteger(dados: bytes) -> bytes:
        return _chamar(_crypt32.CryptUnprotectData, dados)

    DISPONIVEL = True

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # sem a biblioteca: o cofre de arquivo não existe
    AESGCM = None
    InvalidTag = ValueError

if not WINDOWS:
    DISPONIVEL = AESGCM is not None


def arquivo_da_chave() -> Path:
    """Onde mora a chave do cofre fora do Windows: SOLIS_COFRE_ARQUIVO, senão
    ~/.config/solis/cofre.chave (longe do banco, em ~/.local/share/solis)."""
    if os.environ.get('SOLIS_COFRE_ARQUIVO'):
        return Path(os.environ['SOLIS_COFRE_ARQUIVO'])
    base = os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config'
    return Path(base) / 'solis' / 'cofre.chave'


_chaves: dict[Path, bytes] = {}


def _chave_do_arquivo() -> bytes:
    """A chave de 32 bytes; criada na primeira vez, só legível pelo usuário."""
    caminho = arquivo_da_chave()
    if caminho in _chaves:
        return _chaves[caminho]
    try:
        chave = base64.b64decode(caminho.read_bytes().strip(), validate=True)
    except FileNotFoundError:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        chave = secrets.token_bytes(32)
        # O_EXCL: se outro processo criou no meio-tempo, usa a dele.
        try:
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return _chave_do_arquivo()
        with os.fdopen(fd, 'wb') as f:
            f.write(base64.b64encode(chave))
        log.info('cofre: chave nova criada em %s', caminho)
    if len(chave) != 32:
        raise ValueError(f'a chave do cofre em {caminho} não tem 32 bytes')
    _chaves[caminho] = chave
    return chave


def _selar_arquivo(dados: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(_chave_do_arquivo()).encrypt(nonce, dados, ENTROPIA)


def _abrir_arquivo(dados: bytes) -> bytes:
    return AESGCM(_chave_do_arquivo()).decrypt(dados[:12], dados[12:], ENTROPIA)


_avisou = False


def selado(valor: str | None) -> bool:
    return bool(valor) and valor.startswith((PREFIXO_WINDOWS, PREFIXO_ARQUIVO))


def selar(texto: str | None) -> str | None:
    """O texto, criptografado. Vazio e o que já está selado voltam como vieram."""
    global _avisou
    if not texto or selado(texto):
        return texto
    if not DISPONIVEL:
        if not _avisou:
            log.warning('sem cofre neste sistema (falta a biblioteca cryptography): '
                        'o que é privado fica em texto puro no banco')
            _avisou = True
        return texto
    dados = texto.encode('utf-8')
    if WINDOWS:
        return PREFIXO_WINDOWS + base64.b64encode(_proteger(dados)).decode('ascii')
    return PREFIXO_ARQUIVO + base64.b64encode(_selar_arquivo(dados)).decode('ascii')


def abrir(valor: str | None) -> str | None:
    """O texto de volta. O que não está selado volta como veio; o que não abre
    (banco de outra conta ou outro computador, ou sem a chave do cofre) vira
    ILEGIVEL, sem derrubar nada."""
    if not selado(valor):
        return valor
    try:
        if valor.startswith(PREFIXO_WINDOWS):
            if not WINDOWS:
                return ILEGIVEL
            return _desproteger(base64.b64decode(valor[len(PREFIXO_WINDOWS):])).decode('utf-8')
        if AESGCM is None:
            return ILEGIVEL
        return _abrir_arquivo(base64.b64decode(valor[len(PREFIXO_ARQUIVO):])).decode('utf-8')
    except (OSError, ValueError, InvalidTag):
        log.warning('um valor selado não abriu: o banco veio de outra conta ou outro computador?')
        return ILEGIVEL
