"""Quando nenhuma palavra bate, o significado decide? (25/11/2026)

As regras de personalidades.py acertaram 72 de 80 frases inéditas; 6 dos 8 erros
foram "nenhuma palavra bateu, respondeu o Solis geral". Aqui se mede o "modelo
baratíssimo" do IDEIAS.md: o embedding que o Solis já calcula pra busca na
memória (embeddinggemma, no PC, sem custo), comparado com exemplos de cada
personalidade. Só entra quando as regras não acham ninguém.

    backend/.venv/Scripts/python design/personalidades/medir_embedding.py
"""
import asyncio
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from medir_quem_responde import FRASES, FRASES_2, FRASES_3  # noqa: E402
from solis import busca, ollama, personalidades as p  # noqa: E402

# Exemplos de cada uma, escritos como o nicho (não são as frases medidas).
EXEMPLOS = {
    'assessor': ['anota esse gasto', 'quanto eu gastei', 'minhas finanças do mês', 'paguei uma conta',
                 'o que eu tenho marcado', 'me lembra de uma coisa', 'organiza minha semana', 'minhas tarefas',
                 'quanto sobrou do dinheiro', 'marca um compromisso'],
    'ed': ['monta um treino pra mim', 'quero ganhar massa muscular', 'quantas calorias eu como', 'minha dieta',
           'exercício pra perna', 'quero emagrecer', 'o que comer antes de treinar', 'dor depois da academia',
           'quanto de proteína', 'meu peso hoje'],
    'eva': ['estou cansado do meu trabalho', 'quero mudar de emprego', 'como crescer na carreira',
            'problema com meu chefe', 'pedir aumento', 'me preparar pra entrevista', 'estou desmotivado no trabalho',
            'quero uma promoção', 'ideias de renda extra', 'o que fazer da minha carreira'],
    'jarvis': ['o código deu erro', 'roda os testes do projeto', 'faz o deploy', 'qual linguagem de programação',
               'o servidor caiu', 'o que o Claude Code está fazendo', 'cria um script', 'banco de dados do app',
               'corrige esse bug', 'como funciona essa API'],
    'solis': ['qual a capital da França', 'quanto está o dólar', 'como vai estar o tempo', 'quem ganhou o jogo',
              'abre o navegador', 'que horas são', 'me conta uma curiosidade', 'quem foi Santos Dumont',
              'toca uma música', 'qual o tamanho da Terra'],
}


# O risco do significado: roubar do Solis a pergunta geral (a maioria do dia a dia).
GERAIS = [(f, None, 'solis') for f in [
    'quanto é 15 vezes 32?', 'quem escreveu Dom Casmurro?', 'traduz "obrigado" pra inglês', 'que dia cai o Natal?',
    'qual o filme mais visto do ano?', 'me conta uma piada', 'quantos habitantes tem São Paulo?',
    'qual a distância até a lua?', 'explica o que é inflação', 'como faz arroz soltinho?',
    'qual o melhor celular até 2 mil reais?', 'vai chover hoje?', 'liga a luz do quarto', 'pausa a música',
    'o que significa saudade?', 'como se diz cachorro em japonês?', 'quem é o presidente da França?',
    'quanto tempo leva pra ir de carro de SP ao Rio?', 'abre o YouTube', 'qual a raiz quadrada de 144?',
]]

GEMINI = '--gemini' in sys.argv
GEMINI_MODELO = 'gemini-embedding-001'
TEMPOS: list[float] = []


async def vetores(textos: list[str]) -> np.ndarray:
    if GEMINI:
        # Online primeiro (a regra do Matheus): o embedding do Gemini, grátis.
        import time
        from google import genai
        from google.genai import types
        from solis import apis
        cliente = genai.Client(api_key=apis._chave_de('gemini'))
        cfg = types.EmbedContentConfig(task_type='CLASSIFICATION', output_dimensionality=768)
        lista = []
        # O grátis: 100 textos por minuto (medido: o 429 diz "limit: 100"). Aos 10, com folga.
        for i in range(0, len(textos), 10):
            t0 = time.perf_counter()
            r = await cliente.aio.models.embed_content(model=GEMINI_MODELO, contents=textos[i:i + 10], config=cfg)
            TEMPOS.append(time.perf_counter() - t0)
            lista += [e.values for e in r.embeddings]
            await asyncio.sleep(7)
        v = np.array(lista, dtype=np.float32)
    else:
        v = np.array(await ollama.embeddings(busca.MODELO, [busca.PERGUNTA + t for t in textos]), dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


async def um_so() -> float:
    """O tempo de uma frase sozinha (como seria numa mensagem)."""
    import time
    t0 = time.perf_counter()
    await vetores(['quero crescer na empresa, por onde começo?'])
    return time.perf_counter() - t0


async def main() -> None:
    nomes = list(EXEMPLOS)
    exemplos = {k: await vetores(v) for k, v in EXEMPLOS.items()}
    todas = [('lote 1', FRASES), ('lote 2', FRASES_2), ('lote 3', FRASES_3), ('gerais', GERAIS)]
    # Os vetores só das que vão precisar (sem regra e sem quem estava falando), uma vez.
    precisam = sorted({f for _, frases in todas for f, antes, _ in frases
                       if not antes and not (p.chamado(f) or p.do_assunto(f, antes))})
    vetor = dict(zip(precisam, await vetores(precisam)))
    for margem in (0.0, 0.02, 0.05):
        certas = total = roubadas = sem_regra = 0
        erros = []
        for _, frases in todas:
            for f, antes, esperado in frases:
                v = vetor.get(f)
                total += 1
                pela_regra = p.chamado(f) or p.do_assunto(f, antes)
                if pela_regra or antes:
                    deu = pela_regra or antes
                else:
                    sem_regra += 1
                    # A maior parecença com algum exemplo de cada uma.
                    notas = {k: float((exemplos[k] @ v).max()) for k in nomes}
                    ordem = sorted(notas, key=notas.get, reverse=True)
                    deu = ordem[0] if notas[ordem[0]] - notas[ordem[1]] >= margem else 'solis'
                    if esperado == 'solis' and deu != 'solis':
                        roubadas += 1
                if deu == esperado:
                    certas += 1
                else:
                    erros.append((f, deu, esperado))
        print(f'margem {margem}: {certas} de {total} ({sem_regra} sem regra; {roubadas} do geral roubadas)')
        for f, deu, esperado in erros:
            print(f'   "{f}" -> {deu}, era {esperado}')
    sozinhas = []
    for _ in range(5):
        sozinhas.append(await um_so() - 7)  # menos a pausa do grátis (vetores dorme 7 s)
    sozinhas.sort()
    print(f'uma frase sozinha: mediana {sozinhas[2]:.2f} s (de {sozinhas[0]:.2f} a {sozinhas[-1]:.2f} s)')


if __name__ == '__main__':
    asyncio.run(main())
