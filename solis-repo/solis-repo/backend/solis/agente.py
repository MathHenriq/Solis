"""O Claude com ferramentas, pelo Claude Agent SDK (o Claude Code como biblioteca).

O primeiro marco do Solis (docs/VISAO.md): o Matheus parar de usar o Claude
Desktop. Aqui o cérebro Claude deixa de ser "só conversa" (o CLI com as
ferramentas desligadas) e ganha as ferramentas do Claude Code — ler, escrever e
editar arquivos, terminal, buscar e ler na web, subagentes — mais as do próprio
Solis (hora, lembretes, tarefas, agenda, memória), por um servidor MCP no processo.

Permissões — o que é livre e o que pede o Matheus:
- livre: pesquisar e ler na web, as ferramentas do Solis, e ler/buscar arquivos
  DENTRO das pastas autorizadas (Ferramentas → Arquivos) e da pasta de trabalho;
- pede aprovação (um cartão na conversa, POST /aprovacoes/{id}): escrever,
  editar, rodar comando, ler fora das pastas autorizadas, e qualquer outra coisa.
O que é privado não chega aqui: o roteador tira do prompt (como antes).

Autenticação: o Claude logado na conta do Matheus (o mesmo CLI de sempre). Num
produto vendido, a política da Anthropic exige chave de API (docs/VISAO.md).

O SDK roda numa thread com o próprio laço de eventos (Proactor, no Windows): o
uvicorn com --reload usa um laço que não abre processos (NotImplementedError,
o mesmo motivo dos avisos.py), e o SDK sobe o CLI como processo.
"""
import asyncio
import concurrent.futures
import contextlib
import glob
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from . import banco, pc
from .etapas import MUDA

log = logging.getLogger('solis.agente')

# Quanto um pedido de aprovação espera o Matheus antes de virar "recusado".
APROVACAO_MAX_S = 10 * 60
RODADAS_MAX = 40

LIVRES = {'WebSearch', 'WebFetch', 'TodoWrite', 'ToolSearch', 'Task', 'Agent'}
TERMINAL = {'Bash', 'PowerShell'}

# A saída de um comando, ao vivo e no fim: as últimas linhas (a tela mostra
# um terminal pequeno; o Claude leu a saída inteira).
SAIDA_MAX = 4000
SAIDA_LINHAS = 40
_ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07')

LEITURA = {'Read', 'Glob', 'Grep', 'LS'}

# Pedidos de aprovação esperando o Matheus: id → Future (resolvido por
# responder_aprovacao, que roda no laço do servidor; o Future é seguro entre
# threads).
_pendentes: dict[str, concurrent.futures.Future] = {}


class AgenteFalhou(Exception):
    pass


# O modelo e o quanto ele pensa, como o seletor do Claude Desktop. Os nomes
# curtos são os do CLI (`claude --model`): sempre o mais novo de cada família.
# None = o padrão da conta.
MODELOS = ('fable', 'opus', 'sonnet', 'haiku')
ESFORCOS = ('low', 'medium', 'high', 'xhigh', 'max')


def ajustes() -> dict:
    return {'modelo': banco.ajuste('claude_modelo'), 'esforco': banco.ajuste('claude_esforco')}


def guardar_ajustes(modelo: str | None, esforco: str | None) -> dict:
    if modelo is not None and modelo not in MODELOS:
        raise ValueError('modelo')
    if esforco is not None and esforco not in ESFORCOS:
        raise ValueError('esforco')
    banco.guardar_ajuste('claude_modelo', modelo)
    banco.guardar_ajuste('claude_esforco', esforco)
    return ajustes()


# "Sempre" respondido num cartão, por conversa: a regra (o comando exato, ou
# as edições) não pede de novo enquanto o servidor estiver de pé — como o
# "não perguntar de novo" do Claude Code, que também vale só pra sessão.
_sempre: dict[int | None, set[str]] = {}


def _regra(nome: str, entrada: dict) -> str:
    """O que um "sempre" libera: o comando exato (não o programa inteiro —
    sempre `git status` não pode liberar `git push`); as edições de arquivo
    todas juntas; o resto, a ferramenta."""
    if nome in ('Bash', 'PowerShell'):
        return f'{nome}:{(entrada.get("command") or "").strip()}'
    if nome in EDICAO:
        return 'edicao'
    return nome


def responder_aprovacao(id_: str, aprovado: bool, sempre: bool = False) -> bool:
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
            p = p if p.is_absolute() else _base(projeto) / p
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


def _pasta_trabalho() -> Path:
    pasta = banco.caminho_padrao().parent / 'trabalho'
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _base(projeto: str | None = None) -> Path:
    """Onde o Claude trabalha: a pasta do projeto da conversa, ou a de trabalho do Solis."""
    return Path(projeto).resolve() if projeto else _pasta_trabalho().resolve()


def _raizes(projeto: str | None = None) -> list[Path]:
    """Onde ler é livre: o lugar de trabalho primeiro, depois a pasta de
    trabalho do Solis (quando há projeto) e as autorizadas em Ferramentas."""
    raizes = [_base(projeto)]
    if projeto:
        raizes.append(_pasta_trabalho().resolve())
    return raizes + [Path(p).resolve() for p in pc.pastas()]


def _dentro(caminho: str | None, projeto: str | None = None) -> bool:
    """O caminho está numa pasta autorizada (ou é o lugar de trabalho)?"""
    if not caminho:
        return True  # sem caminho: Glob/Grep no lugar de trabalho
    p = Path(caminho)
    if not p.is_absolute():
        p = _base(projeto) / p
    try:
        p = p.resolve()
    except OSError:
        return False
    return any(p == r or p.is_relative_to(r) for r in _raizes(projeto)) or _saida_de_comando(p)


def _saida_de_comando(p: Path) -> bool:
    """A saída de um comando que o próprio Claude rodou em segundo plano: o CLI
    guarda em <temp>/claude/<pasta>/<sessão>/tasks/<tarefa>.output e diz pra
    ele ler dali. Ler isso é livre, como no Claude Code; o resto do temporário não."""
    try:
        temp = Path(tempfile.gettempdir()).resolve() / 'claude'
    except OSError:
        return False
    return p.suffix == '.output' and p.parent.name == 'tasks' and p.is_relative_to(temp) \
        and len(p.relative_to(temp).parts) == 4


EDICAO = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit'}


def _no_projeto(caminho: str | None, projeto: str | None) -> bool:
    """O arquivo está dentro da pasta do projeto (não só numa autorizada)?"""
    if not caminho or not projeto:
        return False
    base = _base(projeto)
    p = Path(caminho)
    try:
        p = (p if p.is_absolute() else base / p).resolve()
    except OSError:
        return False
    return p == base or p.is_relative_to(base)


