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
import logging
import os
import threading
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


def responder_aprovacao(id_: str, aprovado: bool) -> bool:
    """O Matheus respondeu o cartão. False se o pedido já não existe."""
    fut = _pendentes.get(id_)
    if fut is None or fut.done():
        return False
    fut.set_result(bool(aprovado))
    return True


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
    return any(p == r or p.is_relative_to(r) for r in _raizes(projeto))


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


def resumo(nome: str, entrada: dict) -> str:
    """O que vai aparecer no cartão de aprovação, em português."""
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
                   modo: str = 'pedir'):
    """O can_use_tool do SDK: livre, ou um cartão na conversa esperando o Matheus.
    `modo` aceitar: editar arquivo dentro do projeto não pede (fica no registro)."""
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny, PermissionUpdate

    if nome in LIVRES or nome.startswith('mcp__solis__'):
        return PermissionResultAllow()
    caminho = entrada.get('file_path') or entrada.get('notebook_path') or entrada.get('path')
    if nome in LEITURA and _dentro(caminho, projeto):
        return PermissionResultAllow()
    if modo == 'aceitar' and nome in EDICAO and _no_projeto(caminho, projeto):
        banco.registrar_acao(None, nome, entrada, 'aceito pelo modo: ' + resumo(nome, entrada), True)
        return PermissionResultAllow()
    id_ = uuid.uuid4().hex[:12]
    fut: concurrent.futures.Future = concurrent.futures.Future()
    _pendentes[id_] = fut
    if ids is not None:
        ids.add(id_)
    por('etapa', ('aprovacao', {'id': id_, 'ferramenta': nome, 'resumo': resumo(nome, entrada),
                                'alvo': _alvo(nome, entrada, 6000 if nome == 'ExitPlanMode' else 1000)}))
    try:
        ok = await asyncio.wait_for(asyncio.wrap_future(fut), APROVACAO_MAX_S)
    except asyncio.TimeoutError:
        ok = False
    finally:
        _pendentes.pop(id_, None)
    por('etapa', ('aprovacao_resposta', {'id': id_, 'aprovado': ok}))
    banco.registrar_acao(None, nome, entrada, ('aprovado' if ok else 'recusado') + ': ' + resumo(nome, entrada), ok)
    if ok and nome == 'ExitPlanMode':
        # Plano aprovado: sai do modo de planejar e executa — pedindo
        # aprovação pro que escreve, como no modo de sempre.
        return PermissionResultAllow(updated_permissions=[
            PermissionUpdate(type='setMode', mode='default', destination='session')])
    return PermissionResultAllow() if ok else PermissionResultDeny(message='O Matheus recusou.')


async def _sessao(sistema: str, prompt: str, por, retomar: str | None = None, estado: dict | None = None,
                  modelo: str | None = None, esforco: str | None = None, projeto: str | None = None,
                  modo: str = 'pedir') -> None:
    """Roda no laço da thread do SDK. `por(tipo, valor)` manda pro laço do servidor.
    `retomar`: a sessão anterior da conversa, que continua com o que já leu e fez."""
    from claude_agent_sdk import (
        AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, RateLimitEvent, ResultMessage,
        StreamEvent, ToolResultBlock, ToolUseBlock, UserMessage,
    )
    usadas: dict[str, tuple[str, dict]] = {}
    estado = estado if estado is not None else {}
    estado.setdefault('aprovacoes', set())

    async def decidir(nome, entrada, contexto):
        return await _decidir(nome, entrada, por, estado['aprovacoes'], projeto, modo)

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
    )
    pensou = False
    async with ClaudeSDKClient(options=opcoes) as cliente:
        # Pra o Matheus poder parar no meio: o outro lado chama interrupt()
        # neste laço (claude(), no finally).
        estado['cliente'] = cliente
        estado['laco'] = asyncio.get_running_loop()
        await cliente.query(prompt)
        async for m in cliente.receive_response():
            if isinstance(m, StreamEvent):
                delta = m.event.get('delta') or {}
                if m.event.get('type') == 'content_block_delta' and m.parent_tool_use_id is None:
                    if delta.get('type') == 'text_delta' and delta.get('text'):
                        por('texto', delta['text'])
                    elif delta.get('type') == 'thinking_delta' and not pensou:
                        por('etapa', ('pensando', {'cerebro': 'claude'}))
                        pensou = True
            elif isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, ToolUseBlock):
                        usadas[b.id] = (b.name, b.input)
            elif isinstance(m, UserMessage) and isinstance(m.content, list):
                for b in m.content:
                    if isinstance(b, ToolResultBlock) and b.tool_use_id in usadas:
                        nome, entrada = usadas.pop(b.tool_use_id)
                        if nome in ('ToolSearch', 'TodoWrite'):
                            continue
                        por('etapa', ('ferramenta', {'ferramenta': nome, 'alvo': _alvo(nome, entrada),
                                                     'ok': not b.is_error}))
            elif isinstance(m, RateLimitEvent):
                # "rejected" é a cota acabada; o resets_at diz quando volta. O
                # aviso de cota perto do fim ("allowed_warning") não para nada.
                if m.rate_limit_info.status == 'rejected':
                    por('cota', m.rate_limit_info.resets_at)
            elif isinstance(m, ResultMessage):
                if m.is_error:
                    raise AgenteFalhou(str(m.result or m.subtype)[:300])
                por('custo', {'usd': m.total_cost_usd, 'turnos': m.num_turns, 'sessao': m.session_id})


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
                 ao_sessao=None, projeto: str | None = None, modo: str = 'pedir') -> AsyncIterator[str]:
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
            proprio.run_until_complete(_sessao(sistema, prompt, por, retomar, estado=estado,
                                               modelo=escolha['modelo'], esforco=escolha['esforco'],
                                               projeto=projeto, modo=modo))
        except Exception as e:  # noqa: BLE001 — vira erro do cérebro, do outro lado
            if not estado.get('parado'):
                log.exception('o agente do Claude falhou')
            por('erro', e)
        finally:
            por('fim')
            proprio.close()

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


async def _ler(fila: asyncio.Queue, etapas, ao_sessao) -> AsyncIterator[str]:
    while True:
        tipo, valor = await fila.get()
        if tipo == 'texto':
            yield valor
        elif tipo == 'etapa':
            etapa, dados = valor
            etapas.marcar(etapa, **dados)
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
