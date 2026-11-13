"""Criar documentos de verdade (.docx, .xlsx, .pptx, .pdf) — docs/PARIDADE.md.

Quem sabe fazer cada formato são as skills da conta do claude.ai do Matheus
(docx, xlsx, pptx, pdf), que o CLI traz pela fonte "user" (agente._sessao). Elas
usam bibliotecas que a máquina não tem: sem isto, o Claude instala a cada vez,
pedindo cartão e enchendo a pasta de trabalho de node_modules.

Aqui: uma pasta só do Solis com essas bibliotecas, instalada uma vez (o botão
"Preparar documentos", em Configurações), e o caminho dela nas sessões do
Claude (NODE_PATH e PYTHONPATH). Nada vai pro sistema.

Fora daqui, de propósito: o LibreOffice e o pandoc (converter e conferir), que
são programas grandes de instalar no Windows — as skills criam sem eles.
"""
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger('solis.documentos')

# O que as skills de documento usam (contado nos SKILL.md e scripts delas,
# 13/11/2026): docx e pptxgenjs no Node; o resto no Python.
NODE = ('docx', 'pptxgenjs')
PYTHON = ('openpyxl', 'python-pptx', 'pdfplumber', 'reportlab', 'defusedxml', 'pypdf')
# O nome de importar de cada pacote do Python, pra conferir.
IMPORTA = {'openpyxl': 'openpyxl', 'python-pptx': 'pptx', 'pdfplumber': 'pdfplumber', 'reportlab': 'reportlab',
           'defusedxml': 'defusedxml', 'pypdf': 'pypdf'}
INSTALAR_S = 600


def pasta() -> Path:
    """%APPDATA%/Solis/ferramentas — a mesma pro app e pros testes (o banco
    pode mudar com SOLIS_BANCO; as bibliotecas não precisam)."""
    if os.environ.get('SOLIS_FERRAMENTAS'):
        return Path(os.environ['SOLIS_FERRAMENTAS'])
    if os.name == 'nt' and os.environ.get('APPDATA'):
        return Path(os.environ['APPDATA']) / 'Solis' / 'ferramentas'
    return Path.home() / '.local' / 'share' / 'solis' / 'ferramentas'


def _python() -> str | None:
    """O Python que o terminal do Claude vai usar (o do PATH): as bibliotecas
    com parte compilada (lxml, Pillow) têm de ser da mesma versão dele."""
    return shutil.which('python') or shutil.which('py')


def _sem_janela() -> int:
    return getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def estado() -> dict:
    """{'pronto', 'falta': [...], 'pasta', 'node': bool, 'python': bool}"""
    base = pasta()
    falta = [n for n in NODE if not (base / 'node' / 'node_modules' / n / 'package.json').exists()]
    py = base / 'python'
    falta += [p for p in PYTHON if not (py / IMPORTA[p]).exists()]
    return {'pronto': not falta, 'falta': falta, 'pasta': str(base),
            'node': shutil.which('npm') is not None, 'python': _python() is not None}


def env() -> dict[str, str]:
    """Pras sessões do Claude: onde estão as bibliotecas (só o que existe)."""
    base = pasta()
    e: dict[str, str] = {}
    if (base / 'node' / 'node_modules').is_dir():
        e['NODE_PATH'] = str(base / 'node' / 'node_modules')
    if (base / 'python').is_dir():
        atual = os.environ.get('PYTHONPATH')
        e['PYTHONPATH'] = str(base / 'python') + (os.pathsep + atual if atual else '')
    return e


class PrepararFalhou(Exception):
    pass


def _rodar(cmd: list[str], **kw) -> None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=INSTALAR_S, creationflags=_sem_janela(), **kw)
    except FileNotFoundError as e:
        raise PrepararFalhou(f'{cmd[0]} não está instalado') from e
    except subprocess.TimeoutExpired as e:
        raise PrepararFalhou(f'{cmd[0]} passou de {INSTALAR_S // 60} minutos') from e
    if r.returncode != 0:
        raise PrepararFalhou((r.stderr or r.stdout).strip()[-500:] or f'{cmd[0]} falhou')


def preparar() -> dict:
    """Baixa e instala as bibliotecas na pasta do Solis (npm e PyPI, os
    repositórios oficiais). Demora um ou dois minutos. Síncrono: a rota chama
    por asyncio.to_thread."""
    base = pasta()
    (base / 'node').mkdir(parents=True, exist_ok=True)
    npm = shutil.which('npm')
    if not npm:
        raise PrepararFalhou('o Node.js (npm) não está instalado')
    python = _python()
    if not python:
        raise PrepararFalhou('o Python não está instalado')
    log.info('preparando documentos em %s', base)
    _rodar([npm, 'install', '--prefix', str(base / 'node'), '--no-audit', '--no-fund', '--silent', *NODE])
    _rodar([python, '-m', 'pip', 'install', '--target', str(base / 'python'), '--upgrade', '--quiet',
            '--disable-pip-version-check', *PYTHON])
    e = estado()
    if not e['pronto']:
        raise PrepararFalhou('instalou, mas ainda falta: ' + ', '.join(e['falta']))
    return e


# — o arquivo criado, pra abrir ————————————————————————————————————————————————
# O que aparece embaixo da resposta como "arquivo criado": documentos e
# imagens, não código (código tem o diff e o git).
EXTENSOES = {'.docx', '.xlsx', '.pptx', '.pdf', '.csv', '.html', '.htm', '.png', '.jpg', '.jpeg', '.svg', '.odt', '.ods',
             '.odp'}
FORA = {'node_modules', '__pycache__', '.git', '.venv', 'venv', 'dist', 'build', '.claude'}


def fotografia(raiz: Path, profundidade: int = 2) -> dict[str, float]:
    """Os documentos da pasta e quando cada um mudou (pra ver, no fim da
    resposta, o que o Claude criou). Raso: a pasta e dois níveis."""
    vistos: dict[str, float] = {}

    def andar(p: Path, nivel: int) -> None:
        try:
            itens = list(os.scandir(p))
        except OSError:
            return
        for it in itens:
            if it.is_dir(follow_symlinks=False):
                if nivel < profundidade and it.name not in FORA and not it.name.startswith('.'):
                    andar(Path(it.path), nivel + 1)
            elif Path(it.name).suffix.lower() in EXTENSOES:
                try:
                    vistos[it.path] = it.stat().st_mtime
                except OSError:
                    pass
    andar(raiz, 0)
    return vistos


def novos(antes: dict[str, float], depois: dict[str, float], limite: int = 10) -> list[str]:
    """Os que apareceram ou mudaram, o mais novo primeiro."""
    lista = [c for c, t in depois.items() if c not in antes or t > antes[c]]
    return sorted(lista, key=lambda c: depois[c], reverse=True)[:limite]


def abrir(caminho: str, mostrar_na_pasta: bool = False) -> None:
    """Abre no programa do Windows (Word, Excel...) ou mostra na pasta. Só
    documento — nunca um executável."""
    p = Path(caminho)
    if p.suffix.lower() not in EXTENSOES or not p.is_file():
        raise PrepararFalhou('esse arquivo não pode ser aberto daqui')
    if mostrar_na_pasta:
        if os.name == 'nt':
            subprocess.Popen(['explorer', '/select,', str(p)])
        else:
            subprocess.Popen(['xdg-open', str(p.parent)])
    elif os.name == 'nt':
        os.startfile(str(p))  # noqa: S606 — o programa padrão do documento
    else:
        subprocess.Popen(['xdg-open' if sys.platform != 'darwin' else 'open', str(p)])
