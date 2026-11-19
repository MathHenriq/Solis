"""O corpo do Solis: as ferramentas que qualquer cérebro usa.

Decisão do Matheus (18/11/2026, CLAUDE.md → "As funções são do Solis, não do
Claude"): o Solis é um corpo e o cérebro é que se troca. O que o corpo faz,
todos os cérebros fazem — um se diferencia do outro só pela capacidade de
pensar. Então as ferramentas moram aqui, e cada cérebro recebe as mesmas:

- o Claude, pelo Agent SDK (agente.py monta o servidor MCP dele com estas);
- os de API (Groq, Gemini, Mistral, OpenRouter), pelo laço de ferramentas do
  `chat/completions` (apis.responder com um `Corpo`).

Hoje o corpo tem as do Solis (hora, lembrete, agenda, tarefas, memória,
agendar) e o navegador (o mesmo servidor @playwright/mcp que o Claude usa). As
aprovações são as mesmas do Claude: o mesmo cartão, o mesmo "sempre", o mesmo
registro (agente._decidir). Faltam no corpo, pros cérebros de API: arquivos,
terminal e a tela — eles ainda passam esses pedidos pra quem tem
(roteador.PASSA).

Por que o navegador vai inteiro pro Claude e só o essencial pros outros:
medido em 18/11/2026, as 25 ferramentas do servidor somam 19.126 caracteres
de descrição (~5 mil tokens) em CADA pedido; no grátis da Groq, que limita
tokens por minuto, isso sozinho comeria o minuto. As 12 essenciais (abrir,
ler, clicar, escrever, preencher, escolher, teclas, abas, esperar) somam
~7.800.
"""
import asyncio
import copy
import json
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from . import banco, navegador, pc, tela
from .etapas import MUDA

log = logging.getLogger('solis.corpo')

SOLIS = 'mcp__solis__'


@dataclass
class Ferramenta:
    """Uma ferramenta do Solis: o nome curto (o do Claude é mcp__solis__ + nome),
    a descrição pro modelo, os parâmetros (JSON Schema) e o que ela faz."""
    nome: str
    descricao: str
    parametros: dict
    rodar: Callable[[dict], Awaitable[str]]

    @property
    def completo(self) -> str:
        return SOLIS + self.nome


def _objeto(propriedades: dict, obrigatorios: list[str] | None = None) -> dict:
    return {'type': 'object', 'properties': propriedades,
            'required': list(propriedades) if obrigatorios is None else obrigatorios}


_TEXTO = {'type': 'string'}


async def _hora(args: dict) -> str:
    return datetime.now().strftime('%A, %d/%m/%Y, %H:%M')


async def _criar_lembrete(args: dict) -> str:
    dia = (args.get('dia') or '').strip() or None
    h = (args.get('hora') or '').strip() or None
    banco.adicionar_tarefa(args['texto'].strip(), dia, h)
    return f'Anotado: {args["texto"]}' + (f', {dia}' if dia else '') + (f' às {h}' if h else '') + '.'


async def _marcar_compromisso(args: dict) -> str:
    banco.adicionar_compromisso(args['titulo'].strip(), args['dia'], (args.get('hora') or None),
                                None, (args.get('onde') or None))
    return f'Na agenda: {args["titulo"]}, {args["dia"]}' + (f' às {args["hora"]}' if args.get('hora') else '') + '.'


async def _ver_agenda(args: dict) -> str:
    itens = banco.compromissos(args['de'], args['ate'], 100)
    linhas = [f'{c["dia"]} {c.get("hora") or ""} {c["titulo"]}' + (f' ({c["onde"]})' if c.get('onde') else '')
              for c in itens if not c.get('privado')]
    return '\n'.join(linhas) or 'Nada na agenda nesse período.'


async def _ver_tarefas(args: dict) -> str:
    linhas = [f'{t.get("prazo") or "sem prazo"} {t.get("hora") or ""} {t["texto"]}'
              for t in banco.tarefas_abertas(50) if not t.get('privada')]
    return '\n'.join(linhas) or 'Nenhuma tarefa aberta.'


async def _buscar_memoria(args: dict) -> str:
    achadas = [m for m in banco.buscar_memorias(args['busca'], 20) if not m.get('privada')]
    return '\n'.join(f'- {m["texto"]}' for m in achadas) or 'Nada guardado sobre isso.'