# Os conectores da conta do claude.ai (Gmail, Agenda, Drive, Canva...): o CLI
# logado traz eles sozinho (o proxy do claude.ai) e as ferramentas chegam como
# mcp__claude_ai_<Conector>__<ação> — "claude.ai Google Calendar" com o que não
# é letra, número, _ ou - virando _ (visto em 13/11/2026, SDK 0.2.180).
_CONECTOR = re.compile(r'^mcp__claude_ai_(.+?)__(.+)$')


def conector_de(nome: str) -> tuple[str, str] | None:
    """('Google Calendar', 'create_event') de mcp__claude_ai_Google_Calendar__create_event."""
    m = _CONECTOR.match(nome)
    return (m.group(1).replace('_', ' '), m.group(2)) if m else None


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
    return f'Usar {nome}'


def _ferramentas_solis():
    """As ferramentas do próprio Solis pro Claude, num servidor MCP no processo."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    def texto(t: str) -> dict:
        return {'content': [{'type': 'text', 'text': t}]}

    @tool('hora', 'A data e a hora de agora no computador do Matheus.', {})
    async def hora(args):
        return texto(datetime.now().strftime('%A, %d/%m/%Y, %H:%M'))

    @tool('criar_lembrete', 'Anota uma tarefa (com dia e hora opcionais) na tela Tarefas; com hora, o '
          'Solis avisa no Windows na hora. Use quando o Matheus pedir pra lembrar, anotar ou avisar.',
          {'texto': str, 'dia': str, 'hora': str})
    async def criar_lembrete(args):
        dia = (args.get('dia') or '').strip() or None
        h = (args.get('hora') or '').strip() or None
        banco.adicionar_tarefa(args['texto'].strip(), dia, h)
        return texto(f'Anotado: {args["texto"]}' + (f', {dia}' if dia else '') + (f' às {h}' if h else '') + '.')

    @tool('marcar_compromisso', 'Põe um compromisso na Agenda do Matheus. dia em AAAA-MM-DD, hora em HH:MM.',
          {'titulo': str, 'dia': str, 'hora': str, 'onde': str})
    async def marcar_compromisso(args):
        banco.adicionar_compromisso(args['titulo'].strip(), args['dia'], (args.get('hora') or None),
                                    None, (args.get('onde') or None))
        return texto(f'Na agenda: {args["titulo"]}, {args["dia"]}' + (f' às {args["hora"]}' if args.get('hora') else '') + '.')

    @tool('ver_agenda', 'Os compromissos do Matheus entre duas datas (AAAA-MM-DD, as duas inclusas).',
          {'de': str, 'ate': str})
    async def ver_agenda(args):
        itens = banco.compromissos(args['de'], args['ate'], 100)
        linhas = [f'{c["dia"]} {c.get("hora") or ""} {c["titulo"]}' + (f' ({c["onde"]})' if c.get('onde') else '')
                  for c in itens if not c.get('privado')]
        return texto('\n'.join(linhas) or 'Nada na agenda nesse período.')

    @tool('ver_tarefas', 'As tarefas abertas do Matheus, com prazo e hora.', {})
    async def ver_tarefas(args):
        linhas = [f'{t.get("prazo") or "sem prazo"} {t.get("hora") or ""} {t["texto"]}'
                  for t in banco.tarefas_abertas(50) if not t.get('privada')]
        return texto('\n'.join(linhas) or 'Nenhuma tarefa aberta.')

    @tool('buscar_memoria', 'Procura nas memórias que o Solis guarda sobre o Matheus.', {'busca': str})
    async def buscar_memoria(args):
        achadas = [m for m in banco.buscar_memorias(args['busca'], 20) if not m.get('privada')]
        return texto('\n'.join(f'- {m["texto"]}' for m in achadas) or 'Nada guardado sobre isso.')

    return create_sdk_mcp_server(
        name='solis', tools=[hora, criar_lembrete, marcar_compromisso, ver_agenda, ver_tarefas, buscar_memoria],
    )


async def _decidir(nome: str, entrada: dict, por, ids: set | None = None, projeto: str | None = None,
                   modo: str = 'pedir', conversa: int | None = None, ajudante: str | None = None,
                   so_le: bool = False):
    """O can_use_tool do SDK: livre, ou um cartão na conversa esperando o Matheus.
    `modo` aceitar: editar arquivo dentro do projeto não pede (fica no registro)."""
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny, PermissionUpdate

    if nome in LIVRES or nome.startswith('mcp__solis__'):
        return PermissionResultAllow()
    # Um conector que só lê (o próprio conector marca: readOnly) é livre, como
    # ler arquivo na pasta autorizada; criar, mudar, apagar ou compartilhar pede.
    if so_le and conector_de(nome):
        return PermissionResultAllow()
    caminho = entrada.get('file_path') or entrada.get('notebook_path') or entrada.get('path')
    if nome in LEITURA and _dentro(caminho, projeto):
        return PermissionResultAllow()
    if _regra(nome, entrada) in _sempre.get(conversa, set()):
        banco.registrar_acao(conversa, nome, entrada, 'aprovado sempre: ' + resumo(nome, entrada), True)
        return PermissionResultAllow()
    if modo == 'aceitar' and nome in EDICAO and _no_projeto(caminho, projeto):
        banco.registrar_acao(None, nome, entrada, 'aceito pelo modo: ' + resumo(nome, entrada), True)
        return PermissionResultAllow()
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
    if ok == 'sempre':
        _sempre.setdefault(conversa, set()).add(_regra(nome, entrada))
    ok = bool(ok)
    por('etapa', ('aprovacao_resposta', {'id': id_, 'aprovado': ok}))
    banco.registrar_acao(conversa, nome, entrada, ('aprovado' if ok else 'recusado') + ': ' + resumo(nome, entrada), ok)
    if ok and nome == 'ExitPlanMode':
        # Plano aprovado: sai do modo de planejar e executa — pedindo
        # aprovação pro que escreve, como no modo de sempre. A conversa
        # também volta pro modo de pedir (como o Claude Code faz).
        if conversa is not None:
            banco.guardar_projeto(conversa, banco.projeto_da_conversa(conversa)['pasta'], 'pedir')
            por('etapa', ('modo', {'modo': 'pedir'}))
        return PermissionResultAllow(updated_permissions=[
            PermissionUpdate(type='setMode', mode='default', destination='session')])
    return PermissionResultAllow() if ok else PermissionResultDeny(message='O Matheus recusou.')


class _Resposta:
    """Uma resposta do Claude dentro da sessão: o que chega do CLI vira texto,
    etapa, ponto de volta e saída ao vivo de comando. `por(tipo, valor)` manda
    pra quem espera (a conversa, ou o coletor de uma resposta que o Claude
    começou sozinho). Termina no ResultMessage: `feito` resolve."""

    def __init__(self, viva: '_Viva', por, estado: dict, modo: str, sozinha: bool = False):
        self.viva, self.por, self.estado, self.modo, self.sozinha = viva, por, estado, modo, sozinha
        estado.setdefault('aprovacoes', set())
        self.usadas: dict[str, tuple[str, dict]] = {}
        self.seguindo: dict[str, tuple[str, asyncio.Task]] = {}  # tarefa do CLI → (tool_use_id, leitura)
        self.pensou = False
        self.feito: asyncio.Future = asyncio.get_running_loop().create_future()

    def _parar_de_seguir(self, tool_use_id: str | None = None) -> None:
        for tarefa, (id_, leitura) in list(self.seguindo.items()):
            if tool_use_id is None or id_ == tool_use_id:
                leitura.cancel()
                del self.seguindo[tarefa]

    def acabar(self, erro: Exception | None = None) -> None:
        self._parar_de_seguir()
        if not self.feito.done():
            if erro is None:
                self.feito.set_result(None)
            else:
                self.feito.set_exception(erro)

    def receber(self, m) -> None:
        from claude_agent_sdk import (
            AssistantMessage, RateLimitEvent, ResultMessage, StreamEvent, SystemMessage, ToolResultBlock,
            ToolUseBlock, UserMessage,
        )
        viva, por, conversa = self.viva, self.por, self.viva.conversa
        if isinstance(m, StreamEvent):
            delta = m.event.get('delta') or {}
            if m.event.get('type') == 'content_block_delta' and m.parent_tool_use_id is None:
                if delta.get('type') == 'text_delta' and delta.get('text'):
                    por('texto', delta['text'])
                elif delta.get('type') == 'thinking_delta' and not self.pensou:
                    por('etapa', ('pensando', {'cerebro': 'claude'}))
                    self.pensou = True
        elif isinstance(m, SystemMessage):
            dados = m.data or {}
            if (m.subtype == 'task_started' and dados.get('task_type') == 'local_bash'
                    and not dados.get('is_backgrounded') and viva.sessao_id and dados.get('task_id')):
                # Um comando passou de ~2 s: a saída dele, ao vivo.
                id_ = dados.get('tool_use_id') or ''
                comando = str((self.usadas.get(id_) or ('', {}))[1].get('command', ''))
                self.seguindo[dados['task_id']] = (id_, asyncio.ensure_future(
                    _seguir_saida(viva.sessao_id, dados['task_id'], id_, comando, por)))
            elif m.subtype == 'task_notification' and dados.get('task_id') in self.seguindo:
                self.seguindo.pop(dados['task_id'])[1].cancel()
        elif isinstance(m, UserMessage) and isinstance(m.content, str):
            # A nossa mensagem, devolvida com o uuid (replay-user-messages): o
            # ponto de volta desta resposta. Só a primeira, e só numa resposta
            # pedida pelo Matheus (a que o Claude começa sozinho vem do aviso do
            # CLI, não de uma fala). Direto no banco, desta thread: pela fila,
            # parar a resposta no meio perderia o que ainda não foi lido.
            if (m.uuid and m.parent_tool_use_id is None and viva.sessao_id and not self.sozinha
                    and not self.estado.get('ponto')):
                self.estado['ponto'] = m.uuid
                if conversa is not None:
                    banco.guardar_ponto(conversa, viva.sessao_id, m.uuid, str(_base(viva.projeto)))
        elif isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, ToolUseBlock):
                    self.usadas[b.id] = (b.name, b.input)
        elif isinstance(m, UserMessage) and isinstance(m.content, list):
            for b in m.content:
                if isinstance(b, ToolResultBlock) and b.tool_use_id in self.usadas:
                    self._parar_de_seguir(b.tool_use_id)
                    nome, entrada = self.usadas.pop(b.tool_use_id)
                    if nome in ('ToolSearch', 'TodoWrite'):
                        continue
                    if nome in EDICAO and not b.is_error and viva.sessao_id and conversa is not None:
                        banco.ponto_mudou(conversa, viva.sessao_id)
                    extra = {}
                    if nome in TERMINAL:
                        # A saída fica no passo, pra abrir depois. Um comando em
                        # segundo plano só devolve o aviso de que começou.
                        extra['saida'] = _limpar_saida(_texto_do_resultado(b.content))
                        if entrada.get('run_in_background'):
                            extra['fundo'] = True
                    por('etapa', ('ferramenta', {'ferramenta': nome, 'alvo': _alvo(nome, entrada),
                                                 'ok': not b.is_error, 'id': b.tool_use_id, **extra}))
        elif isinstance(m, RateLimitEvent):
            # "rejected" é a cota acabada; o resets_at diz quando volta. O
            # aviso de cota perto do fim ("allowed_warning") não para nada.
            if m.rate_limit_info.status == 'rejected':
                por('cota', m.rate_limit_info.resets_at)
        elif isinstance(m, ResultMessage):
            if m.is_error:
                self.acabar(AgenteFalhou(str(m.result or m.subtype)[:300]))
            else:
                por('custo', {'usd': m.total_cost_usd, 'turnos': m.num_turns, 'sessao': m.session_id})
                self.acabar()


class _Coletor:
    """A resposta que o Claude começa sozinho — quando um comando em segundo
    plano termina, o CLI avisa e ele conta o que saiu, como no Claude Code. Não
    há stream aberto pra ela: fica aqui (a tela lê por GET /conversas/{id}/fundo)
    e vai pro banco no fim."""

    def __init__(self, conversa: int | None):
        self.conversa = conversa
        self.inicio = time.monotonic()
        self.pedacos: list[str] = []
        self.etapas: list[dict] = []
        self.marcar('sozinha')
        self.marcar('cerebro', cerebro='claude')

    def _t(self) -> float:
        return round(time.monotonic() - self.inicio, 2)

    def marcar(self, etapa: str, **dados) -> None:
        self.etapas.append({'etapa': etapa, 't': self._t(), **dados})

    def por(self, tipo, valor=None) -> None:
        if tipo == 'texto':
            if not self.pedacos:
                self.marcar('primeira_palavra', cerebro='claude')
            self.pedacos.append(valor)
        elif tipo == 'etapa':
            etapa, dados = valor
            self.marcar(etapa, **dados)
        elif tipo == 'aovivo':
            etapa, dados = valor
            # Só a mais nova de cada comando: são o fim da saída até agora.
            self.etapas = [e for e in self.etapas if not (e['etapa'] == etapa and e.get('id') == dados.get('id'))]
            self.etapas.append({'etapa': etapa, 't': self._t(), **dados})
        elif tipo == 'custo' and self.conversa is not None and valor.get('sessao'):
            banco.guardar_sessao_claude(self.conversa, valor['sessao'])

    def agora(self) -> dict:
        return {'texto': ''.join(self.pedacos), 'etapas': list(self.etapas)}

    def guardar(self, cortada: bool = False) -> int | None:
        """No banco, como uma resposta do Claude: só o que fica (sem a saída ao vivo)."""
        texto = ''.join(self.pedacos).strip()
        if self.conversa is None or not texto:
            return None
        self.marcar('fim', cerebro='claude', **({'cortada': True} if cortada else {}))
        id_ = banco.adicionar(self.conversa, 'solis', texto, cerebro='claude')
        banco.guardar_etapas(id_, [e for e in self.etapas if e['etapa'] != 'saida'])
        return id_


# As últimas ações de um ajudante (subagente) que a tela mostra.
AJUDANTE_PASSOS = 6

# A sessão de cada conversa que ficou aberta por ter comando em segundo plano.
_vivas: dict[int, '_Viva'] = {}
# Fechada a última resposta e sem comando rodando, quanto a sessão espera
# (o aviso de fim de um comando chega logo antes da resposta que ele provoca).
OCIOSA_S = 8.0


class _Viva:
    """A sessão do Claude (um CLI) de uma conversa. Abre pra cada resposta e
    fecha no fim dela — a não ser que o Claude tenha deixado um comando em
    segundo plano (um servidor, um teste longo): aí fica aberta até ele
    acabar, como no Claude Code. Nesse meio tempo a próxima mensagem vai pra
    ela (e não pra uma sessão nova, que não saberia do comando), o Matheus vê
    a saída e pode parar, e quando o comando termina o Claude conta o que saiu.

    Tudo aqui roda no laço da thread dela; de fora, só por run_coroutine_threadsafe."""

    def __init__(self, conversa: int | None, projeto: str | None, modelo: str | None, modo: str):
        self.conversa, self.projeto, self.modelo, self.modo = conversa, projeto, modelo, modo
        self.cliente = None
        self.laco: asyncio.AbstractEventLoop | None = None
        self.sessao_id: str | None = None
        self.resposta: _Resposta | None = None
        self.sozinha: _Coletor | None = None
        # task_id → {'id', 'tipo' (comando | ajudante), 'comando', 'descricao',
        # 'inicio', 'tool_use_id', e num ajudante: 'agora' e os 'passos'}
        self.fundo: dict[str, dict] = {}
        # Pedidos de aprovação que chegam sem resposta em andamento (um ajudante
        # trabalhando depois que a resposta acabou): a tela lê pelo /fundo.
        self.pedidos: list[dict] = []
        self.ultima = time.monotonic()
        self.aberta = True
        self.fechar_ja = False
        # nome da ferramenta de conector → anotações dela (readOnly, destructive...)
        self.anotacoes: dict[str, dict] | None = None

    async def so_le(self, nome: str) -> bool:
        """A ferramenta de conector só lê? Pergunta ao CLI uma vez por sessão."""
        if not conector_de(nome):
            return False
        if self.anotacoes is None or nome not in self.anotacoes:
            try:
                st = await self.cliente.get_mcp_status()
            except Exception:  # noqa: BLE001 — sem saber, pede (o seguro)
                return False
            self.anotacoes = {
                f'mcp__{_normalizar_servidor(s.get("name", ""))}__{t.get("name")}': t.get('annotations') or {}
                for s in (st or {}).get('mcpServers', []) for t in (s.get('tools') or [])
            }
        a = self.anotacoes.get(nome) or {}
        return bool(a.get('readOnly')) and not a.get('destructive')

    # — o que chega do CLI ——————————————————————————————————————————————————————
    async def ler(self) -> None:
        """Lê tudo que o CLI manda, o tempo todo, e entrega à resposta da vez."""
        from claude_agent_sdk import SystemMessage
        try:
            async for m in self.cliente.receive_messages():
                self.ultima = time.monotonic()
                if getattr(m, 'parent_tool_use_id', None):
                    # De um ajudante (subagente): vai pro quadro dele, não pras
                    # etapas da resposta principal.
                    self._do_ajudante(m)
                    continue
                if isinstance(m, SystemMessage):
                    if m.subtype == 'init':
                        self.sessao_id = (m.data or {}).get('session_id') or self.sessao_id
                        if self.resposta is None:
                            self._comecar_sozinha()
                    self._ver_fundo(m)
                if self.resposta is not None:
                    self.resposta.receber(m)
                    if self.resposta.feito.done():
                        self._acabou_resposta()
        except Exception as e:  # noqa: BLE001 — o CLI caiu: a resposta da vez falha
            log.warning('a sessão do Claude caiu: %s', e)
        finally:
            self.aberta = False
            if self.resposta is not None:
                self.resposta.acabar(AgenteFalhou('a sessão do Claude fechou no meio'))
                self._acabou_resposta(cortada=True)

    def _comecar_sozinha(self) -> None:
        self.sozinha = _Coletor(self.conversa)
        modo = banco.projeto_da_conversa(self.conversa)['modo'] if self.conversa is not None else 'pedir'
        self.resposta = _Resposta(self, self.sozinha.por, {}, modo, sozinha=True)
        log.info('claude (agente): resposta começada sozinho, conversa %s', self.conversa)

    def _acabou_resposta(self, cortada: bool = False) -> None:
        if self.resposta is not None and self.resposta.sozinha and self.sozinha is not None:
            try:
                self.sozinha.guardar(cortada)
            except Exception:  # noqa: BLE001
                log.exception('não consegui guardar a resposta que o Claude começou sozinho')
            self.sozinha = None
        self.resposta = None

    def por_fundo(self, tipo, valor=None) -> None:
        """O `por` de quando não há resposta em andamento: só os cartões de
        aprovação interessam (os outros acontecimentos não têm onde aparecer)."""
        if tipo != 'etapa':
            return
        etapa, dados = valor
        if etapa == 'aprovacao':
            self.pedidos.append({'etapa': 'aprovacao', 't': 0, **dados})
        elif etapa == 'aprovacao_resposta':
            self.pedidos = [p for p in self.pedidos if p.get('id') != dados.get('id')]

    def _do_ajudante(self, m) -> None:
        from claude_agent_sdk import AssistantMessage, ToolResultBlock, ToolUseBlock, UserMessage
        t = next((t for t in self.fundo.values() if t.get('tool_use_id') == m.parent_tool_use_id), None)
        if t is None:
            return
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, ToolUseBlock):
                    t.setdefault('usadas', {})[b.id] = (b.name, b.input)
                    # O que ele está fazendo agora: a ação em andamento (a tela
                    # diz em português; o "progresso" do CLI vem em inglês).
                    t['agora'] = {'ferramenta': b.name, 'alvo': _alvo(b.name, b.input), 'id': b.id}
        elif isinstance(m, UserMessage) and isinstance(m.content, list):
            for b in m.content:
                if isinstance(b, ToolResultBlock) and b.tool_use_id in t.get('usadas', {}):
                    nome, entrada = t['usadas'].pop(b.tool_use_id)
                    if (t.get('agora') or {}).get('id') == b.tool_use_id:
                        t['agora'] = None
                    if nome in ('ToolSearch', 'TodoWrite'):
                        continue
                    if nome in EDICAO and not b.is_error and self.sessao_id and self.conversa is not None:
                        banco.ponto_mudou(self.conversa, self.sessao_id)
                    t['passos'] = (t.get('passos', []) + [
                        {'ferramenta': nome, 'alvo': _alvo(nome, entrada), 'ok': not b.is_error}])[-AJUDANTE_PASSOS:]

    def _ver_fundo(self, m) -> None:
        dados, sub = m.data or {}, m.subtype
        ajudante = dados.get('task_type') == 'local_agent'
        if sub == 'task_started' and (dados.get('is_backgrounded') or ajudante) and dados.get('task_id'):
            usada = (self.resposta.usadas.get(dados.get('tool_use_id') or '') if self.resposta else None) or ('', {})
            self.fundo[dados['task_id']] = {
                'id': dados['task_id'], 'tipo': 'ajudante' if ajudante else 'comando',
                'comando': '' if ajudante else str(usada[1].get('command', '')),
                'descricao': dados.get('description') or '', 'inicio': time.time(),
                'tool_use_id': dados.get('tool_use_id'), 'agora': None, 'passos': [],
            }
        elif sub == 'background_tasks_changed':
            # A lista inteira do que roda: o que saiu dela acabou.
            agora = {t.get('task_id') for t in dados.get('tasks') or []}
            for id_ in list(self.fundo):
                if id_ not in agora:
                    del self.fundo[id_]
        elif sub in ('task_notification', 'task_updated'):
            status = dados.get('status') or (dados.get('patch') or {}).get('status')
            if status in ('completed', 'failed', 'killed', 'stopped'):
                self.fundo.pop(dados.get('task_id'), None)

    # — uma resposta pedida ————————————————————————————————————————————————————————
    async def turno(self, prompt: str, por, estado: dict, modo: str, modelo: str | None) -> None:
        """Uma mensagem do Matheus. Manda `fim` (e `erro`, se for o caso) no fim
        dela — a sessão pode seguir aberta depois."""
        try:
            # Uma resposta que o Claude começou sozinho termina antes.
            while self.resposta is not None and self.aberta:
                await asyncio.sleep(0.2)
            if not self.aberta:
                raise AgenteFalhou('a sessão do Claude fechou')
            if modelo != self.modelo:
                await self.cliente.set_model(modelo)
                self.modelo = modelo
            if modo != self.modo:
                await self.cliente.set_permission_mode('plan' if modo == 'planejar' else 'default')
                self.modo = modo
            estado['cliente'] = self.cliente
            estado['laco'] = asyncio.get_running_loop()
            self.resposta = _Resposta(self, por, estado, modo)
            resposta = self.resposta
            await self.cliente.query(prompt)
            await resposta.feito
        except Exception as e:  # noqa: BLE001 — vira erro do cérebro, do outro lado
            if not estado.get('parado') and not isinstance(e, AgenteFalhou):
                log.exception('o agente do Claude falhou')
            por('erro', e)
        finally:
            estado['_fim'] = True
            por('fim')

    # — ficar aberta ————————————————————————————————————————————————————————————————
    async def viver(self) -> None:
        """Enquanto houver comando em segundo plano (ou resposta em andamento,
        ou aviso a caminho), a sessão fica; depois fecha."""
        while self.aberta and not self.fechar_ja:
            if not self.fundo and self.resposta is None and time.monotonic() - self.ultima > OCIOSA_S:
                break
            await asyncio.sleep(0.5)

    async def parar_fundo(self, tarefa: str) -> None:
        await self.cliente.stop_task(tarefa)

    async def fechar(self) -> None:
        """Fechar de propósito (outra pasta, conversa voltou): os comandos param
        antes — sem o CLI, ninguém mais acompanharia."""
        for tarefa in list(self.fundo):
            with contextlib.suppress(Exception):
                await self.cliente.stop_task(tarefa)
        self.fechar_ja = True

    def serve(self, retomar: str | None, projeto: str | None) -> bool:
        return self.aberta and not self.fechar_ja and retomar is not None and retomar == self.sessao_id \
            and projeto == self.projeto

    def estado_fundo(self) -> dict:
        """Pra tela (GET /conversas/{id}/fundo): os comandos com o fim da saída,
        e a resposta que o Claude começou sozinho, se houver."""
        comandos = []
        for t in list(self.fundo.values()):
            arquivo = (_arquivo_da_saida(self.sessao_id or '', t['id'])
                       if self.sessao_id and t.get('tipo') != 'ajudante' else None)
            saida = ''
            if arquivo:
                with contextlib.suppress(OSError):
                    with open(arquivo, 'rb') as f:
                        f.seek(0, os.SEEK_END)
                        f.seek(max(0, f.tell() - 4 * SAIDA_MAX))
                        saida = _limpar_saida(f.read().decode('utf-8', 'replace'))
            publico = {k: v for k, v in t.items() if k != 'usadas'}
            comandos.append({**publico, 'segundos': int(time.time() - t['inicio']), 'saida': saida})
        return {'comandos': comandos, 'resposta': self.sozinha.agora() if self.sozinha else None,
                'aprovacoes': list(self.pedidos)}


async def _sessao(sistema: str, prompt: str, por, retomar: str | None = None, estado: dict | None = None,
                  modelo: str | None = None, esforco: str | None = None, projeto: str | None = None,
                  modo: str = 'pedir', conversa: int | None = None) -> None:
    """Roda no laço da thread do SDK: abre a sessão, faz a resposta e, se ficou
    comando em segundo plano, segue aberta (_Viva). `por(tipo, valor)` manda
    pro laço do servidor. `retomar`: a sessão anterior da conversa."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

    estado = estado if estado is not None else {}
    viva = _Viva(conversa, projeto, modelo, modo)

    async def decidir(nome, entrada, contexto):
        # Quem pede: um ajudante (subagente) diz o id dele; o cartão diz que é
        # ele, com a tarefa dele.
        id_ajudante = getattr(contexto, 'agent_id', None)
        ajudante = None
        if id_ajudante:
            ajudante = (viva.fundo.get(id_ajudante) or {}).get('descricao') or ''
        so_le = await viva.so_le(nome)
        # Da resposta da vez: pode ser uma que o Claude começou sozinho.
        r = viva.resposta
        if r is None:
            # Ninguém respondendo (um ajudante trabalhando depois da resposta):
            # o cartão vai pro /fundo, que a tela lê.
            return await _decidir(nome, entrada, viva.por_fundo, None, projeto, viva.modo, conversa, ajudante, so_le)
        return await _decidir(nome, entrada, r.por, r.estado['aprovacoes'], projeto, r.modo, conversa, ajudante,
                              so_le)

    async def leitura_fora(dados, tool_use_id, contexto):
        """Ler é livre pro Claude Code; aqui, fora das pastas autorizadas, vira pedido."""
        entrada = dados.get('tool_input') or {}
        if _dentro(entrada.get('file_path') or entrada.get('path'), projeto):
            return {}
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask',
                                       'permissionDecisionReason': 'fora das pastas autorizadas'}}

    if projeto:
        sistema += (f'\n\nVocê está trabalhando no projeto em {projeto} (a pasta atual). Siga o CLAUDE.md dele, '
                    'se houver. Ler ali dentro é livre; escrever, editar e rodar comandos seguem o modo da conversa.')
    opcoes = ClaudeAgentOptions(
        system_prompt=sistema,
        cwd=str(_base(projeto)),
        add_dirs=[str(r) for r in _raizes(projeto)[1:]],
        mcp_servers={'solis': _ferramentas_solis()},
        allowed_tools=['WebSearch', 'WebFetch', 'mcp__solis__*'],
        can_use_tool=decidir,
        hooks={'PreToolUse': [HookMatcher(matcher='Read|Glob|Grep|LS', hooks=[leitura_fora])]},
        include_partial_messages=True,
        resume=retomar,
        model=modelo,
        effort=esforco,
        # Num projeto, o Claude lê o CLAUDE.md e a configuração dele, como o
        # Claude Code; fora de um, nada do disco entra.
        setting_sources=['project', 'local'] if projeto else [],
        permission_mode='plan' if modo == 'planejar' else 'default',
        max_turns=RODADAS_MAX,
        # Voltar atrás: o CLI guarda cada arquivo antes de editar, e devolve a
        # nossa mensagem com o uuid dela — o ponto pra onde se volta (voltar()).
        enable_file_checkpointing=True,
        extra_args={'replay-user-messages': None},
    )
    try:
        async with ClaudeSDKClient(options=opcoes) as cliente:
            viva.cliente = cliente
            viva.laco = asyncio.get_running_loop()
            leitor = asyncio.ensure_future(viva.ler())
            # Registrada desde já: um ajudante trabalha durante a resposta, e
            # a tela vê ele pelo /fundo (fundo()).
            if conversa is not None:
                _vivas[conversa] = viva
            try:
                await viva.turno(prompt, por, estado, modo, modelo)
                # Parada no meio também: o comando segue rodando e precisa de dono.
                if viva.fundo and conversa is not None:
                    log.info('claude (agente): %d comando(s) em segundo plano; a sessão fica aberta', len(viva.fundo))
                    await viva.viver()
            finally:
                if _vivas.get(conversa) is viva:
                    del _vivas[conversa]
                viva.aberta = False
                leitor.cancel()
    except Exception as e:  # noqa: BLE001 — o CLI nem abriu (ou caiu ao fechar)
        if not estado.get('_fim'):
            if not estado.get('parado'):
                log.exception('o agente do Claude falhou')
            por('erro', e)
            por('fim')
        else:
            log.warning('a sessão do Claude fechou com erro: %s', e)


