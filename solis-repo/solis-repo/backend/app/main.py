"""API local do Solis.

Três rotas, o mínimo pra tela de Conversa funcionar contra um modelo de
verdade: saber se o motor está de pé, saber o que está instalado, e conversar.
Roda em 127.0.0.1 — não é um serviço de rede, é um processo auxiliar do app na
mesma máquina.
"""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import config
from .gateway import ModelGateway, OllamaError


@asynccontextmanager
async def ciclo(app: FastAPI):
    """Um cliente HTTP pro processo inteiro.

    Criar um httpx.AsyncClient por requisição joga fora o pool de conexões e
    paga handshake a cada mensagem — com o Ollama em loopback isso é barato,
    mas é desperdício sem motivo.
    """
    app.state.gateway = ModelGateway()
    try:
        yield
    finally:
        await app.state.gateway.fechar()


app = FastAPI(title="Solis", version="0.1.0", lifespan=ciclo)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def gateway() -> ModelGateway:
    return app.state.gateway


# --- contratos ------------------------------------------------------------


class Turno(BaseModel):
    """Um turno do histórico vindo do cliente.

    `role` não aceita "system" de propósito: o system prompt é montado aqui
    (config.SYSTEM_PROMPT) e não é coisa que o frontend possa injetar.
    """

    role: Literal["user", "assistant"]
    content: str


class PedidoChat(BaseModel):
    message: str = Field(min_length=1)
    model: str | None = None
    history: list[Turno] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def _nao_vazia(cls, v: str) -> str:
        # min_length=1 deixa passar "   ", e espaço em branco não é pergunta:
        # mandar isso pro modelo gasta uma geração inteira pra nada.
        if not v.strip():
            raise ValueError("mensagem vazia")
        return v


class RespostaChat(BaseModel):
    response: str
    model: str
    eval_count: int
    total_duration_ms: float


class Saude(BaseModel):
    status: str
    ollama: Literal["online", "offline"]


# --- rotas ----------------------------------------------------------------


@app.get("/health", response_model=Saude)
async def health() -> Saude:
    """Sempre 200, mesmo com o Ollama fora do ar.

    Quem pergunta se algo está de pé precisa de resposta, não de exceção: um
    503 aqui obrigaria o frontend a tratar "falhou a checagem" e "o motor está
    parado" como o mesmo caso, e os dois pedem telas diferentes. O status HTTP
    fala do backend; o campo `ollama` fala do motor.
    """
    return Saude(status="ok", ollama="online" if await gateway().is_up() else "offline")


@app.get("/models")
async def models() -> dict:
    """Modelos instalados e qual deles responde se ninguém escolher."""
    g = gateway()
    try:
        instalados = await g.list_models()
    except OllamaError as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro

    # Sem modelo nenhum, `modelo_padrao` levanta — aqui isso não é erro da
    # rota: a lista vazia já é a resposta, e o default vem nulo.
    try:
        padrao = await g.modelo_padrao()
    except OllamaError:
        padrao = None

    return {"models": instalados, "default": padrao}


@app.post("/chat", response_model=RespostaChat)
async def chat(pedido: PedidoChat) -> RespostaChat:
    """Uma mensagem, uma resposta.

    A conversa que vai pro modelo é montada aqui: system prompt do backend,
    depois o histórico recente que o cliente mandou, depois a mensagem nova.
    """
    historico = pedido.history[-config.HISTORICO_MAX :]
    mensagens = [{"role": "system", "content": config.SYSTEM_PROMPT}]
    mensagens += [
        {"role": t.role, "content": t.content} for t in historico if t.content.strip()
    ]
    mensagens.append({"role": "user", "content": pedido.message.strip()})

    try:
        resultado = await gateway().chat(mensagens, model=pedido.model)
    except OllamaError as erro:
        # 503 e não 500: o backend está bem, quem não está é o motor. A
        # mensagem já vem legível do gateway e é ela que aparece no chat.
        raise HTTPException(status_code=503, detail=str(erro)) from erro

    return RespostaChat(**resultado)


def main() -> None:
    """Atalho pra `python -m app.main` sem decorar a linha do uvicorn."""
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)


if __name__ == "__main__":
    main()
