"""Hooks do Claude (docs/PARIDADE.md; decisão do Matheus, 17/11/2026: fazer a tela).

Um hook é uma regra automática: "antes de rodar um comando, faça X", "quando a
resposta terminar, avise". Quem roda é o próprio Claude Code: os hooks moram na
configuração de usuário dele (~/.claude/settings.json → "hooks"), que o Claude
do Solis já carrega (agente.py: setting_sources "user"). Por isso valem aqui e
no Claude Code do terminal, e não valem pros outros cérebros (Codex, Groq,
local), que não têm isso.

Não há comando do CLI pra isso (o /hooks é uma tela interativa): o Solis lê e
grava o settings.json, mexendo só na chave "hooks" e mantendo o resto como
estava. Se o arquivo não for JSON válido, não grava nada (diz pra corrigir lá).
O formato:

    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "...", "timeout": 60}]}]}

Cada linha da tela é um desses comandos. Os de outro tipo (que não "command")
e os de evento que o Solis não conhece aparecem, mas não se mexem pela tela.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# Os eventos que a tela oferece, como o Matheus lê: só os que foram vistos
# disparando no Claude como o Solis o chama (Agent SDK, 17/11/2026, um pedido
# que leu um arquivo). A documentação tem 33; destes, "pedido de permissão" NÃO
# dispara aqui (quem aprova é o cartão do Solis), e os de falha, ajudante e
# resumo não foram vistos — não entram até serem. O Solis abre uma sessão do
# Claude a cada resposta: começo e fim de sessão são de cada resposta.
# Os que recebem `matcher`: a ferramenta, por nome ("Bash", "Write|Edit") ou
# expressão regular; vazio é toda ferramenta.
EVENTOS = {
    'UserPromptSubmit': 'Quando você manda uma mensagem',
    'PreToolUse': 'Antes de usar uma ferramenta',
    'PostToolUse': 'Depois de usar uma ferramenta',
    'Stop': 'Quando a resposta termina',
    'SessionStart': 'Quando o Claude começa a trabalhar',
    'SessionEnd': 'Quando o Claude termina de trabalhar',
}
COM_FERRAMENTA = {'PreToolUse', 'PostToolUse'}
TEMPO_MAX = 600


class HookInvalido(Exception):
    pass


def _casa() -> Path:
    return Path.home()


def _arquivo() -> Path:
    return _casa() / '.claude' / 'settings.json'


def _ler() -> dict:
    try:
        texto = _arquivo().read_text(encoding='utf-8')
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError as e:
        raise HookInvalido('a configuração do Claude Code (~/.claude/settings.json) não é JSON válido: '
                           'corrija por lá antes') from e
    except OSError as e:
        raise HookInvalido(f'não consegui ler a configuração do Claude Code ({e})') from e
    try:
        dados = json.loads(texto) if texto.strip() else {}
    except ValueError as e:
        raise HookInvalido('a configuração do Claude Code (~/.claude/settings.json) não é JSON válido: '
                           'corrija por lá antes') from e
    if not isinstance(dados, dict):
        raise HookInvalido('a configuração do Claude Code não tem o formato esperado')
    return dados


def _gravar(dados: dict) -> None:
    """Num arquivo ao lado e troca de uma vez: nunca fica meio escrito."""
    destino = _arquivo()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='settings.', suffix='.solis', dir=destino.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(json.dumps(dados, indent=2, ensure_ascii=False) + '\n')
        os.replace(temp, destino)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _ident(evento: str, ferramenta: str, comando: str, vez: int) -> str:
    base = f'{evento}\0{ferramenta}\0{comando}\0{vez}'
    return hashlib.sha1(base.encode('utf-8')).hexdigest()[:12]


def _linhas(dados: dict) -> list[dict]:
    saida, vistos = [], {}
    for evento, grupos in (dados.get('hooks') or {}).items():
        if not isinstance(grupos, list):
            continue
        for grupo in grupos:
            if not isinstance(grupo, dict):
                continue
            ferramenta = str(grupo.get('matcher') or '')
            for h in grupo.get('hooks') or []:
                if not isinstance(h, dict):
                    continue
                comando = str(h.get('command') or h.get('prompt') or '')
                chave = (evento, ferramenta, comando)
                vistos[chave] = vistos.get(chave, 0) + 1
                saida.append({
                    'id': _ident(evento, ferramenta, comando, vistos[chave]),
                    'evento': evento,
                    'rotulo': EVENTOS.get(evento, evento),
                    'ferramenta': ferramenta,
                    'comando': comando,
                    'tempo': h.get('timeout') if isinstance(h.get('timeout'), (int, float)) else None,
                    'tipo': h.get('type') or 'command',
                    'editavel': evento in EVENTOS and (h.get('type') or 'command') == 'command',
                })
    return saida


def listar() -> list[dict]:
    """Cada comando de hook do Claude: `id`, `evento` e o `rotulo` dele,
    `ferramenta` (o matcher), `comando`, `tempo` (segundos, ou None pro padrão
    do Claude Code), `tipo` e `editavel`."""
    return _linhas(_ler())


def _tirar(dados: dict, id_: str) -> dict:
    """Tira a linha `id_` do JSON (o grupo que fica vazio sai junto). A linha que saiu."""
    alvo = next((l for l in _linhas(dados) if l['id'] == id_), None)
    if alvo is None or not alvo['editavel']:
        raise HookInvalido('esse hook não existe mais')
    vistos = 0
    grupos = dados['hooks'][alvo['evento']]
    for grupo in list(grupos):
        if str(grupo.get('matcher') or '') != alvo['ferramenta']:
            continue
        for h in list(grupo.get('hooks') or []):
            if isinstance(h, dict) and str(h.get('command') or h.get('prompt') or '') == alvo['comando']:
                vistos += 1
                if _ident(alvo['evento'], alvo['ferramenta'], alvo['comando'], vistos) == id_:
                    grupo['hooks'].remove(h)
                    if not grupo['hooks']:
                        grupos.remove(grupo)
                    if not grupos:
                        del dados['hooks'][alvo['evento']]
                    if not dados['hooks']:
                        del dados['hooks']
                    return alvo
    raise HookInvalido('esse hook não existe mais')


def _validar(evento: str, ferramenta: str, comando: str, tempo: float | None) -> tuple[str, str, int | None]:
    if evento not in EVENTOS:
        raise HookInvalido('evento')
    comando = (comando or '').strip()
    if not comando or '\n' in comando:
        raise HookInvalido('comando')
    ferramenta = (ferramenta or '').strip() if evento in COM_FERRAMENTA else ''
    if tempo is not None and not (1 <= tempo <= TEMPO_MAX):
        raise HookInvalido('tempo')
    return ferramenta, comando, int(tempo) if tempo is not None else None


def salvar(evento: str, ferramenta: str, comando: str, tempo: float | None = None, antigo: str | None = None) -> dict:
    """Adiciona (ou muda, com `antigo`, o id da linha de antes) um comando de hook."""
    ferramenta, comando, tempo = _validar(evento, ferramenta, comando, tempo)
    dados = _ler()
    if antigo:
        _tirar(dados, antigo)
    hooks = dados.setdefault('hooks', {})
    grupos = hooks.setdefault(evento, [])
    grupo = next((g for g in grupos if isinstance(g, dict) and str(g.get('matcher') or '') == ferramenta), None)
    if grupo is None:
        grupo = {'matcher': ferramenta, 'hooks': []} if evento in COM_FERRAMENTA else {'hooks': []}
        grupos.append(grupo)
    novo = {'type': 'command', 'command': comando}
    if tempo is not None:
        novo['timeout'] = tempo
    grupo.setdefault('hooks', []).append(novo)
    _gravar(dados)
    iguais = [l for l in _linhas(dados) if (l['evento'], l['ferramenta'], l['comando']) == (evento, ferramenta, comando)]
    return iguais[-1]


def remover(id_: str) -> dict:
    dados = _ler()
    alvo = _tirar(dados, id_)
    _gravar(dados)
    return alvo


# — Testar antes de salvar (PARIDADE: faltava) ————————————————————————————————————
# Roda o comando uma vez, como o Claude Code roda (documentação dele, lida em
# 19/11/2026): no Windows pelo Git Bash, ou pelo PowerShell quando não há Git
# Bash; o que aconteceu em JSON na entrada; CLAUDE_PROJECT_DIR no ambiente. O
# código de saída diz o efeito: 0 deu certo, 2 bloqueia, outro é erro que não
# bloqueia. O padrão do tempo é o dele: 600 s (30 s pra mensagem).
TESTE_MAX = 60          # o teste espera no máximo isso, mesmo que o hook possa mais
SAIDA_MAX = 4000


def padrao_de_tempo(evento: str) -> int:
    return 30 if evento == 'UserPromptSubmit' else TEMPO_MAX


def _git_bash() -> str | None:
    """O bash do Git pra Windows, onde o Claude Code procura (nunca o bash do
    WSL, em System32). Fora do Windows, o sh."""
    if os.name != 'nt':
        return shutil.which('sh')
    escolhido = os.environ.get('CLAUDE_CODE_GIT_BASH_PATH')
    if escolhido and Path(escolhido).is_file():
        return escolhido
    for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'),
                 os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs')):
        if base and (Path(base) / 'Git' / 'bin' / 'bash.exe').is_file():
            return str(Path(base) / 'Git' / 'bin' / 'bash.exe')
    git = shutil.which('git')
    if git and (Path(git).resolve().parent.parent / 'bin' / 'bash.exe').is_file():
        return str(Path(git).resolve().parent.parent / 'bin' / 'bash.exe')
    return None


def exemplo(evento: str, ferramenta: str, pasta: str) -> dict:
    """O que o Claude manda na entrada do hook, com valores de teste."""
    base = {'session_id': 'teste-do-solis', 'transcript_path': '', 'cwd': pasta, 'hook_event_name': evento}
    if evento in COM_FERRAMENTA:
        # A primeira ferramenta do matcher ("Write|Edit" → Write); expressão ou vazio → Bash.
        nome = ferramenta.split('|')[0].strip() if re.fullmatch(r'[\w|]+', ferramenta or '') else 'Bash'
        entrada = {'Bash': {'command': 'echo teste do Solis', 'description': 'Teste do Solis'},
                   'PowerShell': {'command': 'echo teste do Solis', 'description': 'Teste do Solis'},
                   'Write': {'file_path': str(Path(pasta) / 'teste.txt'), 'content': 'teste do Solis'},
                   'Edit': {'file_path': str(Path(pasta) / 'teste.txt'), 'old_string': 'teste',
                            'new_string': 'teste do Solis'},
                   'Read': {'file_path': str(Path(pasta) / 'teste.txt')}}.get(nome, {})
        base.update(tool_name=nome, tool_input=entrada, tool_use_id='toolu_teste_do_solis')
        if evento == 'PostToolUse':
            base['tool_response'] = ({'stdout': 'teste do Solis', 'stderr': '', 'interrupted': False}
                                     if nome in ('Bash', 'PowerShell') else {'success': True})
    elif evento == 'UserPromptSubmit':
        base['prompt'] = 'Mensagem de teste do Solis'
    elif evento == 'Stop':
        base.update(stop_hook_active=False, last_assistant_message='Resposta de teste do Solis.')
    elif evento == 'SessionStart':
        base['source'] = 'startup'
    elif evento == 'SessionEnd':
        base['reason'] = 'other'
    return base


_BLOQUEIA = {
    'PreToolUse': 'a ferramenta não roda, e o que saiu em erros vai pro Claude como o motivo',
    'PostToolUse': 'o Claude recebe o que saiu em erros',
    'UserPromptSubmit': 'a mensagem não vai pro Claude',
    'Stop': 'o Claude continua trabalhando em vez de parar',
}


def _efeito(evento: str, codigo: int | None, estourou: bool, limite: int, pedido: int) -> str:
    if estourou:
        if pedido > limite:
            return f'Passou de {limite} s, o máximo que o teste espera (o hook pode até {pedido} s no Claude).'
        return f'Passou de {limite} s: no Claude, ele seria interrompido e o Claude seguiria.'
    if codigo == 0:
        return 'Deu certo (código 0). ' + (
            'No Claude, o que ele escrever vai junto como contexto.' if evento in ('UserPromptSubmit', 'SessionStart')
            else 'No Claude, segue tudo normal.')
    if codigo == 2:
        return 'Código 2: no Claude, isso bloqueia — ' + _BLOQUEIA.get(evento, 'o Claude mostra o que saiu em erros') + '.'
    return f'Código {codigo}: um erro que não bloqueia. No Claude, a ação segue e aparece um aviso.'


def testar(evento: str, ferramenta: str, comando: str, tempo: float | None = None,
           pasta: str | None = None) -> dict:
    """Roda o comando uma vez com o exemplo do evento. {codigo, saida, erros,
    segundos, shell, estourou, efeito}."""
    ferramenta, comando, tempo = _validar(evento, ferramenta, comando, tempo)
    if pasta is None:
        from .agente import _pasta_trabalho
        pasta = str(_pasta_trabalho())
    pedido = tempo or padrao_de_tempo(evento)
    limite = min(pedido, TESTE_MAX)
    bash = _git_bash()
    args = [bash, '-c', comando] if bash else ['powershell', '-NoProfile', '-Command', comando]
    shell = ('Git Bash' if os.name == 'nt' else 'sh') if bash else 'PowerShell'
    t0 = time.monotonic()
    estourou, codigo, saida, erros = False, None, '', ''
    try:
        r = subprocess.run(args, input=json.dumps(exemplo(evento, ferramenta, pasta), ensure_ascii=False),
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=limite,
                           cwd=pasta, env={**os.environ, 'CLAUDE_PROJECT_DIR': pasta},
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        codigo, saida, erros = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        estourou = True
        saida = (e.stdout or b'').decode('utf-8', 'replace') if isinstance(e.stdout, bytes) else (e.stdout or '')
        erros = (e.stderr or b'').decode('utf-8', 'replace') if isinstance(e.stderr, bytes) else (e.stderr or '')
    except OSError as e:
        raise HookInvalido(f'não consegui rodar: {e}') from e
    return {'codigo': codigo, 'saida': saida[-SAIDA_MAX:], 'erros': erros[-SAIDA_MAX:],
            'segundos': round(time.monotonic() - t0, 1), 'shell': shell, 'estourou': estourou,
            'efeito': _efeito(evento, codigo, estourou, limite, pedido)}
