"""Quem responde cada mensagem: modelo local, Claude ou Codex.

Regras em código, não um modelo decidindo: decidir não pode gastar VRAM nem
cota, e regra escrita é previsível — dá pra saber por que cada mensagem foi pra
onde foi.

1. Comando na frente da mensagem manda: /claude, /codex, /local, /groq... Sem plano B —
   se o escolhido falhar, o Matheus fica sabendo em vez de receber resposta de
   outro sem pedir.
2. Mensagem dita em sigilo ("isso é privado...") só vai pro local.
3. O resto segue a ordem de preferência (SOLIS_CEREBROS), pulando quem está
   fora (não instalado, cota acabada) e caindo pro próximo se falhar antes da
   primeira palavra.

Pro que vai pra nuvem, o que é privado fica de fora: memória privada, mensagem
privada (no histórico ou como trecho antigo), e o resumo de uma conversa que
tenha qualquer coisa privada — não dá pra saber o que um resumo carrega.
"""
import os
import re
from collections.abc import AsyncIterator

from . import banco, cerebros, memoria, ollama, pc
from .etapas import MUDA

# Preferência do Matheus: os modelos mais fortes primeiro; o local quando a cota
# acabar. É o padrão até ele escolher pela tela (Configurações → Cérebros), que
# vence; SOLIS_CEREBROS=local,claude muda o padrão sem código.
ORDEM = [c.strip() for c in os.environ.get('SOLIS_CEREBROS', 'claude,codex,local').split(',') if c.strip()]


def preferencia() -> list[dict]:
    """Todos os cérebros, na ordem escolhida, cada um ligado ou não.

    O que a tela guardou vence o ORDEM. Cérebro que não está em nenhum dos dois
    (um que entrou depois da escolha) vai pro fim, desligado: ligar um cérebro
    de nuvem é decisão do Matheus, não do Solis. O local nunca desliga — é por
    ele que passa o que é privado."""
    guardada = banco.ajuste('cerebros')
    if guardada is None:
        guardada = [{'nome': c, 'ligado': True} for c in ORDEM if c in cerebros.NOMES]
        guardada += [{'nome': c, 'ligado': False} for c in cerebros.NOMES if c not in ORDEM]
    vistos = {p['nome'] for p in guardada}
    novos = [{'nome': c, 'ligado': c == 'local'} for c in cerebros.NOMES if c not in vistos]
    return [
        {'nome': p['nome'], 'ligado': p['nome'] == 'local' or p['ligado']}
        for p in guardada + novos
        if p['nome'] in cerebros.NOMES
    ]


def guardar_preferencia(ordem: list[dict]) -> list[dict]:
    """Valida e guarda. ValueError com nome repetido ou desconhecido. Quem
    ficou de fora entra no fim pelo preferencia() (desligado, menos o local) —
    assim uma tela mais velha que um cérebro novo não quebra."""
    nomes = [p['nome'] for p in ordem]
    if len(set(nomes)) != len(nomes) or not set(nomes) <= set(cerebros.NOMES):
        raise ValueError('cada cérebro uma vez, só os que existem')
    banco.guardar_ajuste('cerebros', [{'nome': p['nome'], 'ligado': bool(p['ligado'])} for p in ordem])
    return preferencia()


def ligar(nome: str, ligado: bool) -> None:
    """Liga ou desliga um cérebro sem mexer na ordem."""
    guardar_preferencia([{**p, 'ligado': ligado} if p['nome'] == nome else p for p in preferencia()])


def _ordem() -> list[str]:
    return [p['nome'] for p in preferencia() if p['ligado']]

# /claude, /codex, /local, /groq, /gemini... — um por cérebro.
COMANDOS = {f'/{nome}': nome for nome in cerebros.NOMES}

