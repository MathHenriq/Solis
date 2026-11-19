"""Controle da tela (docs/PARIDADE.md): o Claude vê a tela e clica, digita e
aperta teclas em qualquer programa do PC, como o computer use do Claude Desktop.

Desligado até o Matheus ligar em Configurações → Controle da tela: o que está
na tela vai pro Claude (na nuvem). Ver a tela é livre; cada clique, texto ou
tecla pede cartão, com o print marcado onde vai clicar e o programa ("Sempre
neste programa" libera as ações nele, na conversa). Nada cai numa janela do
próprio Solis: o Claude não pode aprovar os próprios cartões.

Pela API do Windows (ctypes: SendInput, a mesma que o pyautogui usa por baixo;
o texto vai como Unicode, então acento sai certo) e o Pillow pro print. Só a
tela principal. O print vai pro Claude reduzido (LADO_MAX de largura); as
coordenadas que ele manda são nesse print e voltam pra tela de verdade aqui."""
from __future__ import annotations

import base64
import ctypes
import io
import logging
import os
import time
from ctypes import wintypes

from . import banco

log = logging.getLogger('solis.tela')

LADO_MAX = 1366          # a largura do print pro Claude (o tamanho em que o computer use enxerga bem)
RECORTE = (520, 320)     # o pedaço da tela que o cartão mostra em volta do clique
MINIATURA = 640          # o print inteiro no cartão de digitar/tecla
DEPOIS_S = 0.6           # espera depois da ação, antes do print novo
SOLIS = {'solis.exe'}    # o app do Solis: nada cai nele


class TelaRecusada(Exception):
    """A ação não pode acontecer (cai no Solis, coordenada fora, tecla que não existe)."""


def ligada() -> bool:
    return bool(banco.ajuste('tela_ligada')) and os.name == 'nt'


def ligar(valor: bool) -> bool:
    banco.guardar_ajuste('tela_ligada', bool(valor))
    return ligada()


# — o Windows ——————————————————————————————————————————————————————————————————
def _user32():
    return ctypes.windll.user32


_dpi_pronto = False


def _dpi() -> None:
    """Coordenadas em pixels de verdade (com a escala do Windows em 125%, sem isto
    o print e o clique discordam)."""
    global _dpi_pronto
    if _dpi_pronto or os.name != 'nt':
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        try:
            _user32().SetProcessDPIAware()
        except (OSError, AttributeError):
            pass
    _dpi_pronto = True


# — as telas ——————————————————————————————————————————————————————————————————
# Mais de um monitor (o do Matheus: dois, o principal e o do notebook à direita,
# 19/11/2026): o print é de uma tela por vez, a escolhida (tela_ver com `tela`:
# 1, 2...), e as coordenadas são as do print dela. Sem escolher, a principal.
_atual = 0


class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT),
                ('dwFlags', wintypes.DWORD)]


def monitores() -> list[dict]:
    """As telas, a principal primeiro e as outras da esquerda pra direita:
    x, y (no espaço de todas as telas, em pixels de verdade), largura, altura."""
    _dpi()
    lista = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                              wintypes.LPARAM)

    def cada(h, _hdc, _r, _l):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if _user32().GetMonitorInfoW(h, ctypes.byref(mi)):
            rc = mi.rcMonitor
            lista.append({'x': rc.left, 'y': rc.top, 'largura': rc.right - rc.left, 'altura': rc.bottom - rc.top,
                          'principal': bool(mi.dwFlags & 1)})
        return 1
    _user32().EnumDisplayMonitors(None, None, proc(cada), 0)
    if not lista:
        u = _user32()
        return [{'x': 0, 'y': 0, 'largura': u.GetSystemMetrics(0), 'altura': u.GetSystemMetrics(1), 'principal': True}]
    return sorted(lista, key=lambda m: (not m['principal'], m['x'], m['y']))


def _monitor() -> dict:
    lista = monitores()
    return lista[_atual] if _atual < len(lista) else lista[0]


