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
legíveis. Fora do Windows não há DPAPI: o texto fica como está, com um aviso
no log (é onde o Solis roda nos testes da nuvem).
"""
import base64
import logging
import sys

log = logging.getLogger('solis.cofre')

PREFIXO = 'cofre:v1:'

# Entropia própria do Solis: outro programa da mesma conta que chame a DPAPI
# sem ela não abre. Não é segredo (está aqui), mas tira o "abre qualquer um".
ENTROPIA = b'Solis: o que e privado'

# O que aparece no lugar de um valor que não abre — o banco foi copiado pra
# outra conta ou outro computador.
ILEGIVEL = '(privado — não abre neste computador)'

if sys.platform == 'win32':
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
else:
    DISPONIVEL = False

_avisou = False


def selado(valor: str | None) -> bool:
    return bool(valor) and valor.startswith(PREFIXO)


def selar(texto: str | None) -> str | None:
    """O texto, criptografado. Vazio e o que já está selado voltam como vieram."""
    global _avisou
    if not texto or selado(texto):
        return texto
    if not DISPONIVEL:
        if not _avisou:
            log.warning('sem DPAPI neste sistema: o que é privado fica em texto puro no banco')
            _avisou = True
        return texto
    return PREFIXO + base64.b64encode(_proteger(texto.encode('utf-8'))).decode('ascii')


def abrir(valor: str | None) -> str | None:
    """O texto de volta. O que não está selado volta como veio; o que não abre
    (banco de outra conta ou outro computador) vira ILEGIVEL, sem derrubar nada."""
    if not selado(valor):
        return valor
    if not DISPONIVEL:
        return ILEGIVEL
    try:
        return _desproteger(base64.b64decode(valor[len(PREFIXO):])).decode('utf-8')
    except (OSError, ValueError):
        log.warning('um valor selado não abriu: o banco veio de outra conta ou outro computador?')
        return ILEGIVEL