SISTEMA_NUVEM = (
    'Você é o Solis, o assistente pessoal do Matheus. Nesta mensagem quem pensa é '
    'você, chamado pelo Solis; o Matheus fala com você pela interface do Solis, '
    'não por um terminal.\n\n'
    'Responda COMO o Solis, não como o modelo que você é: o Matheus fala com o Solis, '
    'e o que o Solis faz em volta de você vale como seu. O que o Solis faz sozinho, '
    'depois da sua resposta, a partir do que o Matheus disse:\n'
    '- anota tarefas e lembretes na tela Tarefas; lembrete com hora ("daqui a 30 '
    'minutos", "às 15h") vira aviso no Windows na hora certa;\n'
    '- põe compromissos com dia marcado na tela Agenda;\n'
    '- guarda memórias.\n'
    'Então, pedido de lembrete, tarefa ou compromisso: confirme o que ficou anotado e '
    'a hora, contando a partir de Agora (no contexto) — nunca diga que não consegue '
    'lembrar ou avisar, nem mande usar o celular ou outro app pra isso. A data e a hora '
    'de agora estão no contexto: você sabe que horas são.\n\n'
    'O que fica com o modelo local do Solis, não com você: ler arquivos do computador e '
    'o que for privado. Você não roda comandos nem acessa a internet nesta resposta. '
    'Junto da mensagem vêm as memórias que o Solis guarda sobre o Matheus e o contexto '
    'da conversa — use o que ajudar.\n\n'
    # Sem esta frase, "grave isso" recebia "não consigo gravar daqui" — falso: o
    # Solis guarda sozinho, depois da resposta (visto rodando o Claude Code).
    'Guardar memória não é com você: o Solis guarda sozinho, depois da sua '
    'resposta, o que importa e tudo o que o Matheus pedir pra guardar. Quando ele '
    'pedir, confirme que ficou guardado.\n\n'
    'Quando não souber algo, diga que não sabe. Responda em português do Brasil, '
    'com clareza e sem rodeios.'
)


def _modo_local(mensagem: str, voz: bool) -> dict:
    """Ferramentas e raciocínio do modelo local. Pela voz, o caminho rápido:
    sem raciocínio e sem ferramentas — o raciocínio custa ~5 s, e sem ele o
    modelo usa mal as ferramentas (5 de 16 certas, medido). Pergunta de arquivo
    pela voz vai com os dois: mais lenta, mas certa."""
    arquivos = pc.disponivel() and do_pc(mensagem)
    if voz and not arquivos:
        return {'ferramentas': False, 'pensar': False}
    return {'ferramentas': pc.disponivel()}


class NinguemRespondeu(Exception):
    def __init__(self, ordem: list[str], erros: dict[str, Exception]):
        super().__init__(', '.join(f'{c}: {e}' for c, e in erros.items()))
        self.ordem, self.erros = ordem, erros


# Pergunta sobre os arquivos do Matheus vai pro local: só ele tem as
# ferramentas do PC (pc.py), e o que ele lê não sai da máquina. Regra escrita,
# como a do privado: os nomes de arquivo e de pasta, e as coisas da vida dele
# que costumam morar num arquivo ("meu contrato", "a reunião", "gastei").
# PROVISÓRIO: conferida nas 22 frases da medição das ferramentas (tests/test_pc.py).
_DO_PC = re.compile(
    r'\b(arquivos?|pastas?|documentos?|planilhas?|pdfs?|readme|computador|meu pc|desktop|downloads)\b'
    r'|\b[\w-]+\.(txt|md|pdf|csv|json|docx?|xlsx?|pptx?|py|ts|js)\b'
    r'|\b(meu|minha|meus|minhas|do meu|da minha)\s+(contrato|aluguel|receita|receitas|notas?|projetos?|relat[oó]rios?|curr[ií]culo|extrato|boletos?|contas?|gastos?|planilha|apartamento|casa)\b'
    r'|\b(reuni[aã]o|gastei|combinei|or[cç]amento|prot[oó]tipo)\b',
    re.IGNORECASE,
)


def do_pc(texto: str) -> bool:
    return bool(_DO_PC.search(texto))


