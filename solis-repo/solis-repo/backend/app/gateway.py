"""Ponte com o Ollama.

Uma classe só, com três operações: está de pé, o que tem instalado, responde
isto. Tudo pela API HTTP (`/api/tags`, `/api/chat`) — nunca chamando o binário
`ollama` por subprocess. Motivo: o CLI não existe em toda instalação (o app
oficial do macOS sobe o servidor sem colocar nada no PATH), a saída dele é
formatada pra humano e parsear texto de CLI quebra a cada versão. O servidor
HTTP é a interface estável.
"""

import re
from typing import Any

import httpx

from . import config


class OllamaError(Exception):
    """Falha ao falar com o Ollama, já traduzida pra frase legível.

    A mensagem daqui é exibida ao usuário (ERROR_STATES.md §2: nada de stack
    trace no balão do chat), então ela diz o que houve e o que fazer.
    """


# Qwen3 e outros modelos "thinking" devolvem o raciocínio junto da resposta,
# embrulhado em <think>…</think>. Isso é rascunho, não resposta: sai fora antes
# de virar mensagem na tela.
_THINK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_THINK_ABERTO = re.compile(r"<think\b[^>]*>.*\Z", re.DOTALL | re.IGNORECASE)


def remover_raciocinio(texto: str) -> str:
    """Tira os blocos <think>…</think> da resposta.

    Trata também o bloco aberto e nunca fechado — acontece quando a geração
    bate no limite de tokens no meio do raciocínio. Nesse caso o que sobra
    depois da abertura é rascunho até o fim, e o certo é descartar tudo dali
    pra frente em vez de mostrar meio pensamento como se fosse resposta.
    """
    texto = _THINK.sub("", texto)
    texto = _THINK_ABERTO.sub("", texto)
    return texto.strip()


