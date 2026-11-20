"""Os NEGATIVOS em português: o que soa perto de "Solis" e não pode acordar ("só
isso", "sol", "Celso", "Sales"...) e frases comuns de casa. O treinador oficial
gera os dele em inglês, com o Piper — que talvez nem instale no Colab de hoje;
estes vão no lugar. As mesmas vozes do Edge dos positivos, em três velocidades
e dois tons, em design/_treino-solis/negativos-tts/ (fora do git).

Uso: backend/.venv/Scripts/python design/gravar-solis/gerar_negativos.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gerar_vozes as g  # noqa: E402

g.DESTINO = Path(__file__).resolve().parents[1] / '_treino-solis' / 'negativos-tts'
PARECIDAS = ['Só isso.', 'É isso.', 'Sol.', 'Sóis.', 'Solo.', 'Celso.', 'Sales.', 'Sales, vem cá.', 'Solange.',
             'Solista.', 'Só eles.', 'Só lhes.', 'Sólido.', 'Solução.', 'Isso.', 'Olha isso.', 'Soltei.',
             'Sozinho.', 'Sorriso.', 'Solar.', 'Ei, Celso.', 'Oi, Sales.', 'Só isso aí.', 'Saulo.', 'Sólon.',
             'Ei, isso.', 'Oi, Lis.']
CASA = ['Mãe, cadê o controle?', 'Pai, vamos almoçar?', 'Que horas são?', 'Liga a televisão.',
        'Olha que legal isso.', 'Vamos sair mais tarde.', 'Você viu meu celular?', 'Tá muito calor hoje.',
        'Bom dia, gente.', 'Pode desligar a luz.', 'Já terminei a tarefa.', 'O jogo começa às oito.',
        'Passa o sal, por favor.', 'Amanhã eu vou trabalhar cedo.', 'Esse filme é muito bom.']
g.VOZES = ['pt-BR-ThalitaMultilingualNeural', 'pt-BR-AntonioNeural', 'pt-BR-FranciscaNeural', 'pt-PT-DuarteNeural',
           'pt-PT-RaquelNeural', 'en-US-AvaMultilingualNeural', 'en-US-AndrewMultilingualNeural']
g.FRASES = PARECIDAS + CASA
g.TONS = ['-8Hz', '+8Hz']

asyncio.run(g.main())
