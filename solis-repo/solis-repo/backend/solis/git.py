"""O git da pasta de projeto de uma conversa, na tela (docs/PARIDADE.md →
Trabalhar num projeto): o ramo, o que mudou, o diff de cada arquivo, e
commit, push e PR — cada um é o Matheus clicando, e vai pro registro de ações.

O Claude também usa git pelo terminal (com o cartão de aprovação); aqui é o
que o Claude Code Desktop mostra sem precisar pedir.

Tudo síncrono (subprocess): as rotas chamam por asyncio.to_thread.
"""
import os
import shutil
import subprocess
from pathlib import Path

DIFF_LINHAS = 400
# Push e PR falam com a rede: sem pergunta de senha no meio (travaria sem
# ninguém pra responder) e com um teto de tempo.
REDE_S = 120
LOCAL_S = 30


class GitFalhou(Exception):
    pass


def _git(pasta: str, *args: str, tempo: float = LOCAL_S, entrada: str | None = None) -> str:
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never', 'LC_ALL': 'C.UTF-8'}
    try:
        r = subprocess.run(
            ['git', '-C', pasta, *args], capture_output=True, timeout=tempo, env=env, input=entrada,
            encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except FileNotFoundError as e:
        raise GitFalhou('o git não está instalado') from e
    except subprocess.TimeoutExpired as e:
        raise GitFalhou(f'o git passou de {int(tempo)} s sem terminar') from e
    if r.returncode != 0:
        raise GitFalhou((r.stderr or r.stdout).strip()[-600:] or f'git {args[0]} falhou')
    return r.stdout


def repositorio(pasta: str | None) -> bool:
    """A pasta é a raiz de um repositório git (ou está dentro de um)?"""
    if not pasta or not Path(pasta).is_dir():
        return False
    try:
        return _git(pasta, 'rev-parse', '--is-inside-work-tree').strip() == 'true'
    except GitFalhou:
        return False


def _linhas_do_arquivo(caminho: Path) -> int:
    try:
        with caminho.open('rb') as f:
            dados = f.read(2_000_000)
    except OSError:
        return 0
    if b'\0' in dados[:8000]:
        return 0  # binário
    return dados.count(b'\n') + (1 if dados and not dados.endswith(b'\n') else 0)


def estado(pasta: str) -> dict:
    """{'repo', 'ramo', 'upstream', 'frente', 'atras', 'arquivos': [{caminho,
    status, mais, menos}], 'gh'}. status: M mudou, A novo, D apagado, R
    renomeado, U em conflito, ? fora do git."""
    if not repositorio(pasta):
        return {'repo': False}
    raiz = _git(pasta, 'rev-parse', '--show-toplevel').strip()
    saida = _git(raiz, 'status', '--porcelain=v1', '-b', '-z', '--untracked-files=all')
    partes = saida.split('\0')
    cabeca = partes[0][3:] if partes and partes[0].startswith('## ') else ''
    ramo, upstream, frente, atras = cabeca, None, 0, 0
    if '...' in cabeca:
        ramo, resto = cabeca.split('...', 1)
        upstream = resto.split(' ', 1)[0]
        if '[' in resto:
            for item in resto.split('[', 1)[1].rstrip(']').split(','):
                n, _, qual = item.strip().partition(' ')
                if n == 'ahead':
                    frente = int(qual or 0)
                elif n == 'behind':
                    atras = int(qual or 0)
    elif ' ' in cabeca:
        ramo = cabeca.split(' ')[0]  # "No commits yet on main"
    if ramo.startswith('No commits yet on '):
        ramo = ramo[len('No commits yet on '):]

    arquivos: list[dict] = []
    i = 1
    while i < len(partes):
        item = partes[i]
        i += 1
        if len(item) < 4:
            continue
        xy, caminho = item[:2], item[3:]
        if xy[0] == 'R' or xy[0] == 'C':
            i += 1  # o nome antigo vem no item seguinte
        if xy == '??':
            status = '?'
        elif 'U' in xy or xy in ('AA', 'DD'):
            status = 'U'
        else:
            status = next((c for c in (xy[0], xy[1]) if c in 'MADRC'), 'M')
            status = 'R' if status == 'C' else status
        arquivos.append({'caminho': caminho, 'status': status, 'mais': 0, 'menos': 0})

    # As linhas de cada um, contra o último commit (o que está no índice e o que não está).
    contagem: dict[str, tuple[int, int]] = {}
    try:
        for linha in _git(raiz, 'diff', 'HEAD', '--numstat', '--no-renames').splitlines():
            mais, menos, nome = linha.split('\t', 2)
            contagem[nome] = (int(mais) if mais.isdigit() else 0, int(menos) if menos.isdigit() else 0)
    except GitFalhou:
        pass  # repositório sem commit ainda
    for a in arquivos:
        if a['status'] == '?':
            a['mais'] = _linhas_do_arquivo(Path(raiz) / a['caminho'])
        elif a['caminho'] in contagem:
            a['mais'], a['menos'] = contagem[a['caminho']]
    return {'repo': True, 'raiz': raiz, 'ramo': ramo, 'upstream': upstream, 'frente': frente, 'atras': atras,
            'arquivos': arquivos, 'gh': shutil.which('gh') is not None}


def _dentro_do_repo(raiz: str, caminho: str) -> Path:
    p = (Path(raiz) / caminho).resolve()
    if not p.is_relative_to(Path(raiz).resolve()):
        raise GitFalhou('esse arquivo não é do repositório')
    return p


def diff(pasta: str, caminho: str) -> str:
    """O diff unificado de um arquivo contra o último commit; um arquivo novo,
    fora do git, vira só linhas que entram. Longo, corta com "… mais N linhas"."""
    if not repositorio(pasta):
        raise GitFalhou('a pasta não é um repositório git')
    raiz = _git(pasta, 'rev-parse', '--show-toplevel').strip()
    arquivo = _dentro_do_repo(raiz, caminho)
    rastreado = bool(_git(raiz, 'ls-files', '--', caminho).strip())
    if rastreado:
        try:
            texto = _git(raiz, 'diff', 'HEAD', '--no-color', '--', caminho)
        except GitFalhou:
            texto = _git(raiz, 'diff', '--cached', '--no-color', '--', caminho)
        linhas = texto.splitlines()
        # Sem o cabeçalho (diff --git, index, ---, +++): a tela já diz qual é o arquivo.
        while linhas and not linhas[0].startswith('@@'):
            linhas.pop(0)
    else:
        if not arquivo.is_file() or _linhas_do_arquivo(arquivo) == 0 and arquivo.stat().st_size:
            return '(arquivo binário)'
        conteudo = arquivo.read_text(encoding='utf-8', errors='replace').splitlines()
        linhas = [f'@@ -0,0 +1,{len(conteudo)} @@'] + ['+' + l for l in conteudo]
    if len(linhas) > DIFF_LINHAS:
        linhas = linhas[:DIFF_LINHAS] + [f'… mais {len(linhas) - DIFF_LINHAS} linhas']
    return '\n'.join(linhas)


def commit(pasta: str, mensagem: str) -> dict:
    """Tudo que mudou (inclusive o novo) num commit. Os hooks do projeto rodam
    como sempre; se um recusar, o erro volta e nada fica pela metade no índice."""
    mensagem = mensagem.strip()
    if not mensagem:
        raise GitFalhou('o commit precisa de uma mensagem')
    raiz = _git(pasta, 'rev-parse', '--show-toplevel').strip()
    _git(raiz, 'add', '-A')
    try:
        _git(raiz, 'commit', '-F', '-', entrada=mensagem, tempo=REDE_S)
    except GitFalhou:
        # Volta o índice como estava: o que foi adicionado agora sai de novo.
        try:
            _git(raiz, 'reset', '-q')
        except GitFalhou:
            pass
        raise
    return {'hash': _git(raiz, 'rev-parse', '--short', 'HEAD').strip(), 'mensagem': mensagem.splitlines()[0]}


def push(pasta: str) -> dict:
    """Manda os commits pro remoto. Sem upstream ainda: cria (origin, o mesmo nome)."""
    e = estado(pasta)
    if not e.get('repo'):
        raise GitFalhou('a pasta não é um repositório git')
    if e['upstream']:
        _git(e['raiz'], 'push', tempo=REDE_S)
    else:
        if 'origin' not in _git(e['raiz'], 'remote').split():
            raise GitFalhou('o repositório não tem remoto (origin)')
        _git(e['raiz'], 'push', '-u', 'origin', 'HEAD', tempo=REDE_S)
    return {'ramo': e['ramo']}


def pr(pasta: str) -> dict:
    """Abre o PR do ramo atual pelo gh, com o título e o texto dos commits."""
    if shutil.which('gh') is None:
        raise GitFalhou('o gh (GitHub CLI) não está instalado')
    e = estado(pasta)
    if not e.get('repo'):
        raise GitFalhou('a pasta não é um repositório git')
    env = {**os.environ, 'GH_PROMPT_DISABLED': '1'}
    try:
        r = subprocess.run(['gh', 'pr', 'create', '--fill'], cwd=e['raiz'], capture_output=True, timeout=REDE_S,
                           env=env, encoding='utf-8', errors='replace',
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as erro:
        raise GitFalhou('o gh passou do tempo') from erro
    if r.returncode != 0:
        raise GitFalhou((r.stderr or r.stdout).strip()[-600:])
    url = next((l for l in r.stdout.splitlines() if l.startswith('http')), r.stdout.strip())
    return {'url': url}