def _limpar_saida(texto: str) -> str:
    """Pra tela: sem as cores do terminal; a linha que se reescreve (barra de
    progresso, com \\r) fica só com o que sobrou nela; e só o fim."""
    linhas = [l.rsplit('\r', 1)[-1] for l in _ANSI.sub('', texto).replace('\r\n', '\n').split('\n')]
    return '\n'.join(linhas[-SAIDA_LINHAS:])[-SAIDA_MAX:]


def _texto_do_resultado(conteudo) -> str:
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return '\n'.join(b.get('text', '') for b in conteudo if isinstance(b, dict))
    return ''


def _arquivo_da_saida(sessao: str, tarefa: str) -> str | None:
    """O CLI escreve a saída de um comando que passa de ~2 s em
    <temp>/claude/<pasta>/<sessão>/tasks/<tarefa>.output enquanto ele roda, e
    apaga no fim (visto em 12/11/2026, SDK 0.2.180). Não é API pública: se
    mudar, a tela só deixa de ver ao vivo — a saída do fim continua no passo."""
    achados = glob.glob(os.path.join(glob.escape(tempfile.gettempdir()), 'claude', '*', glob.escape(sessao),
                                     'tasks', glob.escape(tarefa) + '.output'))
    return achados[0] if achados else None


async def _seguir_saida(sessao: str, tarefa: str, id_: str, comando: str, por, passo: float = 0.3) -> None:
    """Lê o arquivo da saída enquanto o comando roda e manda o fim dele pra
    tela (a etapa `saida`, ao vivo). Acaba cancelada, quando o resultado chega."""
    arquivo, lido, fim, ultimo = None, 0, b'', None
    while True:
        arquivo = arquivo or _arquivo_da_saida(sessao, tarefa)
        if arquivo:
            try:
                with open(arquivo, 'rb') as f:
                    f.seek(lido)
                    novo = f.read()
            except OSError:  # o CLI apagou: o comando acabou
                novo = b''
            if novo:
                # Só o fim fica: a saída inteira de um build longo não cabe aqui.
                lido += len(novo)
                fim = (fim + novo)[-4 * SAIDA_MAX:]
                texto = _limpar_saida(fim.decode('utf-8', 'replace'))
                if texto != ultimo:
                    ultimo = texto
                    por('aovivo', ('saida', {'id': id_, 'comando': comando, 'saida': texto}))
        await asyncio.sleep(passo)