def escolher_tela(numero) -> None:
    """A tela que tela_ver mostra e onde as coordenadas valem (1 = a principal)."""
    global _atual
    if numero in (None, ''):
        return
    try:
        n = int(numero)
    except (TypeError, ValueError) as e:
        raise TelaRecusada(f'a tela "{numero}" não existe') from e
    if not 1 <= n <= len(monitores()):
        raise TelaRecusada(f'a tela {n} não existe (são {len(monitores())})')
    _atual = n - 1


def descrever_telas() -> str:
    """'Telas: 1 (principal, 1920x1080) e 2 (1920x1080, à direita). Vendo a 1.'"""
    lista = monitores()
    if len(lista) == 1:
        return ''
    principal = lista[0]
    partes = []
    for i, m in enumerate(lista, 1):
        onde = 'principal' if m['principal'] else (
            'à direita' if m['x'] >= principal['x'] + principal['largura'] else
            'à esquerda' if m['x'] + m['largura'] <= principal['x'] else
            'embaixo' if m['y'] >= principal['y'] + principal['altura'] else 'em cima')
        partes.append(f'{i} ({onde}, {m["largura"]}x{m["altura"]})')
    atual = _atual + 1 if _atual < len(lista) else 1
    return f'Telas: {", ".join(partes[:-1])} e {partes[-1]}. Vendo a {atual}; pra outra, tela_ver com tela.'


def tamanho() -> tuple[int, int]:
    m = _monitor()
    return m['largura'], m['altura']


def _origem() -> tuple[int, int]:
    try:
        m = _monitor()
    except (OSError, AttributeError, ValueError):
        return 0, 0
    return m['x'], m['y']


def escala() -> float:
    largura, _ = tamanho()
    return min(1.0, LADO_MAX / largura)


def _real(x: float, y: float) -> tuple[int, int]:
    """Do print que o cérebro viu (da tela escolhida) pro ponto de verdade, no
    espaço de todas as telas."""
    e = escala()
    largura, altura = tamanho()
    rx, ry = round(x / e), round(y / e)
    if not (0 <= rx < largura and 0 <= ry < altura):
        raise TelaRecusada(f'({x}, {y}) fica fora da tela')
    ox, oy = _origem()
    return ox + rx, oy + ry


def _processo_da_janela(hwnd) -> tuple[str, str]:
    """(processo.exe, título) da janela de cima de `hwnd`."""
    u = _user32()
    raiz = u.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
    titulo = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(raiz, titulo, 256)
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(raiz, ctypes.byref(pid))
    nome = ''
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        try:
            buf = ctypes.create_unicode_buffer(520)
            n = wintypes.DWORD(520)
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                nome = os.path.basename(buf.value)
        finally:
            k.CloseHandle(h)
    return nome.lower(), titulo.value


def janela_em(x: int, y: int) -> tuple[str, str]:
    _dpi()
    return _processo_da_janela(_user32().WindowFromPoint(wintypes.POINT(x, y)))


def janela_ativa() -> tuple[str, str]:
    return _processo_da_janela(_user32().GetForegroundWindow())


def nome_do_programa(processo: str, titulo: str) -> str:
    """'Bloco de Notas — Sem título' vira o que o cartão mostra."""
    return titulo or processo.removesuffix('.exe') or 'um programa'


# — o print ————————————————————————————————————————————————————————————————————
def _print():
    """O print da tela escolhida, inteira, em pixels de verdade."""
    from PIL import ImageGrab
    m = _monitor()
    return ImageGrab.grab(bbox=(m['x'], m['y'], m['x'] + m['largura'], m['y'] + m['altura']), all_screens=True)


def _png(imagem) -> bytes:
    saida = io.BytesIO()
    imagem.save(saida, 'PNG', optimize=True)
    return saida.getvalue()


def ver() -> tuple[bytes, dict]:
    """O print reduzido pro Claude e o que ele precisa saber dele."""
    imagem = _print()
    e = escala()
    if e < 1:
        imagem = imagem.resize((round(imagem.width * e), round(imagem.height * e)))
    processo, titulo = janela_ativa()
    return _png(imagem), {'largura': imagem.width, 'altura': imagem.height,
                          'ativa': nome_do_programa(processo, titulo)}


