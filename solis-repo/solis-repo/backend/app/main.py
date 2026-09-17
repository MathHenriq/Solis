"""API local do Solis.

O mínimo pra Conversa funcionar contra um modelo de verdade — saber se o motor
está de pé, o que está instalado, conversar — mais a base de conhecimento:
subir documento, listar, remover, buscar, e usar o que foi encontrado como
contexto da resposta.

Roda em 127.0.0.1 — não é um serviço de rede, é um processo auxiliar do app na
mesma máquina.

As rotas `/knowledge/*` não dependem do Ollama. Indexar é trabalho de SQLite, e
continua funcionando com o motor desligado: dá pra montar o acervo primeiro e
ligar o modelo depois.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import config, ingest, rag, store
from .gateway import ModelGateway, OllamaError


@asynccontextmanager
async def ciclo(app: FastAPI):
    """Um cliente HTTP pro processo inteiro.

    Criar um httpx.AsyncClient por requisição joga fora o pool de conexões e
    paga handshake a cada mensagem — com o Ollama em loopback isso é barato,
    mas é desperdício sem motivo.
    """
    store.init_db()
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
    allow_methods=["GET", "POST", "DELETE"],
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
    # Ligado por padrão: quem subiu documento espera que o Solis os use sem ter
    # que pedir. Desligar serve pra comparar a resposta com e sem contexto.
    use_knowledge: bool = True

    @field_validator("message")
    @classmethod
    def _nao_vazia(cls, v: str) -> str:
        # min_length=1 deixa passar "   ", e espaço em branco não é pergunta:
        # mandar isso pro modelo gasta uma geração inteira pra nada.
        if not v.strip():
            raise ValueError("mensagem vazia")
        return v


class Fonte(BaseModel):
    """De onde saiu um pedaço da resposta."""

    document: str
    chunk_idx: int
    score: float
    preview: str


class RespostaChat(BaseModel):
    response: str
    model: str
    eval_count: int
    total_duration_ms: float
    # Vazio quando não houve consulta ou o gate reprovou. A interface usa isto
    # (e não `used_knowledge`) pra decidir se mostra as fontes.
    sources: list[Fonte] = Field(default_factory=list)
    used_knowledge: bool = False


class Documento(BaseModel):
    id: int
    name: str
    chars: int
    n_chunks: int
    status: Literal["processado", "erro"]
    error: str | None = None
    created_at: str = ""


class PedidoBusca(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=config.RAG_K, ge=1, le=20)


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


# --- base de conhecimento -------------------------------------------------


@app.post("/knowledge/documents", response_model=Documento)
async def subir_documento(file: UploadFile = File(...)) -> Documento:
    """Recebe um arquivo, extrai, chunka e indexa.

    A ingestão vai pra `asyncio.to_thread` porque é trabalho síncrono e pesado:
    pypdf percorrendo trezentas páginas segura o event loop, e enquanto isso o
    processo inteiro para de responder — `/health` incluído. Do lado do app
    isso aparece como o Solis inteiro travado por causa de um upload.

    Arquivo ilegível não vira erro HTTP: vira documento com status 'erro' e a
    mensagem, porque é isso que a tela de Conhecimento precisa mostrar na linha
    dele. O 4xx fica pros casos em que não há o que registrar — sem nome, sem
    conteúdo, ou grande demais.
    """
    nome = Path(file.filename or "").name.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Arquivo sem nome.")

    dados = await file.read()
    if not dados:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    limite = config.MAX_UPLOAD_MB * 1024 * 1024
    if len(dados) > limite:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo acima de {config.MAX_UPLOAD_MB} MB. Dividir em partes menores.",
        )

    resultado = await asyncio.to_thread(ingest.ingerir, nome, dados)
    return Documento(**resultado)


@app.get("/knowledge/documents", response_model=list[Documento])
async def documentos() -> list[Documento]:
    linhas = await asyncio.to_thread(store.listar_documentos)
    return [Documento(**l) for l in linhas]


@app.delete("/knowledge/documents/{doc_id}")
async def remover(doc_id: int) -> dict[str, Any]:
    """Apaga o documento e, por cascata, seus chunks e o que eles ocupam no FTS."""
    apagou = await asyncio.to_thread(store.remover_documento, doc_id)
    if not apagou:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return {"removed": doc_id}


@app.post("/knowledge/search")
async def buscar_conhecimento(pedido: PedidoBusca) -> dict[str, Any]:
    """Busca crua, sem modelo nenhum no meio.

    Existe pra depurar: mostra a consulta FTS5 que a pergunta gerou, os chunks
    com score e se o gate aprovaria. Quando o Solis responde "não encontrei" e
    o usuário jura que está no documento, é aqui que se vê em qual das três
    etapas a coisa parou.
    """
    fts_query = rag.build_fts_query(pedido.query)
    if not fts_query:
        return {
            "fts_query": "",
            "chunks": [],
            "passou_no_gate": False,
            "motivo": "A pergunta não tem termos buscáveis.",
        }

    achados = await asyncio.to_thread(store.buscar, fts_query, pedido.k)
    aprovados = rag.gate_relevancia(pedido.query, achados, config.RAG_MINIMO)
    return {
        "fts_query": fts_query,
        "chunks": achados,
        "passou_no_gate": bool(aprovados),
        "motivo": ""
        if aprovados
        else ("Nada encontrado." if not achados else "Os trechos não cobrem a pergunta."),
    }


# --- conversa -------------------------------------------------------------


async def _contexto_para(pergunta: str) -> tuple[str, list[dict[str, Any]]]:
    """Trecho + fontes pra esta pergunta. ("", []) quando não houver.

    Três portões, nesta ordem, e cada um evita um jeito diferente de errar:

    1. `build_fts_query` vazia — "oi, tudo bem?" não tem termo buscável.
       Consultar aqui seria gastar ida ao banco pra trazer ruído.
    2. Busca sem resultado — o acervo não fala disso.
    3. Gate reprovou — veio alguma coisa, mas não cobre a pergunta. É o caso
       mais perigoso: sem o gate, o modelo recebe um trecho aleatório com a
       ordem de responder só por ele, e responde qualquer coisa com ar de
       fundamentada.
    """
    fts_query = rag.build_fts_query(pergunta)
    if not fts_query:
        return "", []

    achados = await asyncio.to_thread(store.buscar, fts_query, config.RAG_K)
    aprovados = rag.gate_relevancia(pergunta, achados, config.RAG_MINIMO)
    if not aprovados:
        return "", []

    return rag.build_context(aprovados, config.RAG_MAX_CHARS)


@app.post("/chat", response_model=RespostaChat)
async def chat(pedido: PedidoChat) -> RespostaChat:
    """Uma mensagem, uma resposta — com a base de conhecimento quando couber.

    A conversa que vai pro modelo é montada aqui: system prompt do backend,
    depois o histórico recente que o cliente mandou, depois a mensagem nova.

    Quando há contexto, ele entra NO SYSTEM, substituindo o prompt normal. A
    mensagem do usuário não é tocada. Colar os trechos na pergunta seria mais
    simples e está errado por dois motivos: o histórico passaria a carregar a
    pergunta adulterada, e o modelo trataria o documento como coisa que o
    Matheus escreveu — inclusive obedecendo o que estivesse escrito lá dentro.
    """
    pergunta = pedido.message.strip()

    trechos, fontes = ("", [])
    if pedido.use_knowledge:
        trechos, fontes = await _contexto_para(pergunta)

    system = rag.montar_system_prompt(trechos) if trechos else config.SYSTEM_PROMPT

    historico = pedido.history[-config.HISTORICO_MAX :]
    mensagens = [{"role": "system", "content": system}]
    mensagens += [
        {"role": t.role, "content": t.content} for t in historico if t.content.strip()
    ]
    mensagens.append({"role": "user", "content": pergunta})

    try:
        resultado = await gateway().chat(mensagens, model=pedido.model)
    except OllamaError as erro:
        # 503 e não 500: o backend está bem, quem não está é o motor. A
        # mensagem já vem legível do gateway e é ela que aparece no chat.
        raise HTTPException(status_code=503, detail=str(erro)) from erro

    return RespostaChat(
        **resultado,
        sources=[Fonte(**f) for f in fontes],
        used_knowledge=bool(trechos),
    )


def main() -> None:
    """Atalho pra `python -m app.main` sem decorar a linha do uvicorn."""
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)


if __name__ == "__main__":
    main()
