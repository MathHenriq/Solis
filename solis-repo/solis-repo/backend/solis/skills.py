"""Skills (docs/PARIDADE.md): roteiros que o Matheus escreve uma vez e o
cérebro segue quando o pedido pede — como Configurações → Skills no Claude
Desktop.

De onde vêm:
- as da conta do claude.ai (as da Anthropic, como docx e pdf, e as dele, como
  as do Núcleo WIT): o CLI do Claude sincroniza em ~/.claude/skills/synced e
  manda nelas. Aqui só se lê e se liga/desliga; mudar é no claude.ai.
- as escritas no Solis (ou à mão): cada uma diz pra quem serve, porque uma
  skill escrita pro Claude não serve necessariamente pro GPT (o Matheus,
  15/11/2026). Pro Claude, em ~/.claude/skills/<nome>; pro Codex, em
  ~/.codex/skills/<nome>; pros dois, nas duas — o mesmo SKILL.md, que é o
  formato dos dois. Valem também no Claude Code e no Codex do terminal.

Desligar é só do Claude (o filtro de skills do SDK, ClaudeAgentOptions.skills):
a skill fica no disco e some da lista dele. Apagar manda a pasta pra lixeira
do Solis, não some de vez."""
from __future__ import annotations

import re
import shutil
import time
import unicodedata
from pathlib import Path

import yaml

from . import banco

PARA = ('claude', 'codex')
NOME_MAX = 64          # o limite do formato (Agent Skills)
DESCRICAO_MAX = 1024
CORPO_MAX = 60_000
_NOME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


class SkillInvalida(Exception):
    pass


def _casa() -> Path:
    return Path.home()


def pasta(para: str) -> Path:
    return _casa() / ('.claude' if para == 'claude' else '.codex') / 'skills'


def _sincronizadas() -> Path:
    return pasta('claude') / 'synced'


def lixeira() -> Path:
    return banco.pasta() / 'skills-apagadas'


def nome_de(texto: str) -> str:
    """'Resumo de reunião' → 'resumo-de-reuniao': o nome que o formato aceita."""
    sem_acento = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', sem_acento.lower()).strip('-')[:NOME_MAX].strip('-')


def ler_skill_md(caminho: Path) -> tuple[dict, str]:
    """O cabeçalho (name, description...) e o corpo de um SKILL.md."""
    texto = caminho.read_text(encoding='utf-8', errors='replace')
    if texto.startswith('---'):
        partes = texto.split('---', 2)
        if len(partes) == 3:
            try:
                cabecalho = yaml.safe_load(partes[1]) or {}
            except yaml.YAMLError:
                cabecalho = {}
            if isinstance(cabecalho, dict):
                return cabecalho, partes[2].lstrip('\n')
    return {}, texto


def _texto(valor) -> str:
    return ' '.join(str(valor or '').split())


