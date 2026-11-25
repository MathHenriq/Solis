"""As vozes candidatas de cada personalidade, pro teste cego do Matheus (25/11/2026).

Cada personalidade, 3 vozes do Gemini lendo a mesma fala típica dela, pelo
Gemini Live (o mesmo do pedido ao vivo, com cota grátis própria: não gasta as
10 respostas por dia da voz G). Os arquivos saem com letras (A, B, C) e a chave
fica num arquivo à parte, pra ouvir sem saber qual é qual.

    backend/.venv/Scripts/python design/personalidades/gerar_vozes.py
"""
import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from solis import fala, pedido_ao_vivo  # noqa: E402

PASTA = Path(__file__).resolve().parent / '_vozes'
MODELO = pedido_ao_vivo.MODELO

# A primeira de cada é a que está no código hoje (personalidades.py).
CANDIDATAS = {
    'jarvis': ['Charon', 'Sadaltager', 'Orus'],
    'eva': ['Sulafat', 'Vindemiatrix', 'Achernar'],
    'ed': ['Fenrir', 'Puck', 'Sadachbia'],
    'assessor': ['Schedar', 'Iapetus', 'Kore'],
}
FALAS = {
    'jarvis': 'Aqui é o Jarvis. O Claude Code terminou a tarefa: mudou três arquivos e os testes passaram. Antes de '
              'publicar, vale conferir se a chave da API não ficou no código.',
    'eva': 'Aqui é a Eva. Entendo, deve ter sido um dia pesado. Me conta: o que mais te incomodou naquela reunião?',
    'ed': 'Aqui é o Ed. Bora! Hoje é peito: supino reto, quatro séries de dez, com um minuto de descanso. E bebe água!',
    'assessor': 'Aqui é o Assessor. Anotado: gasto de cinquenta reais no mercado, hoje. No mês, os gastos somam '
                'oitocentos e doze reais.',
}
JEITO = {
    'jarvis': 'sereno, preciso, de engenheiro experiente',
    'eva': 'acolhedor e calmo, de quem escuta',
    'ed': 'animado e com energia, de treinador',
    'assessor': 'direto e organizado, de assessor executivo',
}


async def gerar(voz: str, texto: str, jeito: str) -> tuple[bytes, str]:
    from google.genai import types
    cfg = types.LiveConnectConfig(
        response_modalities=['AUDIO'],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz))),
        system_instruction=('Você é um locutor. Leia em voz alta, em português do Brasil, EXATAMENTE o texto que o '
                            f'usuário mandar, palavra por palavra, sem acrescentar nada, num tom {jeito}.'),
    )
    mp3, disse = fala._PcmEmMp3(), ''
    saida = b''
    async with pedido_ao_vivo._cliente().aio.live.connect(model=MODELO, config=cfg) as s:
        await s.send_client_content(turns=[types.Content(role='user', parts=[types.Part(text=texto)])],
                                    turn_complete=True)
        async for msg in s.receive():
            sc = msg.server_content
            if not sc:
                continue
            if sc.output_transcription and sc.output_transcription.text:
                disse += sc.output_transcription.text
            for parte in (sc.model_turn.parts if sc.model_turn else None) or []:
                if parte.inline_data and parte.inline_data.data:
                    saida += mp3(parte.inline_data.data)
            if sc.turn_complete:
                break
    return saida + mp3.fim(), ' '.join(disse.split())


async def main() -> None:
    PASTA.mkdir(exist_ok=True)
    chave = {}
    for quem, vozes in CANDIDATAS.items():
        letras = ['A', 'B', 'C']
        random.shuffle(letras)
        for letra, voz in zip(letras, vozes):
            audio, disse = await gerar(voz, FALAS[quem], JEITO[quem])
            (PASTA / f'{quem}-{letra}.mp3').write_bytes(audio)
            chave[f'{quem}-{letra}'] = voz
            print(f'{quem}-{letra}: {len(audio) // 1024} KB · disse: {disse}')
    (PASTA / 'chave.json').write_text(json.dumps(chave, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