async def _agendar_tarefa(args: dict) -> str:
    from . import agendadas
    try:
        dia, data = args.get('dia_semana'), (args.get('data') or None)
        agendadas.validar(args['frequencia'], args['hora'], dia, data)
        prox = agendadas.proxima(args['frequencia'], args['hora'], datetime.now(), dia, data)
    except (agendadas.AgendaInvalida, KeyError) as e:
        return f'Não deu pra agendar: {e} inválida.'
    if prox is None:
        return 'Não deu pra agendar: essa data já passou.'
    a = banco.criar_agendada(args['nome'].strip()[:120], args['pedido'].strip()[:4000], args['frequencia'],
                             args['hora'], dia, data, prox.isoformat(timespec='minutes'))
    return (f'Agendada: {a["nome"]}, {agendadas.descrever(a).lower()}. Próxima vez: '
            f'{prox.strftime("%d/%m às %H:%M")}. Fica em Configurações → Tarefas agendadas.')


DO_SOLIS: list[Ferramenta] = [
    Ferramenta('hora', 'A data e a hora de agora no computador do Matheus.', _objeto({}), _hora),
    Ferramenta('criar_lembrete', 'Anota uma tarefa (com dia e hora opcionais) na tela Tarefas; com hora, o '
               'Solis avisa no Windows na hora. Use quando o Matheus pedir pra lembrar, anotar ou avisar.',
               _objeto({'texto': _TEXTO, 'dia': _TEXTO, 'hora': _TEXTO}), _criar_lembrete),
    Ferramenta('marcar_compromisso', 'Põe um compromisso na Agenda do Matheus. dia em AAAA-MM-DD, hora em HH:MM.',
               _objeto({'titulo': _TEXTO, 'dia': _TEXTO, 'hora': _TEXTO, 'onde': _TEXTO}), _marcar_compromisso),
    Ferramenta('ver_agenda', 'Os compromissos do Matheus entre duas datas (AAAA-MM-DD, as duas inclusas).',
               _objeto({'de': _TEXTO, 'ate': _TEXTO}), _ver_agenda),
    Ferramenta('ver_tarefas', 'As tarefas abertas do Matheus, com prazo e hora.', _objeto({}), _ver_tarefas),
    Ferramenta('buscar_memoria', 'Procura nas memórias que o Solis guarda sobre o Matheus.',
               _objeto({'busca': _TEXTO}), _buscar_memoria),
    Ferramenta('agendar_tarefa', 'Agenda uma tarefa que o Claude faz sozinho num horário, como as tarefas agendadas '
               'do Claude Desktop: na hora, o Solis abre uma conversa com o nome da tarefa, manda o pedido e avisa no '
               'Windows quando acaba. Use quando o Matheus pedir pra fazer algo todo dia, toda semana, numa data. '
               'frequencia: uma_vez (com data AAAA-MM-DD), diaria, dias_uteis, semanal (com dia_semana 0 = segunda '
               '... 6 = domingo) ou hora_em_hora (só os minutos da hora contam). hora em HH:MM. pedido: o que fazer, '
               'escrito pra quem vai fazer sem ninguém olhando. O Matheus aprova antes de agendar.',
               _objeto({'nome': _TEXTO, 'pedido': _TEXTO,
                        'frequencia': {'type': 'string',
                                       'enum': ['uma_vez', 'diaria', 'dias_uteis', 'semanal', 'hora_em_hora']},
                        'hora': _TEXTO, 'dia_semana': {'type': 'integer'}, 'data': _TEXTO},
                       ['nome', 'pedido', 'frequencia', 'hora']), _agendar_tarefa),
]
_POR_NOME = {f.completo: f for f in DO_SOLIS}

# As do navegador que vão pros cérebros de API (ver o topo do arquivo), e de
# cada uma só os parâmetros que o dia a dia usa: medido na Groq de verdade
# (18/11/2026), o que pesava em cada rodada eram as descrições das ferramentas
# (~10 mil caracteres), não a página. Os parâmetros de fora (o print com
# caixas, digitar devagar, contexto isolado...) ficam pro Claude.
NAVEGADOR_ESSENCIAIS = {
    'browser_navigate': ('url',),
    'browser_navigate_back': (),
    'browser_snapshot': (),
    'browser_click': ('element', 'target', 'doubleClick'),
    'browser_type': ('element', 'target', 'text', 'submit'),
    'browser_press_key': ('key',),
    'browser_fill_form': ('fields',),
    'browser_select_option': ('element', 'target', 'values'),
    'browser_tabs': ('action', 'index', 'url'),
    'browser_wait_for': ('time', 'text', 'textGone'),
    'browser_hover': ('element', 'target'),
    'browser_handle_dialog': ('accept', 'promptText'),
}
# As descrições dos parâmetros que se repetem, curtas. O `element` vira
# obrigatório: é o que o cartão de aprovação mostra ("Clicar em botão Assistir").
_PARAMETROS = {
    'target': 'A referência do elemento no browser_snapshot (ex.: e12).',
    'element': 'O elemento em poucas palavras (vai pro cartão de aprovação do Matheus).',
}
_DESCRICAO_MAX = 80

