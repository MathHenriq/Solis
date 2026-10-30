"""Quem responde cada mensagem: modelo local, Claude ou Codex.

Regras em código, não um modelo decidindo: decidir não pode gastar VRAM nem
cota, e regra escrita é previsível — dá pra saber por que cada mensagem foi pra
onde foi.

1. Comando na frente da mensagem manda: /claude, /codex, /local. Sem plano B —
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
from collections.abc import AsyncIterator

from . import banco, cerebros, memoria, ollama

# Preferência do Matheus: os modelos mais fortes primeiro; o local quando a cota
# acabar. Mudar a ordem não precisa de código: SOLIS_CEREBROS=local,claude
ORDEM = [c.strip() for c in os.environ.get('SOLIS_CEREBROS', 'claude,codex,local').split(',') if c.strip()]

COMANDOS = {'/claude': 'claude', '/codex': 'codex', '/local': 'local'}

SISTEMA_NUVEM = (
    'Você é o Solis, o assistente pessoal do Matheus. Nesta mensagem quem pensa é '
    'você, chamado pelo Solis; o Matheus fala com você pela interface do Solis, '
    'não por um terminal.\n\n'
    'Aqui você não tem ferramentas: não lê arquivos, não roda comandos e não '
    'acessa a internet. Junto da mensagem vêm as memórias que o Solis guarda sobre '
    'o Matheus e o contexto da conversa — use o que ajudar.\n\n'
    # Sem esta frase, "grave isso" recebia "não consigo gravar daqui" — falso: o
    # Solis guarda sozinho, depois da resposta (visto rodando o Claude Code).
    'Guardar memória não é com você: o Solis guarda sozinho, depois da sua '
    'resposta, o que importa e tudo o que o Matheus pedir pra guardar. Quando ele '
    'pedir, confirme que ficou guardado.\n\n'
    'Quando não souber algo, diga que não sabe. Responda em português do Brasil, '
    'com clareza e sem rodeios.'
)


class NinguemRespondeu(Exception):
    def __init__(self, ordem: list[str], erros: dict[str, Exception]):
        super().__init__(', '.join(f'{c}: {e}' for c, e in erros.items()))
        self.ordem, self.erros = ordem, erros


def escolher(texto: str) -> tuple[str, list[str], bool]:
    """(texto sem o comando, ordem a tentar, se foi forçado)."""
    primeira, _, resto = texto.strip().partition(' ')
    if primeira.lower() in COMANDOS and resto.strip():
        return resto.strip(), [COMANDOS[primeira.lower()]], True
    if memoria.eh_privado(texto):
        return texto, ['local'], False
    return texto, [c for c in ORDEM if c == 'local' or cerebros.disponivel(c)], False


def prompt_nuvem(memorias, trechos, resumo, historico, mensagem) -> str:
    """Tudo num texto só: os CLIs recebem um prompt, não uma lista de mensagens."""
    partes = [ollama.contexto(memorias, trechos, resumo)]
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
) -> tuple[AsyncIterator[str], str]:
    """(texto em pedaços, quem está respondendo). Tenta na ordem até alguém
    começar a responder."""
    erros: dict[str, Exception] = {}
    for nome in ordem:
        try:
            if nome == 'local':
                if not modelo_local:
                    raise ollama.OllamaIndisponivel()
                fluxo = await ollama.conversar(modelo_local, historico, memorias, trechos, resumo)
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
                    ),
                )
            return fluxo, nome
        except (ollama.OllamaIndisponivel, ollama.ModeloInexistente, cerebros.CerebroFalhou) as e:
            erros[nome] = e
    raise NinguemRespondeu(ordem, erros)
