"""Arquivo que entra → texto limpo → chunks no banco.

Nada toca o disco: o upload chega em memória e sai em memória. Gravar o
original seria uma segunda cópia do acervo do usuário pra manter, apagar junto
e explicar — e o Solis não precisa dela pra responder.

Regra da casa: `ingerir` NUNCA levanta. Um PDF corrompido no meio de um lote
não pode derrubar a rota; ele vira uma linha com status 'erro' e a mensagem do
que houve.
"""

import io
import re
from pathlib import Path
from typing import Any

from . import store
from .rag import chunk_text

EXTENSOES = (".pdf", ".docx", ".txt", ".md")

# Abaixo disso não há o que indexar. O caso comum não é arquivo vazio, é PDF de
# página escaneada: o pypdf abre, lê zero caractere e devolve texto em branco
# sem erro nenhum. Sem esta checagem o documento entra "processado" com 0
# chunks e nunca responde nada, e o usuário não tem como saber por quê.
MIN_CARACTERES = 20


class ErroDeIngestao(Exception):
    """Falha já traduzida pra frase que a interface pode mostrar."""


# --- extração -------------------------------------------------------------


def extrair_texto(nome: str, dados: bytes) -> str:
    """Texto cru do arquivo, conforme a extensão."""
    ext = Path(nome).suffix.lower()
    if ext == ".pdf":
        return _do_pdf(dados)
    if ext == ".docx":
        return _do_docx(dados)
    if ext in (".txt", ".md"):
        # `errors="replace"` e não `strict`: arquivo salvo em latin-1 ou com um
        # byte solto no meio vira texto com um caractere estranho, o que é bem
        # melhor que recusar o documento inteiro por causa dele.
        return dados.decode("utf-8", errors="replace")
    raise ErroDeIngestao(
        f"Formato {ext or 'desconhecido'} não suportado. Usar PDF, DOCX, TXT ou MD."
    )


def _do_pdf(dados: bytes) -> str:
    from pypdf import PdfReader

    try:
        leitor = PdfReader(io.BytesIO(dados))
    except Exception as erro:
        raise ErroDeIngestao(f"Não consegui abrir o PDF: {erro}") from erro

    if getattr(leitor, "is_encrypted", False):
        # Alguns PDFs abrem com senha vazia; vale tentar antes de desistir.
        try:
            leitor.decrypt("")
        except Exception as erro:
            raise ErroDeIngestao(
                "O PDF está protegido por senha. Remover a proteção e subir de novo."
            ) from erro

    paginas: list[str] = []
    for numero, pagina in enumerate(leitor.pages, start=1):
        try:
            # extract_text() devolve None em página sem camada de texto —
            # imagem pura, assinatura digitalizada, capa. Isso não é erro: o
            # resto do documento continua valendo.
            texto = pagina.extract_text() or ""
        except Exception:
            texto = ""
        if texto.strip():
            paginas.append(texto)
        del numero
    return "\n\n".join(paginas)


def _do_docx(dados: bytes) -> str:
    import docx

    try:
        documento = docx.Document(io.BytesIO(dados))
    except Exception as erro:
        raise ErroDeIngestao(f"Não consegui abrir o DOCX: {erro}") from erro

    partes = [p.text for p in documento.paragraphs if p.text.strip()]
    # Tabela costuma carregar justamente o dado que se quer consultar (prazo,
    # valor, responsável). Cada linha vira uma linha de texto com as células
    # separadas por " | " pra não colar palavra de colunas vizinhas.
    for tabela in documento.tables:
        for linha in tabela.rows:
            celulas = [c.text.strip() for c in linha.cells if c.text.strip()]
            if celulas:
                partes.append(" | ".join(celulas))
    return "\n\n".join(partes)


# --- normalização ---------------------------------------------------------

_SOFT_HYPHEN = "­"
_HIFEN_QUEBRADO = re.compile(r"(\w)[-‐‑]\n(\w)")
# Quebra simples que NÃO vem depois de pontuação final e NÃO precede início de
# item de lista. A lookbehind exclui o que encerra frase; a lookahead exclui
# linha em branco (parágrafo) e marcador de lista.
_QUEBRA_SOLTA = re.compile(r"(?<=[^\n.!?:;•…])\n(?![\n\s]|[-*••]|\d+[.)])")
_ESPACOS = re.compile(r"[ \t ]+")
_LINHAS_VAZIAS = re.compile(r"\n{3,}")


def normalizar(texto: str) -> str:
    """Texto de PDF/DOCX → parágrafos de verdade.

    O passo que mais importa é o último: **juntar a quebra de linha simples**.
    PDF não guarda parágrafos, guarda linhas posicionadas na página — o
    extrator devolve uma quebra a cada linha VISUAL. Sem juntar, um documento
    de dez páginas vira mil linhas de sessenta caracteres, `\\n\\n` nunca
    aparece, e o `chunk_text` perde toda fronteira de parágrafo: ele passa a
    cortar por tamanho puro, no meio de frases.

    O critério pra juntar é a pontuação: linha que termina em `.`, `!`, `?`,
    `:` ou `;` acabou de fato e a quebra fica. Linha que termina no meio da
    frase era só o fim da largura da página, e a quebra vira espaço. Item de
    lista e linha em branco são preservados — é o que sobra de estrutura.
    """
    if not texto:
        return ""

    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    # Hífen de separação silábica que o editor inseriu: invisível na tela, vira
    # lixo no meio da palavra no índice.
    texto = texto.replace(_SOFT_HYPHEN, "")
    # "conhe-\ncimento" → "conhecimento"
    texto = _HIFEN_QUEBRADO.sub(r"\1\2", texto)
    texto = _QUEBRA_SOLTA.sub(" ", texto)
    texto = _ESPACOS.sub(" ", texto)
    texto = "\n".join(linha.strip() for linha in texto.split("\n"))
    texto = _LINHAS_VAZIAS.sub("\n\n", texto)
    return texto.strip()


# --- ingestão -------------------------------------------------------------


def ingerir(nome: str, dados: bytes) -> dict[str, Any]:
    """Pipeline inteiro de um arquivo. Não levanta: falha vira status 'erro'."""
    try:
        bruto = extrair_texto(nome, dados)
        texto = normalizar(bruto)

        if len(texto) < MIN_CARACTERES:
            raise ErroDeIngestao(
                "Não consegui extrair texto deste arquivo. Se for um PDF "
                "escaneado, ele é imagem e precisa passar por OCR antes."
            )

        chunks = chunk_text(texto)
        if not chunks:
            raise ErroDeIngestao("O arquivo não gerou nenhum trecho indexável.")

        doc_id = store.salvar_documento(nome, len(texto), chunks)
        return {
            "id": doc_id,
            "name": nome,
            "chars": len(texto),
            "n_chunks": len(chunks),
            "status": "processado",
            "error": None,
        }

    except ErroDeIngestao as erro:
        return _falha(nome, str(erro))
    except Exception as erro:
        # Rede de proteção: pypdf e python-docx levantam de tudo diante de
        # arquivo malformado. A rota não pode cair por causa disso.
        return _falha(nome, f"Falha ao processar o arquivo: {erro}")


def _falha(nome: str, mensagem: str) -> dict[str, Any]:
    doc_id = store.registrar_falha(nome, mensagem)
    return {
        "id": doc_id,
        "name": nome,
        "chars": 0,
        "n_chunks": 0,
        "status": "erro",
        "error": mensagem,
    }