def _alvo(nome: str, entrada: dict, limite: int = 160) -> str:
    for chave in ('file_path', 'notebook_path', 'path', 'pattern', 'query', 'url', 'command', 'description',
                  'texto', 'titulo', 'busca', 'plan'):
        if entrada.get(chave):
            valor = str(entrada[chave])
            if len(valor) > limite and chave in ('file_path', 'notebook_path', 'path'):
                # Num caminho, o que importa é o fim (o nome do arquivo).
                return '…' + valor[-(limite - 1):]
            return valor[:limite]
    return ''


async def claude(sistema: str, prompt: str, etapas=MUDA, retomar: str | None = None,
                 ao_sessao=None, projeto: str | None = None, modo: str = 'pedir',
                 conversa: int | None = None) -> AsyncIterator[str]:
    """O texto da resposta em pedaços; as ferramentas e os pedidos de
    aprovação viram etapas. Erro: AgenteFalhou. `retomar` continua uma sessão;
    `ao_sessao(id)` recebe a sessão desta resposta, pra a próxima continuar."""
    laco = asyncio.get_running_loop()
    fila: asyncio.Queue = asyncio.Queue()

    def por(tipo, valor=None):
        laco.call_soon_threadsafe(fila.put_nowait, (tipo, valor))

    estado: dict = {}
    escolha = ajustes()
    if escolha['modelo'] or escolha['esforco']:
        log.info('claude (agente): modelo %s, esforço %s', escolha['modelo'] or 'padrão', escolha['esforco'] or 'padrão')

    def na_thread():
        proprio = asyncio.ProactorEventLoop() if os.name == 'nt' else asyncio.new_event_loop()
        try:
            # _sessao manda o `fim` da resposta; a thread pode seguir depois
            # dele, com a sessão aberta por um comando em segundo plano.
            proprio.run_until_complete(_sessao(sistema, prompt, por, retomar, estado=estado,
                                               modelo=escolha['modelo'], esforco=escolha['esforco'],
                                               projeto=projeto, modo=modo, conversa=conversa))
        except Exception as e:  # noqa: BLE001 — vira erro do cérebro, do outro lado
            if not estado.get('parado'):
                log.exception('o agente do Claude falhou')
            por('erro', e)
        finally:
            # Quem espera do outro lado não pode ficar preso: se a sessão não
            # mandou o fim da resposta (caiu antes), vai aqui.
            if not estado.get('_fim'):
                estado['_fim'] = True
                por('fim')
            proprio.close()

    viva = _vivas.get(conversa) if conversa is not None else None
    if viva is not None and viva.serve(retomar, projeto):
        # A sessão ainda aberta (comando em segundo plano): a mensagem vai pra
        # ela, que sabe do comando. O pedido curto é o mesmo de retomar.
        log.info('claude (agente): continuando a sessão aberta da conversa %s', conversa)
        asyncio.run_coroutine_threadsafe(viva.turno(prompt, por, estado, modo, escolha['modelo']), viva.laco)
    else:
        if viva is not None:
            # Outra sessão vai começar (a conversa voltou, outra pasta): a
            # aberta para os comandos dela e fecha.
            asyncio.run_coroutine_threadsafe(viva.fechar(), viva.laco)
        threading.Thread(target=na_thread, name='solis-agente', daemon=True).start()
    terminou = False
    try:
        async for item in _ler(fila, etapas, ao_sessao):
            yield item
        terminou = True
    except AgenteFalhou:
        terminou = True  # a sessão já acabou sozinha: não há o que interromper
        raise
    finally:
        if not terminou:
            _interromper(estado)


