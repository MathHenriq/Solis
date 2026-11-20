"""A aprovação do Solis: o que é livre e o que pede o Matheus, o cartão na
conversa, o "sempre" e o registro — pra qualquer cérebro.

Decisão do Matheus (18/11/2026): as funções são do Solis, não do Claude. A
aprovação nasceu dentro do agente.py (o Claude pelo Agent SDK) e saiu dele em
19/11/2026: o Claude traduz a Decisao pros tipos do SDK (agente._decidir), e o
corpo do Solis (corpo.py, a Groq, o Gemini, o local) usa direto. Este módulo
não importa o SDK do Claude.

O cartão: `por('etapa', ('aprovacao', pedido))` põe o pedido na conversa; o
Matheus responde por POST /aprovacoes/{id} (responder), que resolve o Future
esperando aqui; sem resposta em APROVACAO_MAX_S, é recusado.
"""
import asyncio
import concurrent.futures
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import banco, navegador, tela

# Quanto um pedido de aprovação espera o Matheus antes de virar "recusado".
APROVACAO_MAX_S = 10 * 60

# A lista de tarefas do próprio Claude (o plano): TaskCreate/TaskUpdate no
# CLI de agora, ligadas por CLAUDE_CODE_ENABLE_TODO_TOOLS (visto em 15/11/2026).
PLANO = {'TodoWrite', 'TaskCreate', 'TaskUpdate', 'TaskList', 'TaskGet'}
# Skill: ler as instruções de uma skill do Matheus (no Claude e no corpo) é livre.
LIVRES = {'WebSearch', 'WebFetch', 'ToolSearch', 'Task', 'Agent', 'Skill'} | PLANO
TERMINAL = {'Bash', 'PowerShell'}

LEITURA = {'Read', 'Glob', 'Grep', 'LS'}

# Pedidos de aprovação esperando o Matheus: id → Future (resolvido por
# responder_aprovacao, que roda no laço do servidor; o Future é seguro entre
# threads).
_pendentes: dict[str, concurrent.futures.Future] = {}


@dataclass
class Decisao:
    """O que a aprovação decidiu. `mensagem`: por que não (vai pro modelo).
    `sair_do_plano`: o plano foi aprovado (o Claude sai do modo de planejar)."""
    ok: bool
    mensagem: str | None = None
    sair_do_plano: bool = False


# "Sempre" respondido num cartão, por conversa: a regra (o comando exato, ou
# as edições) não pede de novo enquanto o servidor estiver de pé — como o
# "não perguntar de novo" do Claude Code, que também vale só pra sessão.
_sempre: dict[int | None, set[str]] = {}


def _regra(nome: str, entrada: dict, pagina: str | None = None) -> str:
    """O que um "sempre" libera: o comando exato (não o programa inteiro —
    sempre `git status` não pode liberar `git push`); as edições de arquivo
    todas juntas; no navegador, o site (como o Claude in Chrome); o resto, a
    ferramenta."""
    if navegador.acao(nome):
        return f'navegador:{navegador.site_da_acao(nome, entrada, pagina)}'
    if nome in ('Bash', 'PowerShell'):
        return f'{nome}:{(entrada.get("command") or "").strip()}'
    if nome in EDICAO:
        return 'edicao'
    return nome


def responder(id_: str, aprovado: bool, sempre: bool = False) -> bool:
    """O Matheus respondeu o cartão. False se o pedido já não existe.
    `sempre`: aprovar, e não perguntar de novo nesta conversa."""
    fut = _pendentes.get(id_)
    if fut is None or fut.done():
        return False
    fut.set_result('sempre' if aprovado and sempre else bool(aprovado))
    return True