class ModelGateway:
    """Cliente do Ollama. Uma instância por processo (ver main.py)."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or config.OLLAMA_URL).rstrip("/")
        self._cliente = httpx.AsyncClient(
            base_url=self.base_url,
            # O Ollama é loopback: mandar a chamada pro proxy do sistema
            # (HTTP_PROXY/ALL_PROXY no ambiente) só faz a conexão sair da
            # máquina pra tentar voltar, e onde há proxy corporativo ela não
            # volta — vira timeout no lugar de "conexão recusada".
            trust_env=False,
            timeout=httpx.Timeout(
                connect=config.TIMEOUT_CONEXAO,
                read=config.TIMEOUT_LEITURA,
                write=config.TIMEOUT_CONEXAO,
                pool=config.TIMEOUT_CONEXAO,
            ),
        )

    async def fechar(self) -> None:
        await self._cliente.aclose()

    # --- rede -------------------------------------------------------------

    async def _pedir(self, metodo: str, rota: str, **kwargs: Any) -> dict[str, Any]:
        """Faz a chamada e converte qualquer falha de rede em OllamaError."""
        try:
            resposta = await self._cliente.request(metodo, rota, **kwargs)
            resposta.raise_for_status()
            return resposta.json()
        except httpx.ConnectError as erro:
            raise OllamaError(
                "Não consegui acessar o modelo local. Verificar se o Ollama "
                "está rodando."
            ) from erro
        except httpx.ConnectTimeout as erro:
            raise OllamaError(
                f"O Ollama não respondeu em {config.TIMEOUT_CONEXAO:.0f}s em "
                f"{self.base_url}. Verificar se o serviço está de pé."
            ) from erro
        except httpx.ReadTimeout as erro:
            raise OllamaError(
                "O modelo demorou demais para responder. Tentar de novo ou usar "
                "um modelo menor."
            ) from erro
        except httpx.HTTPStatusError as erro:
            raise OllamaError(self._ler_erro(erro.response)) from erro
        except httpx.HTTPError as erro:
            raise OllamaError(f"Falha ao falar com o Ollama: {erro}") from erro
        except ValueError as erro:  # JSON inválido
            raise OllamaError("O Ollama devolveu uma resposta que não entendi.") from erro

    @staticmethod
    def _ler_erro(resposta: httpx.Response) -> str:
        """Extrai a mensagem de erro do Ollama, que vem em {"error": "..."}."""
        detalhe = ""
        try:
            corpo = resposta.json()
            if isinstance(corpo, dict):
                detalhe = str(corpo.get("error") or "").strip()
        except ValueError:
            detalhe = resposta.text.strip()[:200]

        if resposta.status_code == 404 and detalhe:
            # O 404 do /api/chat é quase sempre modelo não instalado, e a
            # mensagem crua ("model 'x' not found, try pulling it first") não
            # diz o comando.
            return f"{detalhe}. Instalar com: ollama pull <modelo>."
        return detalhe or f"O Ollama respondeu {resposta.status_code}."

    # --- operações --------------------------------------------------------

    async def is_up(self) -> bool:
        """True se o Ollama atende. Nunca levanta — é o que /health consulta."""
        try:
            await self._pedir("GET", "/api/tags")
            return True
        except OllamaError:
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """Modelos instalados, normalizados pro que a interface precisa."""
        dados = await self._pedir("GET", "/api/tags")
        modelos = []
        for m in dados.get("models") or []:
            detalhes = m.get("details") or {}
            modelos.append(
                {
                    "nome": m.get("model") or m.get("name") or "",
                    "tamanho": m.get("size") or 0,
                    "familia": detalhes.get("family") or "",
                    "parametros": detalhes.get("parameter_size") or "",
                    "quantizacao": detalhes.get("quantization_level") or "",
                    "modificado": m.get("modified_at") or "",
                }
            )
        return [m for m in modelos if m["nome"]]

    async def modelo_padrao(self) -> str:
        """Qual modelo usar quando o cliente não informa nenhum.

        Ordem: o que estiver fixado no ambiente; senão o primeiro instalado que
        não seja de embedding. Não há cache — `ollama pull` e `ollama rm`
        acontecem com o app aberto, e uma lista velha aqui viraria um 404 na
        cara do usuário.
        """
        if config.MODELO_PADRAO:
            return config.MODELO_PADRAO

        modelos = await self.list_models()
        if not modelos:
            raise OllamaError(
                "Nenhum modelo instalado no Ollama. Instalar um com: "
                "ollama pull qwen3:8b."
            )

        for m in modelos:
            if not any(marca in m["nome"].lower() for marca in config.MARCAS_DE_EMBEDDING):
                return m["nome"]

        # Só sobraram modelos de embedding: dizer isso é mais útil do que
        # mandar uma conversa pra um modelo que não conversa.
        raise OllamaError(
            "Só há modelos de embedding instalados. Instalar um de conversa "
            "com: ollama pull qwen3:8b."
        )

    async def chat(
        self, messages: list[dict[str, str]], model: str | None = None
    ) -> dict[str, Any]:
        """Uma rodada de conversa. `messages` já vem montada pelo chamador."""
        modelo = model or await self.modelo_padrao()
        dados = await self._pedir(
            "POST",
            "/api/chat",
            json={
                "model": modelo,
                "messages": messages,
                # Sem streaming: a resposta volta inteira num JSON só. Streaming
                # entra junto com o cursor vivo da Thread, não antes.
                "stream": False,
                # Desliga o modo thinking onde o modelo suporta o parâmetro
                # (Qwen3, deepseek-r1). Onde não suporta, é ignorado — por isso
                # a limpeza de <think> continua valendo como rede de proteção.
                "think": False,
            },
        )

        mensagem = dados.get("message") or {}
        texto = remover_raciocinio(str(mensagem.get("content") or ""))
        if not texto:
            raise OllamaError(
                f"O modelo {modelo} devolveu uma resposta vazia. Tentar de novo."
            )

        duracao = dados.get("total_duration") or 0  # nanossegundos
        return {
            "response": texto,
            "model": dados.get("model") or modelo,
            "eval_count": int(dados.get("eval_count") or 0),
            "total_duration_ms": round(int(duracao) / 1_000_000, 1),
        }