_conectores: dict = {'quando': 0.0, 'lista': None}
CONECTORES_CACHE_S = 300


async def _ler_conectores() -> list[dict]:
    """Sobe um CLI sem perguntar nada (não gasta cota), espera os conectores
    conectarem e lê o estado de cada um."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    opcoes = ClaudeAgentOptions(cwd=str(_pasta_trabalho()), setting_sources=[])
    async with ClaudeSDKClient(options=opcoes) as cliente:
        servidores: list = []
        # Logo ao abrir, a lista ainda vem vazia (os conectores chegam do
        # claude.ai um instante depois) e depois "pending" enquanto conectam.
        for _ in range(40):
            servidores = (await cliente.get_mcp_status() or {}).get('mcpServers', [])
            proxy = [s for s in servidores if (s.get('config') or {}).get('type') == 'claudeai-proxy']
            if proxy and not any(s.get('status') == 'pending' for s in proxy):
                break
            await asyncio.sleep(0.5)
    lista = []
    for s in servidores:
        if (s.get('config') or {}).get('type') != 'claudeai-proxy':
            continue  # só os da conta do claude.ai
        ferramentas = s.get('tools') or []
        lista.append({
            'nome': s.get('name', '').removeprefix('claude.ai ').strip(),
            'estado': {'connected': 'conectado', 'needs-auth': 'precisa_entrar', 'pending': 'conectando'}.get(
                s.get('status'), 'falhou'),
            'ferramentas': len(ferramentas),
            'so_leem': sum(1 for t in ferramentas if (t.get('annotations') or {}).get('readOnly')),
        })
    return sorted(lista, key=lambda c: (c['estado'] != 'conectado', c['nome'].lower()))


async def conectores(atualizar: bool = False) -> list[dict]:
    """Os conectores da conta do claude.ai que o Claude do Solis usa (GET
    /conectores). Guardados 5 minutos: ler sobe um CLI (alguns segundos)."""
    if not atualizar and _conectores['lista'] is not None and time.time() - _conectores['quando'] < CONECTORES_CACHE_S:
        return _conectores['lista']
    laco = asyncio.get_running_loop()
    pronto: asyncio.Future = laco.create_future()

    def na_thread():
        proprio = asyncio.ProactorEventLoop() if os.name == 'nt' else asyncio.new_event_loop()
        try:
            r = proprio.run_until_complete(_ler_conectores())
            laco.call_soon_threadsafe(pronto.set_result, r)
        except Exception as e:  # noqa: BLE001
            log.exception('não consegui ler os conectores')
            laco.call_soon_threadsafe(pronto.set_exception, AgenteFalhou(str(e)[:300]))
        finally:
            proprio.close()

    threading.Thread(target=na_thread, name='solis-conectores', daemon=True).start()
    lista = await pronto
    _conectores.update(quando=time.time(), lista=lista)
    return lista


def fundo(conversa: int) -> dict:
    """O que roda em segundo plano na conversa, e a resposta que o Claude
    começou sozinho (GET /conversas/{id}/fundo). Lido de outra thread: cópias."""
    viva = _vivas.get(conversa)
    if viva is None or viva.laco is None:
        return {'comandos': [], 'resposta': None, 'aprovacoes': []}
    try:
        return asyncio.run_coroutine_threadsafe(_no_laco(viva.estado_fundo), viva.laco).result(5)
    except Exception:  # noqa: BLE001 — a sessão acabou de fechar
        return {'comandos': [], 'resposta': None, 'aprovacoes': []}


async def _no_laco(funcao):
    return funcao()


async def parar_fundo(conversa: int, tarefa: str) -> bool:
    """Para um comando em segundo plano (o CLI mata o processo)."""
    viva = _vivas.get(conversa)
    if viva is None or tarefa not in viva.fundo:
        return False
    await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(viva.parar_fundo(tarefa), viva.laco))
    banco.registrar_acao(conversa, 'parar_segundo_plano', {'tarefa': tarefa}, 'parado', True)
    return True


def _interromper(estado: dict) -> None:
    """O Matheus parou a resposta (ou ela caiu do lado de cá): a sessão do
    Claude é interrompida no laço dela, e os cartões que ainda esperavam
    viram recusa — senão a thread ficaria presa 10 minutos esperando."""
    estado['parado'] = True
    for id_ in list(estado.get('aprovacoes', ())):
        responder_aprovacao(id_, False)
    cliente, laco = estado.get('cliente'), estado.get('laco')
    if cliente is not None and laco is not None and not laco.is_closed():
        try:
            asyncio.run_coroutine_threadsafe(cliente.interrupt(), laco)
        except RuntimeError:  # o laço acabou de fechar: nada a interromper
            pass
    log.info('claude (agente): interrompido')


async def _voltar_sessoes(pontos: list[dict], simular: bool) -> dict:
    """Roda no laço da thread. Cada sessão volta pro primeiro ponto dela, da
    mais nova pra mais antiga: um arquivo que duas sessões mudaram termina como
    estava antes da primeira."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    primeiro: dict[str, dict] = {}
    for p in sorted(pontos, key=lambda p: p['mensagem']):
        primeiro.setdefault(p['sessao'], p)
    arquivos: list[str] = []
    mais = menos = 0
    erros: list[str] = []
    for p in sorted(primeiro.values(), key=lambda p: p['mensagem'], reverse=True):
        if not Path(p['pasta']).is_dir():
            erros.append(f'a pasta {p["pasta"]} não existe mais')
            continue
        # A sessão ainda aberta (comando em segundo plano) volta pelo CLI dela:
        # dois CLIs na mesma sessão se atropelariam.
        viva = next((v for v in list(_vivas.values()) if v.aberta and v.sessao_id == p['sessao']), None)
        if viva is not None:
            def no_laco(coro, laco=viva.laco):
                return asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, laco))
            r = await _voltar_uma(viva.cliente, p['uuid'], simular, no_laco)
        else:
            # Abrir a sessão sem mandar nada: não gasta cota, só sobe o CLI.
            opcoes = ClaudeAgentOptions(cwd=p['pasta'], resume=p['sessao'], setting_sources=[],
                                        enable_file_checkpointing=True)
            async with ClaudeSDKClient(options=opcoes) as cliente:
                r = await _voltar_uma(cliente, p['uuid'], simular)
        if not r.get('canRewind'):
            erros.append(str(r.get('error') or 'não deu'))
            continue
        for a in r.get('filesChanged') or []:
            if a not in arquivos:
                arquivos.append(a)
        mais += r.get('insertions') or 0
        menos += r.get('deletions') or 0
    return {'arquivos': arquivos, 'mais': mais, 'menos': menos, 'erros': erros}