def _diff(nome: str, entrada: dict, projeto: str | None = None, limite: int = 400) -> str | None:
    """O que muda, em diff unificado, pro cartão mostrar antes de aprovar:
    na edição, o trecho antigo contra o novo; ao reescrever, o arquivo de hoje
    contra o novo; arquivo novo, tudo como adição."""
    import difflib
    from . import agente
    pares = []
    if nome == 'Edit':
        pares = [(entrada.get('old_string') or '', entrada.get('new_string') or '')]
    elif nome == 'MultiEdit':
        pares = [(e.get('old_string') or '', e.get('new_string') or '') for e in entrada.get('edits') or []]
    elif nome == 'Write':
        antes = ''
        caminho = entrada.get('file_path')
        if caminho:
            p = Path(caminho)
            p = p if p.is_absolute() else agente._base(projeto) / p
            try:
                if p.is_file() and p.stat().st_size <= 512_000:
                    antes = p.read_text(encoding='utf-8', errors='replace')
            except OSError:
                pass
        pares = [(antes, entrada.get('content') or '')]
    else:
        return None
    linhas: list[str] = []
    for antes, depois in pares:
        bloco = list(difflib.unified_diff(antes.splitlines(), depois.splitlines(), lineterm='', n=3))[2:]
        linhas += bloco
    if not linhas:
        return None
    if len(linhas) > limite:
        linhas = linhas[:limite] + [f'… mais {len(linhas) - limite} linhas']
    return '\n'.join(linhas)


EDICAO = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit'}


# Os conectores da conta do claude.ai (Gmail, Agenda, Drive, Canva...): o CLI
# logado traz eles sozinho (o proxy do claude.ai) e as ferramentas chegam como
# mcp__claude_ai_<Conector>__<ação> — "claude.ai Google Calendar" com o que não
# é letra, número, _ ou - virando _ (visto em 13/11/2026, SDK 0.2.180).
_CONECTOR = re.compile(r'^mcp__claude_ai_(.+?)__(.+)$')


_MCP = re.compile(r'^mcp__(.+?)__(.+)$')
# Os do próprio Solis (as ferramentas dele e o navegador) têm regra própria.
_DO_SOLIS = {'solis', 'navegador'}


def conector_de(nome: str) -> tuple[str, str] | None:
    """('Google Calendar', 'create_event') de mcp__claude_ai_Google_Calendar__create_event.
    Um servidor MCP que o Matheus pôs (servidores_mcp.py) conta como conector:
    ('notion', 'search') de mcp__notion__search — ler é livre, mudar pede."""
    m = _CONECTOR.match(nome)
    if m:
        return m.group(1).replace('_', ' '), m.group(2)
    m = _MCP.match(nome)
    return (m.group(1), m.group(2)) if m and m.group(1) not in _DO_SOLIS else None