# — a lista ———————————————————————————————————————————————————————————————————
def _da_conta() -> list[dict]:
    """As do claude.ai, pelo manifesto que o CLI escreve ao sincronizar."""
    import json
    saida = []
    for manifesto in sorted(_sincronizadas().glob('*/manifest.json')):
        try:
            dados = json.loads(manifesto.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for s in dados.get('skills') or []:
            nome = s.get('name') or s.get('skillId')
            if not nome:
                continue
            anthropic = str(s.get('source', '')).startswith('anthropic')
            saida.append({'nome': nome, 'descricao': _texto(s.get('description')), 'para': ['claude'],
                          'origem': 'anthropic' if anthropic else 'conta', 'editavel': False})
    return saida


def _locais(para: str) -> dict[str, dict]:
    """As de ~/.claude/skills ou ~/.codex/skills (sem as sincronizadas nem as
    do sistema do Codex): as escritas no Solis ou à mão."""
    saida = {}
    base = pasta(para)
    if not base.is_dir():
        return saida
    for skill_md in sorted(base.glob('*/SKILL.md')):
        dono = skill_md.parent.name
        if dono.startswith('.') or dono == 'synced':
            continue
        cabecalho, _ = ler_skill_md(skill_md)
        saida[dono] = {'nome': dono, 'descricao': _texto(cabecalho.get('description')),
                       'titulo': _texto(cabecalho.get('name')) or dono}
    return saida


def desligadas() -> list[str]:
    return list(banco.ajuste('skills_desligadas') or [])


def listar() -> list[dict]:
    """Todas, as suas primeiro: `nome`, `descricao`, `para` (claude, codex),
    `origem` (solis, conta, anthropic), `editavel`, `ligada` (só conta pro Claude)."""
    claude, codex = _locais('claude'), _locais('codex')
    suas = []
    for nome in sorted(set(claude) | set(codex)):
        s = claude.get(nome) or codex[nome]
        suas.append({'nome': nome, 'descricao': s['descricao'],
                     'para': [p for p, l in (('claude', claude), ('codex', codex)) if nome in l],
                     'origem': 'solis', 'editavel': True})
    da_conta = [s for s in _da_conta() if s['nome'] not in claude]
    fora = set(desligadas())
    todas = suas + sorted(da_conta, key=lambda s: (s['origem'] != 'conta', s['nome']))
    return [{**s, 'ligada': 'claude' not in s['para'] or s['nome'] not in fora} for s in todas]


def ler(nome: str) -> dict | None:
    """Uma das suas, inteira (pra editar): nome, descrição, instruções, pra quem."""
    para = [p for p in PARA if (pasta(p) / nome / 'SKILL.md').is_file()] if _NOME.match(nome or '') else []
    if not para:
        return None
    cabecalho, corpo = ler_skill_md(pasta(para[0]) / nome / 'SKILL.md')
    return {'nome': nome, 'descricao': _texto(cabecalho.get('description')), 'instrucoes': corpo.rstrip(),
            'para': para}


# — escrever, apagar, ligar ———————————————————————————————————————————————————
def _validar(nome: str, descricao: str, instrucoes: str, para: list[str]) -> None:
    if not _NOME.match(nome) or len(nome) > NOME_MAX:
        raise SkillInvalida('nome')
    if nome == 'synced':
        raise SkillInvalida('nome')
    if not descricao.strip() or len(descricao) > DESCRICAO_MAX:
        raise SkillInvalida('descrição')
    if not instrucoes.strip() or len(instrucoes) > CORPO_MAX:
        raise SkillInvalida('instruções')
    if not para or any(p not in PARA for p in para):
        raise SkillInvalida('pra quem')


def _conteudo(nome: str, descricao: str, instrucoes: str) -> str:
    cabecalho = yaml.safe_dump({'name': nome, 'description': ' '.join(descricao.split())}, allow_unicode=True,
                               sort_keys=False, width=100000)
    return f'---\n{cabecalho}---\n\n{instrucoes.strip()}\n'


def salvar(nome: str, descricao: str, instrucoes: str, para: list[str], antigo: str | None = None) -> dict:
    """Cria (ou muda, com `antigo`: o nome de antes) uma das suas. Escreve o
    SKILL.md em cada lugar de `para` e tira dos outros — mudando só o SKILL.md:
    scripts e arquivos de apoio que a pasta tiver ficam (e vão junto se o nome
    ou o lugar mudar)."""
    _validar(nome, descricao, instrucoes, para)
    if nome in {s['nome'] for s in _da_conta()} and nome != antigo:
        raise SkillInvalida('já existe uma skill da sua conta com esse nome')
    antes = ler(antigo) if antigo else None
    if antigo and antes is None:
        raise SkillInvalida('essa skill não existe mais')
    if (antigo or '') != nome and ler(nome) is not None:
        raise SkillInvalida('já existe uma skill com esse nome')
    origem = pasta(antes['para'][0]) / antigo if antes else None
    for p in PARA:
        destino = pasta(p) / nome
        if p in para:
            atual = pasta(p) / antigo if antes and p in antes['para'] else None
            if atual and atual != destino:
                atual.rename(destino)
            elif not destino.exists() and origem and origem.is_dir():
                shutil.copytree(origem, destino)
            destino.mkdir(parents=True, exist_ok=True)
            (destino / 'SKILL.md').write_text(_conteudo(nome, descricao, instrucoes), encoding='utf-8')
        elif antes and p in antes['para']:
            _pra_lixeira(pasta(p) / antigo, p)
    if antigo and antigo != nome and antigo in desligadas():
        banco.guardar_ajuste('skills_desligadas', [n for n in desligadas() if n != antigo])
    return next(s for s in listar() if s['nome'] == nome)


def _pra_lixeira(caminho: Path, para: str) -> None:
    if caminho.is_dir():
        lixeira().mkdir(parents=True, exist_ok=True)
        shutil.move(str(caminho), str(lixeira() / f'{caminho.name}-{para}-{time.strftime("%Y%m%d-%H%M%S")}'))


def apagar(nome: str) -> bool:
    """Tira uma das suas do Claude e do Codex. A pasta vai pra lixeira do
    Solis (skills-apagadas, ao lado do banco): dá pra voltar à mão."""
    s = ler(nome)
    if s is None:
        return False
    for p in s['para']:
        _pra_lixeira(pasta(p) / nome, p)
    banco.guardar_ajuste('skills_desligadas', [n for n in desligadas() if n != nome])
    return True


def ligar(nome: str, ligada: bool) -> None:
    fora = [n for n in desligadas() if n != nome] + ([] if ligada else [nome])
    banco.guardar_ajuste('skills_desligadas', fora)


# — o filtro do Claude ————————————————————————————————————————————————————————
def lembrar_descobertas(nomes: list[str]) -> None:
    """O que o CLI descobriu (as skills e os comandos dele, plugins): o filtro
    precisa da lista inteira, menos as desligadas."""
    conhecidas = set(banco.ajuste('skills_conhecidas') or [])
    if not set(nomes) <= conhecidas:
        banco.guardar_ajuste('skills_conhecidas', sorted(conhecidas | set(nomes)))


def filtro() -> list[str] | str:
    """O `skills` do ClaudeAgentOptions: 'all', ou todas as conhecidas menos as
    desligadas (as escritas agora entram mesmo antes do CLI descobrir)."""
    fora = set(desligadas())
    if not fora:
        return 'all'
    conhecidas = set(banco.ajuste('skills_conhecidas') or []) | set(_locais('claude')) \
        | {s['nome'] for s in _da_conta()}
    # O CLI chama as da conta de "anthropic-skills:docx": desligar "docx" tira as duas formas.
    return sorted(n for n in conhecidas if n not in fora and n.rsplit(':', 1)[-1] not in fora)