# O que uma ferramenta devolve pro modelo, no máximo. A árvore de uma página
# (browser_snapshot) passa fácil de 30 mil caracteres; um cérebro de API no
# grátis não aguenta isso a cada rodada. PROVISÓRIO: medindo com páginas reais.
RESULTADO_MAX = 12_000
# Quantas rodadas (pedir ferramenta → resultado → seguir) numa resposta.
RODADAS_MAX = 12

# O terminal: o mesmo nome e a mesma entrada do PowerShell do Claude, pra
# valerem o mesmo cartão ("Rodar no terminal: ..."), o mesmo "Sempre este
# comando" (o comando exato) e o mesmo registro (agente._decidir).
TERMINAL = 'PowerShell'
TERMINAL_MAX_S = 120
_TERMINAL = {
    'type': 'function',
    'function': {
        'name': TERMINAL,
        'description': ('Roda um comando no PowerShell do Windows do Matheus, na pasta de trabalho (a do projeto da '
                        'conversa, se houver). Cada comando pede a aprovação dele, num cartão. No máximo '
                        f'{TERMINAL_MAX_S} s; devolve a saída e o código de saída.'),
        'parameters': {'type': 'object', 'required': ['command', 'description'], 'properties': {
            'command': {'type': 'string', 'description': 'O comando, como seria digitado no PowerShell.'},
            'description': {'type': 'string', 'description': 'O que ele faz, em poucas palavras.'}}},
    },
}


def _rodar_comando(comando: str, pasta: str) -> tuple[str, bool]:
    """(saída pro modelo, se saiu com 0). A saída em UTF-8 (o padrão do
    PowerShell é a página de código antiga, e o acento chegava quebrado)."""
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command',
             '[Console]::OutputEncoding = [Text.Encoding]::UTF8; ' + comando],
            cwd=pasta, capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=TERMINAL_MAX_S, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        return f'Passou de {TERMINAL_MAX_S} s: o comando foi parado.', False
    except OSError as e:
        return f'O PowerShell não abriu: {e}', False
    saida = (r.stdout or '') + (('\n' + r.stderr) if r.stderr.strip() else '')
    return f'(código de saída {r.returncode})\n{saida.strip()}', r.returncode == 0


# A tela, pra quem não vê imagem (a Groq e os outros de API só leem texto):
# tela_ler é o texto da tela com a posição de cada linha (o OCR do Windows,
# ocr.linhas_com_posicao), nas mesmas coordenadas do print que o Claude vê
# (tela.escala). As ações têm os mesmos nomes das do Claude: o mesmo cartão,
# com o print marcado pro Matheus, e o mesmo "Sempre neste programa".
TELA_LER = SOLIS + 'tela_ler'
_XY = {'x': {'type': 'number'}, 'y': {'type': 'number'}}
_DA_TELA = [
    ('tela_ler', 'O texto da tela principal do PC do Matheus agora, cada linha com o centro [x,y] em pixels '
                 '(0,0 no canto de cima à esquerda) e o programa que está na frente. Leia antes de agir.',
     {'type': 'object', 'properties': {}}),
    ('tela_clicar', 'Clica num ponto da tela (as coordenadas do tela_ler). botao: esquerdo (padrão), direito ou meio; '
                    'duplo: clique duplo. O Solis mostra o cartão pro Matheus.',
     {'type': 'object', 'required': ['x', 'y'], 'properties': {
         **_XY, 'botao': {'type': 'string', 'enum': list(tela.BOTOES)}, 'duplo': {'type': 'boolean'}}}),
    ('tela_digitar', 'Digita um texto na janela da frente (clique no campo antes). \\n vira Enter. Nunca senha, '
                     'cartão ou documento.',
     {'type': 'object', 'required': ['texto'], 'properties': {'texto': {'type': 'string'}}}),
    ('tela_tecla', 'Aperta uma tecla ou combinação na janela da frente: "enter", "ctrl+s", "alt+tab", "f5".',
     {'type': 'object', 'required': ['teclas'], 'properties': {'teclas': {'type': 'string'}}}),
    ('tela_rolar', 'Rola a tela no ponto. direcao: cima, baixo, esquerda ou direita; quantidade: cliques da rodinha '
                   '(padrão 3).',
     {'type': 'object', 'required': ['x', 'y', 'direcao'], 'properties': {
         **_XY, 'direcao': {'type': 'string', 'enum': ['cima', 'baixo', 'esquerda', 'direita']},
         'quantidade': {'type': 'integer'}}}),
    ('tela_mover', 'Leva o mouse até um ponto, sem clicar (pra abrir um menu de passar o mouse).',
     {'type': 'object', 'required': ['x', 'y'], 'properties': _XY}),
]


