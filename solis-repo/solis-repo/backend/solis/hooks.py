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
import tempfile
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
