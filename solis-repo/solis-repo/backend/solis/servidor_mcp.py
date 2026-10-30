"""A memória do Solis aberta pro Claude Code e o Codex, pelo MCP.

Com isto, quando o Matheus usa o Claude Code ou o Codex direto no terminal —
fora do Solis — eles ainda consultam o que o Solis sabe sobre ele, e podem
guardar coisas nele. A memória fica num lugar só: no Solis.

Processo próprio, pela entrada e saída padrão (é assim que os dois CLIs sobem
um servidor MCP). Lê o mesmo `solis.db` que o servidor do Solis, direto do
arquivo: funciona mesmo com o servidor do Solis desligado.

Nada privado sai por aqui. Memória privada e mensagem privada não aparecem em
nenhuma ferramenta — quem está do outro lado é um modelo de nuvem.

    python -m solis.servidor_mcp        # quem roda é o CLI, não o Matheus

Como registrar: ver backend/README.md, seção "Servidor MCP".
"""
from mcp.server.mcpserver import MCPServer

from . import banco, busca, memoria, ollama

servidor = MCPServer(
    name='solis',
    instructions=(
        'Memória pessoal do Matheus, guardada pelo Solis, o assistente dele. Antes de '
        'trabalhar em algo que dependa de quem ele é, do que ele faz ou do que já foi '
        'decidido, consulte aqui. Quando ele disser algo duradouro sobre si, ou pedir '
        'pra lembrar, guarde aqui.'
    ),
)

PERFIL_MAX = 60


@servidor.tool()
async def memorias_do_matheus() -> list[dict]:
    """O que o Solis sabe sobre o Matheus: trabalho, estudos, preferências,
    projetos e decisões. As mais recentes primeiro."""
    return [_publica(m) for m in banco.memorias() if not m['privada']][:PERFIL_MAX]


@servidor.tool()
async def buscar_na_memoria(assunto: str, quantas: int = 10) -> dict:
    """Memórias e trechos de conversas antigas ligados a um assunto, por
    significado (não precisa ser a palavra exata)."""
    quantas = max(1, min(quantas, 30))
    parecidas = await busca.memorias_parecidas(assunto, quantas * 2)
    # Conversa 0 não existe: nenhuma fica de fora por estar "aberta".
    _, trechos = await busca.contexto(assunto, 0)
    return {
        'memorias': [_publica(m) for m in parecidas if not m['privada']][:quantas],
        'trechos': [
            {'data': t['criada'][:10], 'quem': ollama.autor(t), 'texto': t['texto']}
            for t in trechos
            if not t['privada']
        ],
    }


@servidor.tool()
async def guardar_memoria(texto: str, tema: str) -> str:
    """Guarda um fato duradouro sobre o Matheus. `texto`: uma frase curta em
    terceira pessoa ("Trabalha na Syngenta."). `tema`: uma palavra ou duas que
    agrupem ("Trabalho")."""
    texto, tema = texto.strip(), tema.strip() or 'Geral'
    if not texto:
        return 'Nada guardado: texto vazio.'
    banco.adicionar_memoria(texto, tema, pedido=True, conversa=None, privada=memoria.eh_privado(texto))
    # Best effort: sem o Ollama, o vetor fica pendente e entra na próxima vez.
    await busca.indexar_pendentes()
    return f'Guardado no Solis: {texto}'


def _publica(m: dict) -> dict:
    return {'texto': m['texto'], 'tema': m['tema'], 'desde': m['criada'][:10]}


if __name__ == '__main__':
    servidor.run('stdio')