def _agir_na_tela(acao: str, e: dict) -> None:
    if acao == 'tela_clicar':
        tela.clicar(float(e['x']), float(e['y']), e.get('botao') or 'esquerdo', bool(e.get('duplo')))
    elif acao == 'tela_digitar':
        tela.digitar(str(e['texto']))
    elif acao == 'tela_tecla':
        tela.tecla(str(e['teclas']))
    elif acao == 'tela_rolar':
        tela.rolar(float(e['x']), float(e['y']), str(e['direcao']), int(e.get('quantidade') or 3))
    elif acao == 'tela_mover':
        tela.mover(float(e['x']), float(e['y']))


async def texto_da_tela() -> str:
    """O que o cérebro sem visão recebe no lugar do print: as linhas de texto,
    cada uma com o centro, nas coordenadas do print (as que as ações usam)."""
    from . import ocr
    imagem = await asyncio.to_thread(tela._print)
    e = tela.escala()
    processo, titulo = await asyncio.to_thread(tela.janela_ativa)
    linhas = await ocr.linhas_com_posicao(await asyncio.to_thread(tela._png, imagem))
    largura, altura = round(imagem.width * e), round(imagem.height * e)
    corpo = '\n'.join(f'[{round((x + w / 2) * e)},{round((y + h / 2) * e)}] {t}' for x, y, w, h, t in linhas)
    return (f'Tela {largura}x{altura}; na frente: {tela.nome_do_programa(processo, titulo)}.\n'
            + (corpo or '(nenhum texto na tela)'))


# As chaves de JSON Schema que todo provedor aceita (o Gemini recusa "$schema"
# e outras); o resto sai.
_CHAVES = {'type', 'properties', 'required', 'items', 'enum', 'description', 'default', 'anyOf'}


def _limpar(esquema):
    if isinstance(esquema, dict):
        limpo = {k: _limpar(v) for k, v in esquema.items() if k in _CHAVES}
        if 'properties' in esquema:
            limpo['properties'] = {k: _limpar(v) for k, v in esquema['properties'].items()}
        return limpo
    if isinstance(esquema, list):
        return [_limpar(x) for x in esquema]
    return esquema


def _curto(esquema):
    """Sem as descrições longas (de parâmetro e de dentro de listas)."""
    if isinstance(esquema, dict):
        r = {k: _curto(v) for k, v in esquema.items()
             if not (k == 'description' and isinstance(v, str) and len(v) > _DESCRICAO_MAX)}
        if 'properties' in esquema:
            r['properties'] = {k: _curto(v) for k, v in esquema['properties'].items()}
        return r
    if isinstance(esquema, list):
        return [_curto(x) for x in esquema]
    return esquema


def _enxuto(acao: str, esquema: dict) -> dict:
    """O esquema do servidor só com os parâmetros que vão (NAVEGADOR_ESSENCIAIS)."""
    quais = NAVEGADOR_ESSENCIAIS[acao]
    props = {k: v for k, v in (esquema.get('properties') or {}).items() if k in quais}
    for k, texto in _PARAMETROS.items():
        if k in props:
            props[k] = {**props[k], 'description': texto}
    obrigatorios = [k for k in esquema.get('required') or [] if k in props]
    if 'element' in props and 'element' not in obrigatorios:
        obrigatorios.insert(0, 'element')
    return _curto({'type': 'object', 'properties': props, 'required': obrigatorios})


def _funcao(nome: str, descricao: str, parametros: dict) -> dict:
    return {'type': 'function', 'function': {'name': nome, 'description': descricao,
                                             'parameters': _limpar(copy.deepcopy(parametros))}}