async def _voltar_uma(cliente, uuid_: str, simular: bool, no_laco=None) -> dict:
    """O que volta de uma sessão (dry_run), e volta. `no_laco` roda as chamadas
    no laço de uma sessão aberta, que é de outra thread."""
    async def pedir():
        # O SDK (0.2.180) não passa o dry_run no rewind_files(); o CLI aceita
        # e devolve os arquivos e as linhas. O pedido de controle é o mesmo.
        r = await cliente._query._send_control_request(
            {'subtype': 'rewind_files', 'user_message_id': uuid_, 'dry_run': True})
        if r.get('canRewind') and not simular and r.get('filesChanged'):
            await cliente.rewind_files(uuid_)
        return r
    return await (no_laco(pedir()) if no_laco else pedir())


async def voltar(pontos: list[dict], simular: bool = False) -> dict:
    """Voltar atrás: os arquivos que o Claude mudou voltam a como estavam antes
    do primeiro ponto (banco.pontos_desde). `simular`: só diz o que voltaria.
    Comandos que ele rodou não voltam — o CLI só guarda o que ele editou."""
    laco = asyncio.get_running_loop()
    pronto: asyncio.Future = laco.create_future()

    def na_thread():
        proprio = asyncio.ProactorEventLoop() if os.name == 'nt' else asyncio.new_event_loop()
        try:
            r = proprio.run_until_complete(_voltar_sessoes(pontos, simular))
            laco.call_soon_threadsafe(pronto.set_result, r)
        except Exception as e:  # noqa: BLE001 — vai pra rota, do outro lado
            log.exception('voltar atrás falhou')
            laco.call_soon_threadsafe(pronto.set_exception, AgenteFalhou(str(e)[:300]))
        finally:
            proprio.close()

    threading.Thread(target=na_thread, name='solis-voltar', daemon=True).start()
    return await pronto


async def _ler(fila: asyncio.Queue, etapas, ao_sessao) -> AsyncIterator[str]:
    while True:
        tipo, valor = await fila.get()
        if tipo == 'texto':
            yield valor
        elif tipo == 'etapa':
            etapa, dados = valor
            etapas.marcar(etapa, **dados)
        elif tipo == 'aovivo':
            etapa, dados = valor
            etapas.ao_vivo(etapa, **dados)
        elif tipo == 'custo':
            log.info('claude (agente): %s rodadas, US$ %.4f equivalente', valor['turnos'], valor['usd'] or 0)
            if ao_sessao and valor.get('sessao'):
                ao_sessao(valor['sessao'])
        elif tipo == 'cota':
            from . import cerebros
            cerebros.pausar('claude', valor, 'a cota acabou')
        elif tipo == 'erro':
            raise AgenteFalhou(str(valor)[:300])
        elif tipo == 'fim':
            return