def recorte_marcado(x: float, y: float) -> str:
    """O pedaço da tela em volta de onde vai clicar, com o alvo marcado (o cartão)."""
    from PIL import ImageDraw
    ox, oy = _origem()
    rx, ry = _real(x, y)
    rx, ry = rx - ox, ry - oy  # no print da tela, não no espaço de todas
    imagem = _print()
    w, h = RECORTE
    esq = min(max(0, rx - w // 2), max(0, imagem.width - w))
    topo = min(max(0, ry - h // 2), max(0, imagem.height - h))
    pedaco = imagem.crop((esq, topo, esq + w, topo + h)).convert('RGB')
    d = ImageDraw.Draw(pedaco)
    cx, cy = rx - esq, ry - topo
    for raio, cor in ((15, (255, 255, 255)), (13, (226, 72, 72))):
        d.ellipse((cx - raio, cy - raio, cx + raio, cy + raio), outline=cor, width=3)
    d.line((cx - 4, cy, cx + 4, cy), fill=(226, 72, 72), width=2)
    d.line((cx, cy - 4, cx, cy + 4), fill=(226, 72, 72), width=2)
    return 'data:image/png;base64,' + base64.b64encode(_png(pedaco)).decode()


def miniatura() -> str:
    imagem = _print().convert('RGB')
    imagem.thumbnail((MINIATURA, MINIATURA))
    return 'data:image/png;base64,' + base64.b64encode(_png(imagem)).decode()


# — agir ———————————————————————————————————————————————————————————————————————
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]


class _UNIAO(ctypes.Union):
    _fields_ = [('mi', _MOUSEINPUT), ('ki', _KEYBDINPUT), ('hi', _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('u', _UNIAO)]


def _mandar(*entradas: _INPUT) -> None:
    arr = (_INPUT * len(entradas))(*entradas)
    _user32().SendInput(len(entradas), arr, ctypes.sizeof(_INPUT))


def _mouse(flags: int, dado: int = 0) -> _INPUT:
    return _INPUT(type=0, u=_UNIAO(mi=_MOUSEINPUT(0, 0, dado, flags, 0, 0)))


def _tecla_vk(vk: int, solta: bool = False) -> _INPUT:
    estendida = vk in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B)
    return _INPUT(type=1, u=_UNIAO(ki=_KEYBDINPUT(vk, 0, (2 if solta else 0) | (1 if estendida else 0), 0, 0)))


def _unicode(codigo: int, solta: bool = False) -> _INPUT:
    return _INPUT(type=1, u=_UNIAO(ki=_KEYBDINPUT(0, codigo, 4 | (2 if solta else 0), 0, 0)))


BOTOES = {'esquerdo': (0x0002, 0x0004), 'direito': (0x0008, 0x0010), 'meio': (0x0020, 0x0040)}


def _nao_no_solis(processo: str) -> None:
    if processo in SOLIS:
        raise TelaRecusada('isso cai numa janela do próprio Solis, e lá nenhum cérebro mexe')


def clicar(x: float, y: float, botao: str = 'esquerdo', duplo: bool = False) -> None:
    rx, ry = _real(x, y)
    _nao_no_solis(janela_em(rx, ry)[0])
    desce, sobe = BOTOES.get(botao, BOTOES['esquerdo'])
    _user32().SetCursorPos(rx, ry)
    time.sleep(0.05)
    for _ in range(2 if duplo else 1):
        _mandar(_mouse(desce), _mouse(sobe))
        time.sleep(0.08)


def mover(x: float, y: float) -> None:
    rx, ry = _real(x, y)
    _user32().SetCursorPos(rx, ry)


def rolar(x: float, y: float, direcao: str, quantidade: int = 3) -> None:
    rx, ry = _real(x, y)
    _nao_no_solis(janela_em(rx, ry)[0])
    _user32().SetCursorPos(rx, ry)
    passo = 120 * max(1, min(int(quantidade), 20))
    if direcao in ('cima', 'baixo'):
        _mandar(_mouse(0x0800, ctypes.c_ulong(passo if direcao == 'cima' else -passo).value))
    elif direcao in ('esquerda', 'direita'):
        _mandar(_mouse(0x1000, ctypes.c_ulong(passo if direcao == 'direita' else -passo).value))
    else:
        raise TelaRecusada(f'direção "{direcao}"')


def digitar(texto: str) -> None:
    """O texto como Unicode (acento, emoji), na janela que está na frente; \\n vira Enter."""
    _nao_no_solis(janela_ativa()[0])
    for ch in texto:
        if ch == '\n':
            _mandar(_tecla_vk(0x0D), _tecla_vk(0x0D, True))
        else:
            for unidade in _utf16(ch):
                _mandar(_unicode(unidade), _unicode(unidade, True))
        time.sleep(0.004)


def _utf16(ch: str) -> list[int]:
    dados = ch.encode('utf-16-le')
    return [int.from_bytes(dados[i:i + 2], 'little') for i in range(0, len(dados), 2)]


TECLAS = {
    'enter': 0x0D, 'tab': 0x09, 'esc': 0x1B, 'escape': 0x1B, 'espaco': 0x20, 'space': 0x20,
    'backspace': 0x08, 'apagar': 0x2E, 'delete': 0x2E, 'del': 0x2E, 'insert': 0x2D,
    'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    'cima': 0x26, 'up': 0x26, 'baixo': 0x28, 'down': 0x28, 'esquerda': 0x25, 'left': 0x25,
    'direita': 0x27, 'right': 0x27,
    'ctrl': 0x11, 'control': 0x11, 'shift': 0x10, 'alt': 0x12, 'win': 0x5B, 'windows': 0x5B,
    **{f'f{i}': 0x6F + i for i in range(1, 13)},
}


def _vk(nome: str) -> int:
    n = nome.strip().lower()
    if n in TECLAS:
        return TECLAS[n]
    if len(n) == 1 and n.isalnum():
        return ord(n.upper())
    raise TelaRecusada(f'a tecla "{nome}" não existe')


def tecla(combinacao: str) -> None:
    """'ctrl+s', 'enter', 'alt+tab': aperta junto e solta ao contrário."""
    _nao_no_solis(janela_ativa()[0])
    vks = [_vk(p) for p in combinacao.split('+') if p.strip()]
    if not vks:
        raise TelaRecusada('nenhuma tecla')
    _mandar(*[_tecla_vk(v) for v in vks], *[_tecla_vk(v, True) for v in reversed(vks)])


# — o cartão ———————————————————————————————————————————————————————————————————
def resumo(acao: str, entrada: dict) -> str:
    if acao == 'tela_clicar':
        b = entrada.get('botao', 'esquerdo')
        verbo = 'Clicar duas vezes' if entrada.get('duplo') else 'Clicar com o botão direito' if b == 'direito' else 'Clicar'
        return f'{verbo} em ({entrada.get("x")}, {entrada.get("y")})'
    if acao == 'tela_digitar':
        return 'Digitar um texto'
    if acao == 'tela_tecla':
        return f'Apertar {entrada.get("teclas", "")}'
    if acao == 'tela_rolar':
        return f'Rolar pra {entrada.get("direcao", "baixo")}'
    if acao == 'tela_mover':
        return f'Levar o mouse até ({entrada.get("x")}, {entrada.get("y")})'
    return f'Usar a tela: {acao}'


def programa_alvo(acao: str, entrada: dict) -> tuple[str, str]:
    """(processo, nome) de onde a ação cai: no ponto, pro mouse; a da frente, pro teclado."""
    try:
        if acao in ('tela_clicar', 'tela_rolar', 'tela_mover'):
            p, t = janela_em(*_real(float(entrada.get('x', -1)), float(entrada.get('y', -1))))
        else:
            p, t = janela_ativa()
    except (TelaRecusada, TypeError, ValueError, OSError):
        return '', ''
    return p, nome_do_programa(p, t)


def imagem_do_cartao(acao: str, entrada: dict) -> str | None:
    try:
        if acao in ('tela_clicar', 'tela_rolar', 'tela_mover'):
            return recorte_marcado(float(entrada['x']), float(entrada['y']))
        return miniatura()
    except Exception:  # noqa: BLE001 — sem print o cartão sai sem imagem
        log.warning('o print do cartão falhou', exc_info=True)
        return None
