"""Quem responde, medido em frases que não serviram pra ajustar as regras
(personalidades.py, 25/11/2026). Cada uma: a frase, quem está falando antes
(None = conversa nova) e quem deveria responder.

    backend/.venv/Scripts/python design/personalidades/medir_quem_responde.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from solis import personalidades as p  # noqa: E402

FRASES = [
    # Assessor: dinheiro e rotina.
    ('paguei 230 de condomínio', None, 'assessor'),
    ('recebi 400 de um freela de design', None, 'assessor'),
    ('quanto sobrou do meu salário esse mês?', None, 'assessor'),
    ('tenho alguma coisa marcada pra quinta?', None, 'assessor'),
    ('me lembra de ligar pro dentista às 14h', None, 'assessor'),
    ('anota que o aluguel vence dia 5', None, 'assessor'),
    ('Uber 32,40', None, 'assessor'),
    ('quais são as minhas tarefas de hoje?', None, 'assessor'),
    ('cancela a reunião de amanhã', 'jarvis', 'assessor'),
    ('quanto eu gastei com comida em outubro?', 'ed', 'assessor'),
    # Ed: treino, peso, alimentação.
    ('qual o melhor horário pra treinar?', None, 'ed'),
    ('quanto de creatina eu tomo por dia?', None, 'ed'),
    ('tô pesando 84, quero chegar em 78', None, 'ed'),
    ('me passa um cardápio pra ganhar massa', None, 'ed'),
    ('dá pra fazer cardio em jejum?', None, 'ed'),
    ('agachamento machuca o joelho?', None, 'ed'),
    ('hoje eu corri 5 km', None, 'ed'),
    ('o que eu como antes da academia?', 'eva', 'ed'),
    # Eva: carreira e trabalho.
    ('tô pensando em pedir demissão', None, 'eva'),
    ('recebi uma proposta de emprego em outra empresa', None, 'eva'),
    ('como eu peço um aumento de salário?', None, 'eva'),
    ('minha gestora me cobrou na frente de todo mundo', None, 'eva'),
    ('quero mudar de área, sair de TI', None, 'eva'),
    ('preciso desabafar sobre o trabalho', None, 'eva'),
    ('revisa meu currículo', None, 'eva'),
    ('como eu faço uma renda extra?', 'assessor', 'eva'),
    # Jarvis: o lado técnico.
    ('o build do app quebrou', None, 'jarvis'),
    ('cria um script que renomeia as fotos', None, 'jarvis'),
    ('o que o Codex fez no repositório?', None, 'jarvis'),
    ('abre um pull request com essa mudança', None, 'jarvis'),
    ('a API da Groq está respondendo erro 429', None, 'jarvis'),
    ('refatora essa função pra ficar mais limpa', None, 'jarvis'),
    ('sobe o banco de dados do projeto', 'ed', 'jarvis'),
    # Pelo nome.
    ('Eva, você tá aí?', None, 'eva'),
    ('Solis, passa pro Assessor', 'eva', 'assessor'),
    ('Edi, qual meu treino de hoje?', None, 'ed'),
    # Quem está falando continua (sem assunto de outra).
    ('e se eu fizer três vezes por semana?', 'ed', 'ed'),
    ('obrigado, me ajudou muito', 'eva', 'eva'),
    ('e o resto?', 'jarvis', 'jarvis'),
    # O geral, numa conversa nova.
    ('qual a previsão do tempo pra amanhã?', None, 'solis'),
]


# O lote 1 deu 37 de 40 na primeira medida (25/11/2026); os 3 erros foram
# corrigidos. Pra a medida não ser feita nas mesmas frases do conserto, o
# lote 2 foi escrito depois do conserto e medido uma vez.
FRASES_2 = [
    ('paguei a fatura do cartão', None, 'assessor'),
    ('quanto eu tenho de saldo?', None, 'assessor'),
    ('o que eu tenho pra fazer hoje?', None, 'assessor'),
    ('almoço 28 reais', None, 'assessor'),
    ('marca dentista dia 3 às 10h', None, 'assessor'),
    ('quanto eu devo comer de proteína pesando 80 kg?', None, 'ed'),
    ('monta uma dieta de 2000 calorias', None, 'ed'),
    ('tô com dor no ombro depois do supino', None, 'ed'),
    ('qual exercício é melhor pra glúteo?', None, 'ed'),
    ('meu líder quer que eu assuma o time', None, 'eva'),
    ('vale a pena fazer MBA pra minha carreira?', None, 'eva'),
    ('tô frustrado, ninguém valoriza o que eu entrego no trabalho', None, 'eva'),
    ('me ajuda a escrever o post do LinkedIn', None, 'eva'),
    ('o servidor caiu de novo', None, 'jarvis'),
    ('qual a diferença entre React e Vue?', None, 'jarvis'),
    ('o Claude Code travou no meio da tarefa', None, 'jarvis'),
    ('roda o npm install no projeto', None, 'jarvis'),
    ('Jarvis, bom dia', None, 'jarvis'),
    ('e amanhã, como fica?', 'assessor', 'assessor'),
    ('quem descobriu o Brasil?', None, 'solis'),
]


# O lote 2 deu 17 de 20 (25/11/2026). O conserto foi de método, não de
# palavra: o que o Solis já reconhece como rotina (os pedidos rápidos de agenda,
# tarefas, lembrete, lançamento e gastos) é do Assessor, e no empate o dono do
# assunto ganha do Assessor. O lote 3 foi escrito antes de rodar o conserto.
FRASES_3 = [
    ('lança 45 de farmácia', None, 'assessor'),
    ('quais compromissos eu tenho essa semana?', None, 'assessor'),
    ('me lembra de tomar água daqui a uma hora', None, 'assessor'),
    ('quanto eu gastei hoje?', None, 'assessor'),
    ('anota uma tarefa: mandar o relatório', None, 'assessor'),
    ('o que eu janto pra não sair da dieta?', None, 'ed'),
    ('quantos dias por semana eu devo malhar?', None, 'ed'),
    ('me dá um treino de 30 minutos em casa', None, 'ed'),
    ('whey ou creatina, qual vale mais a pena?', None, 'ed'),
    ('tô com medo de ser demitido', None, 'eva'),
    ('como eu falo com meu chefe sobre a sobrecarga?', None, 'eva'),
    ('quero crescer na empresa, por onde começo?', None, 'eva'),
    ('acho que tô entrando em burnout', None, 'eva'),
    ('o teste do backend está falhando', None, 'jarvis'),
    ('faz um script em python pra baixar os arquivos', None, 'jarvis'),
    ('o Codex terminou a tarefa?', None, 'jarvis'),
    ('qual banco de dados eu uso pro app?', None, 'jarvis'),
    ('Eva, e aí?', 'ed', 'eva'),
    ('e isso funciona com a minha dieta?', 'ed', 'ed'),
    ('qual o tamanho da lua?', None, 'solis'),
]


def medir(nome: str, frases: list) -> None:
    erros = [(f, antes, esperado, p.quem(f, antes)) for f, antes, esperado in frases if p.quem(f, antes) != esperado]
    print(f'{nome}: {len(frases) - len(erros)} de {len(frases)} certas')
    for f, antes, esperado, deu in erros:
        print(f'  ERROU: "{f}" (antes: {antes}) -> {deu}, era {esperado}')


def main() -> None:
    medir('lote 1 (depois do conserto)', FRASES)
    medir('lote 2 (inédito no primeiro conserto)', FRASES_2)
    medir('lote 3 (inédito)', FRASES_3)


if __name__ == '__main__':
    main()