# A página aberta por conversa: é ela que diz o site de um clique (o cartão e
# o "Sempre neste site"). O Claude guarda a dele na sessão viva (agente._Viva).
_paginas: dict[int | None, str] = {}


def _cortar(texto: str) -> str:
    if len(texto) <= RESULTADO_MAX:
        return texto
    return texto[:RESULTADO_MAX] + f'\n\n[cortado: a resposta tinha {len(texto)} caracteres]'


class Corpo:
    """As ferramentas de uma resposta de um cérebro de API: o que oferecer
    (`especificacoes`, no formato do chat/completions) e rodar o que o modelo
    pedir, com o cartão de aprovação quando a ação pede (`rodar`)."""

    def __init__(self, conversa: int | None, etapas=MUDA, navegar: bool | None = None):
        self.conversa, self.etapas = conversa, etapas
        # Ligado em Configurações → Navegador (e o @playwright/mcp instalado).
        self.navegar = (navegador.escolhido() is not None and navegador._cli().is_file()) if navegar is None else navegar
        self._nav: list[dict] | None = None
        # O terminal (PowerShell), com o cartão. SOLIS_CORPO_TERMINAL=0 tira.
        self.terminal = os.name == 'nt' and os.environ.get('SOLIS_CORPO_TERMINAL', '1') != '0'
        # Ler os arquivos das pastas autorizadas (pc.py), livre, como o Claude lê.
        # Decisão do Matheus (18/11/2026): "podem, como o Claude".
        self.arquivos = pc.disponivel()
        # A tela (Configurações → Controle da tela), lida como texto.
        self.tela = os.name == 'nt' and tela.ligada()
        self.agiu = False  # rodou alguma ferramenta que muda algo (a queda pro próximo cérebro refaria)

    async def especificacoes(self) -> list[dict]:
        specs = [_funcao(f.completo, f.descricao, f.parametros) for f in DO_SOLIS]
        if self.arquivos:
            specs += [_funcao(SOLIS + f['function']['name'], f['function']['description'], f['function']['parameters'])
                      for f in pc.FERRAMENTAS]
        if self.terminal:
            specs.append(copy.deepcopy(_TERMINAL))
        if self.tela:
            specs += [_funcao(SOLIS + n, d, p) for n, d, p in _DA_TELA]
        if self.navegar:
            specs += await self._do_navegador()
        return specs

    async def _do_navegador(self) -> list[dict]:
        if self._nav is None:
            try:
                lista = await asyncio.to_thread(navegador.ferramentas)
            except navegador.NavegadorFalhou as e:
                log.warning('corpo: o navegador não abriu (%s); seguindo sem ele', e)
                lista = []
            self._nav = [_funcao(navegador.PREFIXO + t['name'], (t.get('description') or '').split('. ')[0],
                                 _enxuto(t['name'], t.get('inputSchema') or {}))
                         for t in lista if t['name'] in NAVEGADOR_ESSENCIAIS]
        return self._nav

    def tem(self, nome: str) -> bool:
        return (nome in _POR_NOME or (self.terminal and nome == TERMINAL) or self._de_arquivo(nome)
                or (self.tela and nome.removeprefix(SOLIS) in {n for n, _, _ in _DA_TELA})
                or (self.navegar and navegador.acao(nome) in NAVEGADOR_ESSENCIAIS))

    def _de_arquivo(self, nome: str) -> bool:
        return self.arquivos and nome.startswith(SOLIS) and nome.removeprefix(SOLIS) in pc.FUNCOES

    def pasta(self) -> str:
        """Onde o comando roda: a pasta do projeto da conversa, ou a de trabalho do Solis."""
        from . import agente
        projeto = banco.projeto_da_conversa(self.conversa)['pasta'] if self.conversa is not None else None
        return str(agente._base(projeto))

    async def rodar(self, nome: str, entrada: dict) -> str:
        """Roda o que o modelo pediu e devolve o texto pro modelo. Uma recusa
        (do Matheus ou da regra) volta como texto também: o modelo segue a
        resposta sabendo que não fez."""
        from . import agente
        id_ = uuid.uuid4().hex[:12]
        if not self.tem(nome):
            return f'Essa ferramenta não existe aqui: {nome}.'
        pagina = _paginas.get(self.conversa)

        def por(tipo, valor=None):
            if tipo == 'etapa':
                etapa, dados = valor
                self.etapas.marcar(etapa, **dados)

        decisao = await agente._decidir(nome, entrada, por, conversa=self.conversa, pagina=pagina)
        mensagem = getattr(decisao, 'message', None)
        if type(decisao).__name__ == 'PermissionResultDeny':
            self._marcar(id_, nome, entrada, pagina, ok=False)
            return mensagem or 'O Matheus recusou.'
        if nome in _POR_NOME:
            try:
                saida, ok = await _POR_NOME[nome].rodar(entrada), True
            except (KeyError, TypeError, ValueError) as e:
                saida, ok = f'Não deu: faltou ou veio errado {e}.', False
            if nome != SOLIS + 'hora' and not nome.startswith(SOLIS + 'ver_') and nome != SOLIS + 'buscar_memoria':
                self.agiu = self.agiu or ok
            anotadas = getattr(self.etapas, 'anotadas', None)
            if ok and nome == SOLIS + 'criar_lembrete' and anotadas is not None:
                # O aprendizado depois da resposta não anota a mesma de novo.
                anotadas.append({'texto': str(entrada.get('texto') or '').strip(),
                                 'prazo': (entrada.get('dia') or '').strip() or None,
                                 'hora': (entrada.get('hora') or '').strip() or None})
            self._marcar(id_, nome, entrada, pagina, ok)
            return saida
        if self.tela and nome.removeprefix(SOLIS) in {n for n, _, _ in _DA_TELA}:
            acao = nome.removeprefix(SOLIS)
            try:
                if acao != 'tela_ler':
                    await asyncio.to_thread(_agir_na_tela, acao, entrada)
                    self.agiu = True
                    await asyncio.sleep(tela.DEPOIS_S)
                saida, ok = await texto_da_tela(), True
            except tela.TelaRecusada as e:
                saida, ok = f'Não fiz: {e}.', False
            except (KeyError, TypeError, ValueError) as e:
                saida, ok = f'Não deu: faltou ou veio errado {e}.', False
            except Exception as e:  # noqa: BLE001 — o OCR não leu: o modelo fica sabendo
                saida, ok = f'Não consegui ler a tela: {e}', False
            self._marcar(id_, nome, entrada, pagina, ok)
            return _cortar(saida if acao == 'tela_ler' or not ok else f'Feito. A tela agora:\n{saida}')
        if self._de_arquivo(nome):
            # Só dentro das pastas autorizadas: o próprio pc.py recusa o resto.
            saida, ok = await asyncio.to_thread(pc.rodar, nome.removeprefix(SOLIS), entrada, self.conversa)
            self.etapas.marcar('ferramenta', ferramenta=nome, alvo=pc.alvo(entrada), ok=ok, id=id_)
            return _cortar(saida)
        if nome == TERMINAL:
            comando = str(entrada.get('command') or '').strip()
            if not comando:
                self._marcar(id_, nome, entrada, pagina, ok=False)
                return 'Faltou o comando.'
            saida, ok = await asyncio.to_thread(_rodar_comando, comando, self.pasta())
            self.agiu = True
            self._marcar(id_, nome, entrada, pagina, ok, saida=agente._limpar_saida(saida))
            return _cortar(saida)
        acao = navegador.acao(nome)
        try:
            saida = await asyncio.to_thread(navegador.chamar, acao, entrada)
            ok = True
        except navegador.NavegadorFalhou as e:
            saida, ok = f'O navegador não fez: {e}', False
        _paginas[self.conversa] = navegador.pagina_do_resultado(saida) or pagina or ''
        if ok:
            navegador.segurar()
            if acao in navegador.PEDEM:
                self.agiu = True
        self._marcar(id_, nome, entrada, _paginas.get(self.conversa), ok)
        return _cortar(saida)

    def _marcar(self, id_: str, nome: str, entrada: dict, pagina: str | None, ok: bool, **extra) -> None:
        from . import agente
        alvo = navegador.alvo(nome, entrada, pagina) if navegador.acao(nome) else agente._alvo(nome, entrada)
        # `saida`: a do terminal fica no passo, pra abrir depois (como a do Claude).
        self.etapas.marcar('ferramenta', ferramenta=nome, alvo=alvo, ok=ok, id=id_, **extra)


def argumentos(texto: str | None) -> dict:
    """Os argumentos que o modelo mandou (um JSON em texto); vazio, se veio quebrado."""
    try:
        valor = json.loads(texto or '{}')
    except json.JSONDecodeError:
        return {}
    return valor if isinstance(valor, dict) else {}