def _normalizar_servidor(nome: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', nome)


def resumo(nome: str, entrada: dict) -> str:
    """O que vai aparecer no cartão de aprovação, em português."""
    c = conector_de(nome)
    if c:
        return f'Usar o {c[0]}: {c[1]}'
    if nome in ('Write', 'Edit', 'MultiEdit', 'NotebookEdit'):
        alvo = entrada.get('file_path') or entrada.get('notebook_path') or ''
        return f'{"Criar ou reescrever" if nome == "Write" else "Editar"} {alvo}'
    if nome in ('Bash', 'PowerShell'):
        return f'Rodar no terminal: {entrada.get("command", "")[:300]}'
    if nome in LEITURA:
        return f'Ler fora das pastas autorizadas: {entrada.get("file_path") or entrada.get("path") or ""}'
    if nome == 'ExitPlanMode':
        return 'Seguir com o plano'
    if navegador.acao(nome):
        return 'No navegador: ' + navegador.resumo(nome, entrada)
    if nome in TELA_PEDEM:
        return 'Na tela: ' + tela.resumo(nome.removeprefix('mcp__solis__'), entrada)
    if nome == 'mcp__solis__agendar_tarefa':
        from . import agendadas
        try:
            agendadas.validar(entrada.get('frequencia', ''), entrada.get('hora', ''), entrada.get('dia_semana'),
                              entrada.get('data'))
            quando = agendadas.descrever({**entrada, 'dia_semana': entrada.get('dia_semana'),
                                          'data': entrada.get('data')})
        except (agendadas.AgendaInvalida, KeyError, IndexError, TypeError):
            quando = 'horário inválido'
        return f'Agendar "{entrada.get("nome", "")}": {quando}'
    return f'Usar {nome}'


def _alvo(nome: str, entrada: dict, limite: int = 160) -> str:
    for chave in ('file_path', 'notebook_path', 'path', 'pattern', 'query', 'url', 'command', 'description',
                  'texto', 'titulo', 'busca', 'plan', 'pedido', 'skill', 'teclas', 'direcao'):
        if entrada.get(chave):
            valor = str(entrada[chave])
            if len(valor) > limite and chave in ('file_path', 'notebook_path', 'path'):
                # Num caminho, o que importa é o fim (o nome do arquivo).
                return '…' + valor[-(limite - 1):]
            return valor[:limite]
    return ''



# As do Solis que pedem o Matheus antes (o resto das mcp__solis__ é livre).
# As ações na tela (tela.py) pedem, uma a uma ou "sempre neste programa".
TELA_PEDEM = {f'mcp__solis__tela_{a}' for a in ('clicar', 'digitar', 'tecla', 'rolar', 'mover')}
SOLIS_PEDEM = {'mcp__solis__agendar_tarefa'} | TELA_PEDEM
SOLIS_LIVRES = ['mcp__solis__hora', 'mcp__solis__criar_lembrete', 'mcp__solis__marcar_compromisso',
                'mcp__solis__ver_agenda', 'mcp__solis__ver_tarefas', 'mcp__solis__buscar_memoria']


async def decidir(nome: str, entrada: dict, por, ids: set | None = None, projeto: str | None = None,
                   modo: str = 'pedir', conversa: int | None = None, ajudante: str | None = None,
                   so_le: bool = False, pagina: str | None = None):
    """Livre, ou um cartão na conversa esperando o Matheus — pra qualquer cérebro
    (o can_use_tool do Claude traduz pro SDK em agente._decidir; o corpo usa
    direto). `modo` aceitar: editar arquivo dentro do projeto não pede (fica
    no registro)."""
    from . import agente  # a pasta de trabalho e o projeto do Claude (Read, Edit...)

    if nome in LIVRES or (nome.startswith('mcp__solis__') and nome not in SOLIS_PEDEM):
        return Decisao(True)
    # No navegador, abrir e ler página é livre (como o WebFetch); agir nela pede.
    # No navegador de sempre, abrir um site novo também pede (navegador.pede).
    if navegador.acao(nome) in navegador.LIVRES and not navegador.pede(nome, entrada, pagina):
        return Decisao(True)
    # Um conector que só lê (o próprio conector marca: readOnly) é livre, como
    # ler arquivo na pasta autorizada; criar, mudar, apagar ou compartilhar pede.
    if so_le and conector_de(nome):
        return Decisao(True)
    caminho = entrada.get('file_path') or entrada.get('notebook_path') or entrada.get('path')
    if nome in LEITURA and agente._dentro(caminho, projeto):
        return Decisao(True)
    programa = ('', '')
    if nome in TELA_PEDEM:
        programa = await asyncio.to_thread(tela.programa_alvo, nome.removeprefix('mcp__solis__'), entrada)
        if programa[0] in tela.SOLIS:
            banco.registrar_acao(conversa, nome, entrada, 'recusado: cai no Solis', False)
            return Decisao(False, 'Isso cai numa janela do próprio Solis: lá nenhum cérebro mexe. '
                                                'Peça ao Matheus pra trazer o outro programa pra frente.')
        if programa[0] and f'tela:{programa[0]}' in _sempre.get(conversa, set()):
            banco.registrar_acao(conversa, nome, entrada, 'aprovado sempre: ' + resumo(nome, entrada), True)
            return Decisao(True)
    if _regra(nome, entrada, pagina) in _sempre.get(conversa, set()):
        banco.registrar_acao(conversa, nome, entrada, 'aprovado sempre: ' + resumo(nome, entrada), True)
        return Decisao(True)
    if modo == 'aceitar' and nome in EDICAO and agente._no_projeto(caminho, projeto):
        banco.registrar_acao(None, nome, entrada, 'aceito pelo modo: ' + resumo(nome, entrada), True)
        return Decisao(True)
    id_ = uuid.uuid4().hex[:12]
    fut: concurrent.futures.Future = concurrent.futures.Future()
    _pendentes[id_] = fut
    if ids is not None:
        ids.add(id_)
    pedido = {'id': id_, 'ferramenta': nome, 'resumo': resumo(nome, entrada),
              # Num conector: o que vai ser mandado, inteiro (o cartão mostra).
              **({'entrada': json.dumps(entrada, ensure_ascii=False, indent=2)[:3000]} if conector_de(nome) else {}),
              **({'ajudante': ajudante} if ajudante is not None else {}),
              # Num conector, a ação (create_event); o que vai, inteiro, em `entrada`.
              'alvo': (conector_de(nome) or ('', ''))[1] or _alvo(nome, entrada, 6000 if nome == 'ExitPlanMode' else 1000)}
    if nome == 'mcp__solis__agendar_tarefa':
        # Agendar: na linha, o nome e quando ("Revisão · Toda sexta às 17:00");
        # o pedido inteiro embaixo, legível — é o que vai rodar sem ninguém olhando.
        pedido['alvo'] = resumo(nome, entrada).removeprefix('Agendar ').replace('": ', '" · ', 1)
        pedido['entrada'] = str(entrada.get('pedido') or '')[:3000]
    if navegador.acao(nome):
        # No navegador: o que vai fazer e em qual site; o que vai escrever (ou
        # os campos, o script) inteiro embaixo.
        pedido['alvo'] = navegador.resumo(nome, entrada)
        if navegador.site_da_acao(nome, entrada, pagina):
            pedido['site'] = navegador.site_da_acao(nome, entrada, pagina)
        if navegador.detalhe(nome, entrada):
            pedido['entrada'] = navegador.detalhe(nome, entrada)[:3000]
    if nome in TELA_PEDEM:
        # Na tela: o que vai fazer, em qual programa, e o print — o pedaço em
        # volta do clique, marcado; pra digitar e tecla, a tela inteira pequena.
        acao = nome.removeprefix('mcp__solis__')
        pedido['alvo'] = tela.resumo(acao, entrada)
        if programa[1]:
            pedido['site'] = programa[1]
        if acao == 'tela_digitar':
            pedido['entrada'] = str(entrada.get('texto') or '')[:3000]
        imagem = await asyncio.to_thread(tela.imagem_do_cartao, acao, entrada)
        if imagem:
            pedido['imagem'] = imagem
    diff = _diff(nome, entrada, projeto)
    if diff:
        pedido['diff'] = diff
    por('etapa', ('aprovacao', pedido))
    try:
        ok = await asyncio.wait_for(asyncio.wrap_future(fut), APROVACAO_MAX_S)
    except asyncio.TimeoutError:
        ok = False
    finally:
        _pendentes.pop(id_, None)
    # Agendar se aprova uma a uma; no navegador, o sempre é do site (sem site, não há).
    if ok == 'sempre' and nome not in SOLIS_PEDEM and not (
            navegador.acao(nome) and not navegador.site_da_acao(nome, entrada, pagina)):
        _sempre.setdefault(conversa, set()).add(_regra(nome, entrada, pagina))
    if ok == 'sempre' and nome in TELA_PEDEM and programa[0]:
        _sempre.setdefault(conversa, set()).add(f'tela:{programa[0]}')
    ok = bool(ok)
    por('etapa', ('aprovacao_resposta', {'id': id_, 'aprovado': ok}))
    banco.registrar_acao(conversa, nome, entrada, ('aprovado' if ok else 'recusado') + ': ' + resumo(nome, entrada), ok)
    if ok and nome == 'ExitPlanMode':
        # Plano aprovado: sai do modo de planejar e executa — pedindo
        # aprovação pro que escreve, como no modo de sempre. A conversa
        # também volta pro modo de pedir (como o Claude Code faz).
        if conversa is not None:
            banco.guardar_modo(conversa, 'pedir')
            por('etapa', ('modo', {'modo': 'pedir'}))
        return Decisao(True, sair_do_plano=True)
    return Decisao(True) if ok else Decisao(False, 'O Matheus recusou.')