def escolher(texto: str, voz: bool = False) -> tuple[str, list[str], bool]:
    """(texto sem o comando, ordem a tentar, se foi forçado).

    Pela voz (a resposta vai ser falada), o local vai primeiro e a nuvem fica
    de reserva: medido em 11/11/2026, o qwen3:8b sem raciocínio dá a primeira
    palavra em 0,07 s e a resposta em 0,6 s (mediana, 16 pedidos de voz, 12 de
    13 certos; o lembrete com hora vem calculado em código) — o Claude levava 7
    a 10 s só até a primeira palavra. "Que horas são" não precisa da nuvem."""
    primeira, _, resto = texto.strip().partition(' ')
    if primeira.lower() in COMANDOS and resto.strip():
        return resto.strip(), [COMANDOS[primeira.lower()]], True
    if memoria.eh_privado(texto):
        return texto, ['local'], False
    if pc.disponivel() and do_pc(texto):
        return texto, ['local'], False
    if voz:
        return texto, ['local'] + [c for c in _ordem() if c != 'local' and cerebros.disponivel(c)], False
    return texto, [c for c in _ordem() if c == 'local' or cerebros.disponivel(c)], False


def prompt_nuvem(memorias, trechos, resumo, historico, mensagem, voz: bool = False) -> str:
    """Tudo num texto só: os CLIs recebem um prompt, não uma lista de mensagens."""
    partes = [ollama.contexto(memorias, trechos, resumo)]
    if voz:
        partes.append(ollama.VOZ)
    anteriores = historico[:-1]  # a última é a própria mensagem nova
    if anteriores:
        linhas = '\n\n'.join(
            f'{"Matheus" if m["papel"] == "pessoa" else "Solis"}: {m["texto"]}' for m in anteriores
        )
        partes.append(f'Conversa até agora:\n\n{linhas}')
    partes.append(f'Mensagem nova do Matheus:\n\n{mensagem}')
    return '\n\n---\n\n'.join(partes)


async def responder(
    ordem: list[str],
    modelo_local: str,
    conversa: int,
    historico: list[dict],
    memorias: list[dict],
    trechos: list[dict],
    resumo: str | None,
    mensagem: str,
    etapas=MUDA,
    voz: bool = False,
) -> tuple[AsyncIterator[str], str]:
    """(texto em pedaços, quem está respondendo). Tenta na ordem até alguém
    começar a responder."""
    erros: dict[str, Exception] = {}
    for nome in ordem:
        etapas.marcar('cerebro', cerebro=nome)
        try:
            if nome == 'local':
                if not modelo_local:
                    raise ollama.OllamaIndisponivel()
                fluxo = await _primeira_palavra(
                    await ollama.conversar(
                        modelo_local, historico, memorias, trechos, resumo, etapas=etapas,
                        conversa=conversa, voz=voz, **_modo_local(mensagem, voz),
                    ),
                    etapas,
                )
            else:
                fluxo = await cerebros.abrir(
                    nome,
                    SISTEMA_NUVEM,
                    prompt_nuvem(
                        [m for m in memorias if not m['privada']],
                        [t for t in trechos if not t['privada']],
                        None if banco.tem_privada(conversa) else resumo,
                        [m for m in historico if not m['privada']],
                        mensagem,
                        voz=voz,
                    ),
                    etapas,
                )
            return fluxo, nome
        except (ollama.OllamaIndisponivel, ollama.ModeloInexistente, cerebros.CerebroFalhou) as e:
            erros[nome] = e
            etapas.marcar('queda', cerebro=nome, motivo=_motivo(e))
    raise NinguemRespondeu(ordem, erros)


def _motivo(e: Exception) -> str:
    if isinstance(e, ollama.ModeloInexistente):
        return 'modelo não instalado'
    if isinstance(e, ollama.OllamaIndisponivel):
        return 'Ollama fora do ar'
    return str(e)


async def _primeira_palavra(fluxo: AsyncIterator[str], etapas) -> AsyncIterator[str]:
    """O modelo local só marca a primeira palavra quando ela chega — é ali que
    se vê o tempo de carregar o modelo na placa. Sem prazo, como antes: o limite
    do local é o do próprio Ollama."""
    try:
        primeiro = await anext(fluxo)
    except StopAsyncIteration:
        primeiro = None
    etapas.marcar('primeira_palavra', cerebro='local')

    async def resto():
        if primeiro is not None:
            yield primeiro
        async for pedaco in fluxo:
            yield pedaco
    return resto()
